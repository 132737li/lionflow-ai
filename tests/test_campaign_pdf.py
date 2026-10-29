"""
Tests de l'export PDF des campagnes.
"""
import io
from unittest.mock import patch

import pytest

from app.models.campaign import Campaign


@pytest.fixture
def campaign_for_pdf(db, business, user):
    c = Campaign(
        business_id=business.id,
        name="Campagne PDF Test",
        status="completed",
        total_contacts=100,
        sent_count=90,
        delivered_count=85,
        read_count=50,
        failed_count=10,
    )
    db.session.add(c)
    db.session.commit()
    return c


def test_export_pdf_requires_login(client, campaign_for_pdf):
    resp = client.get(f"/campaigns/{campaign_for_pdf.id}/export/pdf")
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers.get("Location", "")


def test_export_pdf_success(logged_client, campaign_for_pdf):
    # On mocke pisa.CreatePDF pour ne pas générer un vrai PDF (trop lourd)
    with patch("app.services.campaign_pdf_service.pisa.CreatePDF") as mock_pdf:
        # On simule un succès (err=0)
        mock_pdf.return_value.err = 0
        
        resp = logged_client.get(f"/campaigns/{campaign_for_pdf.id}/export/pdf")
        
        assert resp.status_code == 200
        assert resp.mimetype == "application/pdf"
        assert "attachment" in resp.headers.get("Content-Disposition", "")
        assert f"campagne_{campaign_for_pdf.id}" in resp.headers.get("Content-Disposition", "")


def test_export_pdf_cross_tenant_forbidden(logged_client, db, other_business):
    from app.models.campaign import Campaign
    foreign = Campaign(business_id=other_business.id, name="Foreign", status="draft")
    db.session.add(foreign)
    db.session.commit()

    resp = logged_client.get(f"/campaigns/{foreign.id}/export/pdf")
    assert resp.status_code == 404


def test_export_pdf_handles_error(logged_client, campaign_for_pdf):
    with patch("app.services.campaign_pdf_service.pisa.CreatePDF") as mock_pdf:
        # On simule une erreur de génération (err=1)
        mock_pdf.return_value.err = 1
        
        resp = logged_client.get(f"/campaigns/{campaign_for_pdf.id}/export/pdf", follow_redirects=True)
        
        # Doit rediriger vers le détail avec un message d'erreur
        assert resp.status_code == 200
        assert b"Impossible de g&#39;n&#39;rer le PDF" in resp.data or b"Impossible de g" in resp.data