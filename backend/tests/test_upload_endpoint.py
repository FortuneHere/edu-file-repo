import io
import os
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ["DATABASE_URL"] = "sqlite:///./test_backend.db"

import main as main_module
from auth import get_current_user
from database import get_db
from models import Base, User
from s3_service import S3UploadError


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    session = TestingSessionLocal()
    session.add(
        User(
            email="admin@example.com",
            hashed_password="hashed",
            role="admin",
        )
    )
    session.commit()

    def override_get_db():
        try:
            yield session
        finally:
            pass

    def override_get_current_user():
        return SimpleNamespace(id=1, email="admin@example.com", role="admin")

    main_module.app.dependency_overrides[get_db] = override_get_db
    main_module.app.dependency_overrides[get_current_user] = override_get_current_user

    test_client = TestClient(main_module.app)
    yield test_client

    main_module.app.dependency_overrides.clear()
    session.close()
    Base.metadata.drop_all(bind=engine)


def test_upload_pdf_success(client, monkeypatch):
    uploaded = {}

    class FakeS3Service:
        def upload_file(self, file_obj, object_name):
            uploaded["object_name"] = object_name
            uploaded["payload"] = file_obj.read()
            file_obj.seek(0)
            return True

    monkeypatch.setattr(main_module, "s3_service", FakeS3Service())
    monkeypatch.setattr(main_module, "s3_init_error", None)

    response = client.post(
        "/upload",
        data={"folder": "root"},
        files={"file": ("test.pdf", io.BytesIO(b"%PDF-1.4 sample"), "application/pdf")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["filename"] == "test.pdf"
    assert body["s3_key"] == "root/test.pdf"
    assert uploaded["object_name"] == "root/test.pdf"
    assert uploaded["payload"].startswith(b"%PDF")


def test_upload_rejects_non_pdf(client, monkeypatch):
    class FakeS3Service:
        def upload_file(self, file_obj, object_name):
            raise AssertionError("S3 upload should not be called for non-PDF files")

    monkeypatch.setattr(main_module, "s3_service", FakeS3Service())
    monkeypatch.setattr(main_module, "s3_init_error", None)

    response = client.post(
        "/upload",
        data={"folder": "root"},
        files={"file": ("notes.txt", io.BytesIO(b"not a pdf"), "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Разрешены только PDF файлы"


def test_upload_handles_s3_error(client, monkeypatch):
    class BrokenS3Service:
        def upload_file(self, file_obj, object_name):
            raise S3UploadError("storage unavailable")

    monkeypatch.setattr(main_module, "s3_service", BrokenS3Service())
    monkeypatch.setattr(main_module, "s3_init_error", None)

    response = client.post(
        "/upload",
        data={"folder": "root"},
        files={"file": ("broken.pdf", io.BytesIO(b"%PDF-1.4 broken"), "application/pdf")},
    )

    assert response.status_code == 502
    assert "Ошибка S3" in response.json()["detail"]
