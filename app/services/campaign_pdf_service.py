"""
LionFlow AI — Service de génération PDF pour les campagnes.
Utilise xhtml2pdf (pur Python, compatible Windows sans GTK).
"""
from __future__ import annotations

import io
from datetime import datetime

from flask import render_template
from xhtml2pdf import pisa

from app.models.campaign import Campaign


class CampaignPdfService:

    @staticmethod
    def generate_pdf(campaign: Campaign) -> bytes:
        """
        Génère le PDF d'une campagne et retourne les bytes.
        Lève une exception si la génération échoue.
        """
        # 1. Rendre le template HTML avec les données de la campagne
        html_string = render_template(
            "campaigns/pdf_report.html",
            campaign=campaign,
            business=campaign.business,
            now=datetime.utcnow(),
        )

        # 2. Convertir le HTML en PDF
        result = io.BytesIO()
        pdf = pisa.CreatePDF(
            io.BytesIO(html_string.encode("utf-8")),
            dest=result,
            encoding="utf-8",
        )

        # 3. Vérifier les erreurs
        if pdf.err:
            raise RuntimeError(f"Erreur génération PDF (code {pdf.err})")

        return result.getvalue()