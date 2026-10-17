import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture(autouse=True)
def disable_live_credentials(monkeypatch):
    """Tests never use credentials from the developer's local .env file."""
    from app.config import settings

    for name in (
        "NVIDIA_API_KEY",
        "NVIDIA_API_KEYS",
        "NVIDIA_VISION_API_KEY",
        "NEWS_API_KEY",
        "GNEWS_API_KEY",
        "GUARDIAN_API_KEY",
    ):
        monkeypatch.setattr(settings, name, () if name == "NVIDIA_API_KEYS" else "")


@pytest.fixture
def client(monkeypatch):
    """Use an in-memory database; never open or alter the user's jarvis.db."""
    from importlib import import_module

    from app.database import Base, get_db
    main = import_module("app.main")
    application = main.app
    import app.models  # noqa: F401

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    test_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(main, "engine", engine)

    def override_get_db():
        db = test_session()
        try:
            yield db
        finally:
            db.close()

    application.dependency_overrides[get_db] = override_get_db
    try:
        # No context manager means the real application lifespan (and its
        # production database initialization) is not started for route tests.
        yield TestClient(application)
    finally:
        application.dependency_overrides.pop(get_db, None)
        engine.dispose()
