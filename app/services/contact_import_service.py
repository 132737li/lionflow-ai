"""
Service d'import de contacts depuis CSV ou Excel.
Retourne un rapport détaillé (lignes, ajoutés, doublons, erreurs).

✅ FIX 1 : lecture en `dtype=str` pour préserver le "+" des numéros internationaux.
✅ FIX 2 : indicatif Burundi (+257) utilisé par défaut si pas de "+".
"""

import os
import re
import tempfile
from dataclasses import dataclass, field

import pandas as pd
from flask import current_app

from app.extensions import db
from app.models.contact import Contact
from app.utils.validators import is_valid_email, normalize_phone


# Colonnes reconnues automatiquement (insensible à la casse et aux accents)
COLUMN_ALIASES = {
    "first_name": {"first_name", "firstname", "prenom", "prénom", "given name"},
    "last_name": {"last_name", "lastname", "nom", "surname", "family name"},
    "phone": {"phone", "telephone", "téléphone", "numero", "numéro", "whatsapp",
              "phone_number", "mobile", "gsm", "tel"},
    "email": {"email", "e-mail", "mail", "courriel"},
    "company": {"company", "entreprise", "societe", "société", "organization"},
    "tags": {"tags", "tag", "labels", "label", "categories"},
    "status": {"status", "statut", "state"},
}

# 🎯 Indicatif par défaut si le numéro n'a pas de préfixe international
DEFAULT_PHONE_REGION = "BI"          # ISO 3166-1 alpha-2 du Burundi
DEFAULT_PHONE_CALLING_CODE = "257"   # Code téléphonique international


@dataclass
class ImportReport:
    """Rapport d'import."""
    total_rows: int = 0
    added: int = 0
    duplicates: int = 0
    errors: list = field(default_factory=list)  # [{row, message, data}]
    detected_columns: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "total_rows": self.total_rows,
            "added": self.added,
            "duplicates": self.duplicates,
            "errors_count": len(self.errors),
            "errors": self.errors[:100],
            "detected_columns": self.detected_columns,
        }


class ContactImportService:

    # ==================================================
    # ENTRÉE PUBLIQUE
    # ==================================================
    @staticmethod
    def import_file(file_storage, business, max_rows: int = 10000) -> ImportReport:
        """
        Importe un fichier uploadé pour une entreprise donnée.
        Respecte le quota du plan.
        """
        report = ImportReport()

        if not file_storage or not file_storage.filename:
            report.errors.append({"row": 0, "message": "Aucun fichier fourni.", "data": {}})
            return report

        ext = file_storage.filename.rsplit(".", 1)[-1].lower()
        if ext not in ("csv", "xlsx", "xls"):
            report.errors.append({
                "row": 0,
                "message": f"Extension non supportée : .{ext}",
                "data": {},
            })
            return report

        tmp_fd, tmp_path = tempfile.mkstemp(suffix=f".{ext}")
        os.close(tmp_fd)
        try:
            file_storage.save(tmp_path)
            df = ContactImportService._read_dataframe(tmp_path, ext)
        except Exception as e:
            current_app.logger.exception("Erreur lecture fichier import")
            report.errors.append({
                "row": 0,
                "message": f"Impossible de lire le fichier : {e}",
                "data": {},
            })
            return report
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        if df is None or df.empty:
            report.errors.append({"row": 0, "message": "Fichier vide.", "data": {}})
            return report

        if len(df) > max_rows:
            report.errors.append({
                "row": 0,
                "message": f"Le fichier dépasse la limite autorisée ({max_rows} lignes).",
                "data": {},
            })
            return report

        # Détection colonnes
        col_map = ContactImportService._detect_columns(df.columns.tolist())
        report.detected_columns = col_map

        if "phone" not in col_map.values():
            report.errors.append({
                "row": 0,
                "message": (
                    "Impossible de détecter la colonne du numéro (phone). "
                    "Renommez la colonne en 'phone', 'telephone' ou 'whatsapp'."
                ),
                "data": {},
            })
            return report

        # Quota plan
        remaining = ContactImportService._remaining_quota(business)
        if remaining <= 0:
            report.errors.append({
                "row": 0,
                "message": (
                    f"Quota de contacts atteint pour le plan '{business.plan}'. "
                    "Passez à un plan supérieur pour importer davantage."
                ),
                "data": {},
            })
            return report

        report.total_rows = len(df)

        # Pré-chargement des téléphones existants (anti-doublon)
        existing_phones = {
            row[0] for row in
            db.session.query(Contact.phone).filter_by(business_id=business.id).all()
        }

        to_insert: list[Contact] = []
        seen_in_file: set[str] = set()

        for idx, raw in df.iterrows():
            row_dict = ContactImportService._normalize_row(raw, col_map)
            row_number = int(idx) + 2  # +1 (0-index) +1 (header)

            phone = row_dict.get("phone")
            if not phone:
                report.errors.append({
                    "row": row_number,
                    "message": "Numéro manquant.",
                    "data": row_dict,
                })
                continue

            # ✅ Normalisation avec indicatif Burundi par défaut
            normalized = ContactImportService._normalize_import_phone(phone)
            if not normalized:
                report.errors.append({
                    "row": row_number,
                    "message": (
                        f"Numéro invalide : {phone}. "
                        "Format attendu : '+<indicatif><numéro>' "
                        "(ex: +25776672387, +33611111111) ou "
                        "numéro local burundais (ex: 76672387)."
                    ),
                    "data": row_dict,
                })
                continue

            # Doublons (BDD ou fichier)
            if normalized in existing_phones:
                report.duplicates += 1
                continue
            if normalized in seen_in_file:
                report.duplicates += 1
                continue

            # Quota dynamique
            if len(to_insert) >= remaining:
                report.errors.append({
                    "row": row_number,
                    "message": "Quota de contacts du plan atteint — ligne ignorée.",
                    "data": row_dict,
                })
                continue

            # Email optionnel mais validé
            email = row_dict.get("email") or None
            if email and not is_valid_email(email):
                email = None
                report.errors.append({
                    "row": row_number,
                    "message": f"Email invalide ignoré : {row_dict.get('email')}",
                    "data": row_dict,
                })

            # Statut
            status = (row_dict.get("status") or "active").strip().lower()
            if status not in ("active", "inactive", "blocked"):
                status = "active"

            # Tags
            tags_raw = row_dict.get("tags") or ""
            tags_list = [t.strip() for t in re.split(r"[,;|]", tags_raw) if t.strip()]
            tags_str = ",".join(tags_list) if tags_list else None

            contact = Contact(
                business_id=business.id,
                first_name=(row_dict.get("first_name") or "").strip() or None,
                last_name=(row_dict.get("last_name") or "").strip() or None,
                phone=normalized,
                email=email,
                company=(row_dict.get("company") or "").strip() or None,
                tags=tags_str,
                status=status,
            )
            to_insert.append(contact)
            seen_in_file.add(normalized)

        if to_insert:
            db.session.bulk_save_objects(to_insert)
            db.session.commit()
            report.added = len(to_insert)
            
            # À la fin de import_file()
            try:
                max_contacts = business.plan_config.get("max_contacts", 0)
                if max_contacts > 0:
                    total = Contact.query.filter_by(business_id=business.id).count()
                    if total >= max_contacts * 0.9:
                        from app.services.email_service import EmailService
                        EmailService.send_quota_warning(business, used=total, limit=max_contacts) # 👈 Bon nom
            except Exception:
                current_app.logger.exception("[import] Erreur envoi alerte quota")
            
        return report

    # ==================================================
    # NORMALISATION TÉLÉPHONE (indicatif Burundi par défaut)
    # ==================================================
    @staticmethod
    def _normalize_import_phone(phone: str) -> str | None:
        """
        Normalise un numéro importé en format E.164.

        Règles :
        1. Si contient '+', on respecte l'indicatif international.
        2. Si commence par '257' (indicatif Burundi sans '+'), on ajoute le '+'.
        3. Sinon, on suppose que c'est un numéro local burundais (+257 par défaut).

        Exemples :
            "+33611111111"   → "+33611111111"   (France)
            "+25776672387"   → "+25776672387"   (Burundi)
            "25776672387"    → "+25776672387"   (Burundi, auto-préfixé)
            "76672387"       → "+25776672387"   (Burundi local)
            "33611111111"    → None             (ambigu, rejeté)
        """
        if not phone:
            return None

        phone = str(phone).strip()
        if not phone:
            return None

        # Retire les espaces, points, tirets (mais garde le '+')
        phone = re.sub(r"[\s.\-()]", "", phone)

        # Cas 1 : numéro international explicite
        if phone.startswith("+"):
            return normalize_phone(phone, default_region=DEFAULT_PHONE_REGION)

        # Cas 2 : commence par l'indicatif Burundi sans '+'
        if phone.startswith(DEFAULT_PHONE_CALLING_CODE) and len(phone) > 8:
            return normalize_phone(
                "+" + phone, default_region=DEFAULT_PHONE_REGION
            )

        # Cas 3 : numéro local burundais (ex: 76672387)
        return normalize_phone(phone, default_region=DEFAULT_PHONE_REGION)

    # ==================================================
    # LECTURE FICHIER
    # ==================================================
    @staticmethod
    def _read_dataframe(path: str, ext: str) -> pd.DataFrame | None:
        """
        Lit un fichier CSV ou Excel en préservant les chaînes brutes
        (dtype=str) afin de ne pas perdre le '+' initial des numéros
        internationaux ni les zéros de tête.
        """
        if ext == "csv":
            for encoding in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
                for sep in (None, ",", ";", "\t"):
                    try:
                        if sep is None:
                            df = pd.read_csv(
                                path,
                                encoding=encoding,
                                sep=None,
                                engine="python",
                                dtype=str,             # ✅ préserve le '+'
                                keep_default_na=False, # évite que '' devienne NaN
                            )
                        else:
                            df = pd.read_csv(
                                path,
                                encoding=encoding,
                                sep=sep,
                                dtype=str,             # ✅
                                keep_default_na=False,
                            )
                        if df is not None and len(df.columns) >= 1:
                            return df
                    except Exception:
                        continue
            return None
        # Excel
        try:
            return pd.read_excel(
                path,
                engine="openpyxl" if ext == "xlsx" else "xlrd",
                dtype=str,                                 # ✅
            )
        except Exception:
            current_app.logger.exception("Erreur lecture Excel")
            return None

    # ==================================================
    # DÉTECTION COLONNES
    # ==================================================
    @staticmethod
    def _normalize_header(h: str) -> str:
        h = str(h).strip().lower()
        h = (h.replace("é", "e").replace("è", "e").replace("ê", "e")
               .replace("à", "a").replace("ô", "o").replace("û", "u")
               .replace("ç", "c").replace("î", "i"))
        h = re.sub(r"[\s_\-]+", "_", h)
        return h

    @staticmethod
    def _detect_columns(headers: list[str]) -> dict:
        """
        Retourne {'colonne_originale': 'champ_cible'}.
        Ex: {'Téléphone': 'phone', 'Prénom': 'first_name'}
        """
        result = {}
        for h in headers:
            norm = ContactImportService._normalize_header(h)
            for target, aliases in COLUMN_ALIASES.items():
                if norm in aliases or norm in {
                    ContactImportService._normalize_header(a) for a in aliases
                }:
                    result[h] = target
                    break
        return result

    @staticmethod
    def _normalize_row(raw: pd.Series, col_map: dict) -> dict:
        """
        Convertit une ligne pandas en dict cible.
        Préserve le '+' des numéros internationaux.
        """
        out = {}
        for original, target in col_map.items():
            value = raw.get(original)

            if value is None:
                out[target] = None
                continue
            try:
                if pd.isna(value):
                    out[target] = None
                    continue
            except (TypeError, ValueError):
                pass

            # Cellule Excel numérique (rare)
            if isinstance(value, float) and value.is_integer():
                value = str(int(value))
            elif not isinstance(value, str):
                value = str(value)

            value = value.strip()
            out[target] = value if value else None

        return out

    # ==================================================
    # QUOTA
    # ==================================================
    @staticmethod
    def _remaining_quota(business) -> int:
        max_contacts = business.plan_config.get("max_contacts", 0)
        if max_contacts == 0:
            return 10**9
        used = Contact.query.filter_by(business_id=business.id).count()
        return max(max_contacts - used, 0)