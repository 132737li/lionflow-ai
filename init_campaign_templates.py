"""
Script d'initialisation des templates de campagnes globaux.
Usage : python init_campaign_templates.py
"""
from app import create_app
from app.services.campaign_template_service import CampaignTemplateService

app = create_app("development")

with app.app_context():
    created = CampaignTemplateService.ensure_global_templates()
    print(f"Templates globaux créés : {created}")

    from app.models.campaign_template import CampaignTemplate
    total = CampaignTemplate.query.filter_by(business_id=None).count()
    print(f"Total de templates globaux en base : {total}")