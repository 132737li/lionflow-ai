"""
Script de test : simule un message WhatsApp entrant.
Usage : python test_chatbot.py
"""
from app import create_app
from app.extensions import db
from app.models.business import Business
from app.models.contact import Contact
from app.services.chatbot_service import ChatbotService

app = create_app("development")

with app.app_context():
    # 1. Récupérer la première entreprise
    business = Business.query.first()
    if not business:
        print("❌ Aucune entreprise trouvée. Lance 'flask seed-demo' d'abord.")
        exit(1)

    print(f"✅ Entreprise : {business.name}")

    # 2. Récupérer ou créer un contact de test
    contact = Contact.query.filter_by(business_id=business.id).first()
    if not contact:
        contact = Contact(
            business_id=business.id,
            first_name="Test",
            last_name="Client",
            phone="+25779123456",
            status="active",
        )
        db.session.add(contact)
        db.session.commit()
        print(f"✅ Contact créé : {contact.full_name}")
    else:
        print(f"✅ Contact trouvé : {contact.full_name}")

    # 3. Simuler plusieurs messages
    test_messages = [
        "Bonjour",
        "Salut, je voudrais connaître vos horaires",
        "Quels sont vos prix ?",
        "Je veux parler à un agent",
    ]

    print("\n" + "=" * 60)
    print("SIMULATION DE MESSAGES ENTRANTS")
    print("=" * 60)

    for msg in test_messages:
        print(f"\n📨 Message client : « {msg} »")
        result = ChatbotService.process_incoming_message(
            business=business,
            contact=contact,
            message_text=msg,
            sender_phone=contact.phone,
        )
        print(f"   → Action  : {result['action']}")
        print(f"   → Réponse : {(result.get('response') or '')[:120]}...")
        print(f"   → Conv. # : {result['conversation_id']}")

    print("\n" + "=" * 60)
    print("✅ Simulation terminée")
    print("=" * 60)