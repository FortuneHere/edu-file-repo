import io
import os

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ["DATABASE_URL"] = "sqlite:///./test_backend_e2e.db"

import main as main_module
from database import get_db
from models import Base, User


class FakeS3Service:
    def __init__(self):
        self.uploaded_keys = []

    def upload_file(self, file_obj, object_name):
        payload = file_obj.read()
        if not payload.startswith(b"%PDF"):
            raise AssertionError("Expected PDF payload in smoke test")
        self.uploaded_keys.append(object_name)
        file_obj.seek(0)
        return True

    def generate_presigned_url(self, object_name, expires_in=3600, download_filename=None):
        return (
            "https://fake-storage.local/"
            f"{object_name}?expires_in={expires_in}&filename={download_filename}"
        )


def _make_auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_backend_full_smoke_scenario(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()

    def override_get_db():
        try:
            yield session
        finally:
            pass

    main_module.app.dependency_overrides[get_db] = override_get_db
    fake_s3 = FakeS3Service()
    monkeypatch.setattr(main_module, "s3_service", fake_s3)
    monkeypatch.setattr(main_module, "s3_init_error", None)

    client = TestClient(main_module.app)

    try:
        # 1) Register regular user.
        register_email = "smoke-user@example.com"
        register_password = "StrongPass123!"
        register_response = client.post(
            "/register",
            json={"email": register_email, "password": register_password},
        )
        assert register_response.status_code == 201

        # 2) Login as regular user and verify restricted upload access.
        user_token_response = client.post(
            "/token",
            json={"email": register_email, "password": register_password},
        )
        assert user_token_response.status_code == 200
        user_token = user_token_response.json()["access_token"]

        denied_upload_response = client.post(
            "/upload",
            headers=_make_auth_header(user_token),
            data={"folder": "root"},
            files={"file": ("denied.pdf", io.BytesIO(b"%PDF-1.4 denied"), "application/pdf")},
        )
        assert denied_upload_response.status_code == 403

        # 3) Promote the user to admin and login again.
        user_record = session.query(User).filter(User.email == register_email).first()
        assert user_record is not None
        user_record.role = "admin"
        session.commit()

        admin_token_response = client.post(
            "/token",
            json={"email": register_email, "password": register_password},
        )
        assert admin_token_response.status_code == 200
        admin_token = admin_token_response.json()["access_token"]

        # 4) Upload PDF as admin.
        upload_response = client.post(
            "/upload",
            headers=_make_auth_header(admin_token),
            data={"folder": "root"},
            files={"file": ("smoke.pdf", io.BytesIO(b"%PDF-1.4 smoke"), "application/pdf")},
        )
        assert upload_response.status_code == 200
        upload_payload = upload_response.json()
        assert upload_payload["s3_key"] == "root/smoke.pdf"
        assert fake_s3.uploaded_keys == ["root/smoke.pdf"]

        # 5) List files.
        files_response = client.get("/files", params={"folder": "root"})
        assert files_response.status_code == 200
        files_payload = files_response.json()
        assert len(files_payload) == 1
        assert files_payload[0]["s3_key"] == "root/smoke.pdf"

        # 6) Request presigned download link (auth required).
        download_link_response = client.get(
            "/files/download-link",
            params={"s3_key": "root/smoke.pdf", "expires_in": 1200},
            headers=_make_auth_header(admin_token),
        )
        assert download_link_response.status_code == 200
        link_payload = download_link_response.json()
        assert link_payload["filename"] == "smoke.pdf"
        assert link_payload["expires_in"] == 1200
        assert link_payload["download_url"].startswith("https://fake-storage.local/root/smoke.pdf")
    finally:
        main_module.app.dependency_overrides.clear()
        session.close()
        Base.metadata.drop_all(bind=engine)
