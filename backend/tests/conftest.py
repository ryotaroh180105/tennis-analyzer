import os
import uuid

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://tennis:tennis@localhost:5432/tennis")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("CONFIG_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "config"))
os.environ.setdefault("DEV_AUTO_USER", "true")
os.environ.setdefault("S3_ENDPOINT_URL", "http://localhost:5000")
os.environ.setdefault("S3_ACCESS_KEY", "testing")
os.environ.setdefault("S3_SECRET_KEY", "testing")
os.environ.setdefault("S3_REGION", "us-east-1")
os.environ.setdefault("S3_BUCKET", f"test-{uuid.uuid4().hex[:8]}")


@pytest.fixture(scope="session")
def client():
    """FastAPI TestClient。S3互換エンドポイントは `moto.server` を
    localhost:5000 で起動しておくこと（Makefile/CIで `python -m moto.server -p 5000 &`）。"""
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _clean_db():
    from app.core.db import SessionLocal
    from app.models.match import Match
    from app.models.serve import ServeSession
    from app.models.share import ShareLink
    from app.models.upload import Upload
    from app.models.user import AuthProvider, User

    db = SessionLocal()
    db.query(ShareLink).delete()
    db.query(Match).delete()
    db.query(ServeSession).delete()
    db.query(Upload).delete()
    db.query(AuthProvider).delete()
    db.query(User).delete()
    db.commit()
    db.close()
    yield
