"""
Service d'import de contacts depuis CSV ou Excel.
Retourne un rapport détaillé (lignes, ajoutés, doublons, erreurs).
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


@dataclass
class ImportReport:
    """Rapport d'import."""
    total_rows: int = 0
    added: int = 0
    duplicates: int = 0
    errors: list = field(default_factory=list)  # [{row: int, message: str, data: dict}]
    detected_columns: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "total_rows": self.total_rows,
            "added": self.added,
            "duplicates": self.duplicates,
            "errors_count": len(self.errors),
            "errors": self.errors[:100],  # limite sécurité
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

        # Extension
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

        # Écriture dans un fichier temporaire
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

        # Limite dure
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
            # Ligne → dict normalisé
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

            normalized = normalize_phone(phone)
            if not normalized:
                report.errors.append({
                    "row": row_number,
                    "message": f"Numéro invalide : {phone}",
                    "data": row_dict,
                })
                continue

            # Doublons (dans la BDD ou dans le fichier)
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
                email = None  # on ignore silencieusement mais on note en warning
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

        # Insertion
        if to_insert:
            db.session.bulk_save_objects(to_insert)
            db.session.commit()
            report.added = len(to_insert)

        return report

    # ==================================================
    # LECTURE FICHIER
    # ==================================================
    @staticmethod
    def _read_dataframe(path: str, ext: str) -> pd.DataFrame | None:
        if ext == "csv":
            # Essais successifs d'encodage + séparateur
            for encoding in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
                for sep in (None, ",", ";", "\t"):
                    try:
                        if sep is None:
                            return pd.read_csv(path, encoding=encoding, sep=None, engine="python")
                        return pd.read_csv(path, encoding=encoding, sep=sep)
                    except Exception:
                        continue
            return None
        # Excel
        return pd.read_excel(path, engine="openpyxl" if ext == "xlsx" else "xlrd")

    # ==================================================
    # DÉTECTION COLONNES
    # ==================================================
    @staticmethod
    def _normalize_header(h: str) -> str:
        h = str(h).strip().lower()
        # retire accents simples
        h = (h.replace("é", "e").replace("è", "e").replace("ê", "e")
               .replace("à", "a").replace("ô", "o").replace("û", "u")
               .replace("ç", "c").replace("î", "i"))
        h = re.sub(r"[\s_\-]+", "_", h)
        return h

    @staticmethod
    def _detect_columns(headers: list[str]) -> dict:
        """
        Retourne {'colonne_originale': 'champ_cible'}.
        Exemple : {'Téléphone': 'phone', 'Prénom': 'first_name'}
        """
        result = {}
        for h in headers:
            norm = ContactImportService._normalize_header(h)
            for target, aliases in COLUMN_ALIASES.items():
                if norm in aliases or norm in {ContactImportService._normalize_header(a) for a in aliases}:
                    result[h] = target
                    break
        return result

    @staticmethod
    def _normalize_row(raw: pd.Series, col_map: dict) -> dict:
        """Convertit une ligne pandas en dict cible."""
        out = {}
        for original, target in col_map.items():
            value = raw.get(original)
            if pd.isna(value):
                value = None
            if value is not None and not isinstance(value, str):
                # Pour les numéros type Excel qui deviennent float
                if isinstance(value, float) and value.is_integer():
                    value = str(int(value))
                else:
                    value = str(value)
            out[target] = value
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