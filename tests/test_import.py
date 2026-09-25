"""
Tests d'import CSV/Excel.
"""
import io
import pytest
from app.models.contact import Contact


class TestImportCSV:
    def _make_csv(self, content: str):
        return content.encode("utf-8")

    def test_import_csv_success(self, logged_client, business, db):
        content = (
            "prenom,nom,phone,email\n"
            "Alice,Martin,+33611111111,alice@test.com\n"
            "Bob,Durand,+33622222222,bob@test.com\n"
        )
        data = {
            "file": (io.BytesIO(self._make_csv(content)), "contacts.csv"),
        }
        resp = logged_client.post(
            "/contacts/import",
            data=data,
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert Contact.query.count() == 2

    def test_import_csv_with_duplicates(self, logged_client, business, contact, db):
        content = (
            "prenom,nom,phone\n"
            f"Test,Dup,{contact.phone}\n"
            "New,User,+33633333333\n"
        )
        data = {"file": (io.BytesIO(self._make_csv(content)), "contacts.csv")}
        logged_client.post("/contacts/import", data=data,
                           content_type="multipart/form-data",
                           follow_redirects=True)
        assert Contact.query.count() == 2

    def test_import_csv_invalid_phones(self, logged_client, business, db):
        content = (
            "prenom,nom,phone\n"
            "Bad,Phone,abc\n"
            "Good,Phone,+33644444444\n"
        )
        data = {"file": (io.BytesIO(self._make_csv(content)), "contacts.csv")}
        logged_client.post("/contacts/import", data=data,
                           content_type="multipart/form-data",
                           follow_redirects=True)
        assert Contact.query.count() == 1

    def test_import_csv_missing_phone_column(self, logged_client, business):
        content = "prenom,nom\nAlice,Martin\n"
        data = {"file": (io.BytesIO(self._make_csv(content)), "contacts.csv")}
        resp = logged_client.post("/contacts/import", data=data,
                                   content_type="multipart/form-data",
                                   follow_redirects=True)
        assert resp.status_code == 200
        assert Contact.query.count() == 0

    def test_import_csv_detects_french_headers(self, logged_client, business, db):
        content = (
            "Prénom,Nom,Téléphone,Email\n"
            "Marie,Curie,+33655555555,marie@test.com\n"
        )
        data = {"file": (io.BytesIO(self._make_csv(content)), "contacts.csv")}
        logged_client.post("/contacts/import", data=data,
                           content_type="multipart/form-data",
                           follow_redirects=True)
        c = Contact.query.first()
        assert c is not None
        assert c.first_name == "Marie"

    def test_import_unsupported_extension(self, logged_client, business):
        data = {"file": (io.BytesIO(b"some content"), "file.txt")}
        resp = logged_client.post("/contacts/import", data=data,
                                   content_type="multipart/form-data",
                                   follow_redirects=True)
        assert Contact.query.count() == 0


class TestColumnDetection:
    def test_detect_columns(self):
        from app.services.contact_import_service import ContactImportService
        mapping = ContactImportService._detect_columns(
            ["Prénom", "Nom", "Téléphone", "Email", "Société"]
        )
        assert mapping["Prénom"] == "first_name"
        assert mapping["Nom"] == "last_name"
        assert mapping["Téléphone"] == "phone"
        assert mapping["Email"] == "email"
        assert mapping["Société"] == "company"

    def test_normalize_header(self):
        from app.services.contact_import_service import ContactImportService
        assert ContactImportService._normalize_header("Téléphone") == "telephone"
        assert ContactImportService._normalize_header("First-Name") == "first_name"


# ==================================================
# TEST DE DIAGNOSTIC (à supprimer plus tard)
# ==================================================
def test_import_debug(logged_client, business, db):
    """Diagnostic pour comprendre l'échec d'import."""
    r = logged_client.get("/contacts/", follow_redirects=False)
    print(f"\n🔍 GET /contacts/ → {r.status_code}")

    with logged_client.session_transaction() as sess:
        print(f"🔍 active_business_id dans session = {sess.get('active_business_id')}")

    print(f"🔍 business.id = {business.id}")
    print(f"🔍 business.name = {business.name}")
    print(f"🔍 business.plan = {business.plan}")

    content = "prenom,nom,phone\nTest,User,+33611111111\n"
    data = {"file": (io.BytesIO(content.encode("utf-8")), "test.csv")}
    resp = logged_client.post(
        "/contacts/import",
        data=data,
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    print(f"🔍 POST /contacts/import → {resp.status_code}")
    print(f"🔍 Location: {resp.headers.get('Location')}")

    assert resp.status_code == 200
    
    def test_import_debug_detail(logged_client, business, db):
    """Diagnostic détaillé : voir le rapport d'import."""
    import io
    from app.models.contact import Contact
    from app.services.contact_import_service import ContactImportService

    # Créer un fichier
    content = (
        "prenom,nom,phone\n"
        "Alice,Martin,+33611111111\n"
        "Bob,Durand,+33622222222\n"
    )
    data = {"file": (io.BytesIO(content.encode("utf-8")), "contacts.csv")}

    # Simuler un upload
    from werkzeug.datastructures import FileStorage
    file_storage = FileStorage(
        stream=io.BytesIO(content.encode("utf-8")),
        filename="contacts.csv",
        content_type="text/csv",
    )

    # Appeler directement le service
    report = ContactImportService.import_file(file_storage, business)

    print(f"\n🔍 RAPPORT D'IMPORT :")
    print(f"🔍   total_rows = {report.total_rows}")
    print(f"🔍   added = {report.added}")
    print(f"🔍   duplicates = {report.duplicates}")
    print(f"🔍   errors_count = {len(report.errors)}")
    print(f"🔍   detected_columns = {report.detected_columns}")
    for err in report.errors[:5]:
        print(f"🔍   ERROR: ligne {err.get('row')} → {err.get('message')}")

    print(f"\n🔍 Contacts en base = {Contact.query.count()}")

    assert report.added == 2, f"Attendu 2, obtenu {report.added}. Errors: {report.errors}"