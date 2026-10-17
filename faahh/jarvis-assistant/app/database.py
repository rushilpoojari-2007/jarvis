from collections.abc import Generator
from threading import Lock

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(settings.DATABASE_URL, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
_db_initialized = False
_db_init_lock = Lock()


def init_db() -> None:
    global _db_initialized
    with _db_init_lock:
        if _db_initialized:
            return
        import importlib

        importlib.import_module("app.models")
        Base.metadata.create_all(bind=engine)

        # Keep existing SQLite chat records and put them into one selectable thread.
        if settings.DATABASE_URL.startswith("sqlite"):
            with engine.begin() as connection:
                columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(chat_messages)").all()}
                if "conversation_id" not in columns:
                    connection.exec_driver_sql(
                        "ALTER TABLE chat_messages ADD COLUMN conversation_id INTEGER REFERENCES conversations(id)"
                    )

                unassigned = connection.exec_driver_sql(
                    "SELECT COUNT(*) FROM chat_messages WHERE conversation_id IS NULL"
                ).scalar_one()
                if unassigned:
                    result = connection.exec_driver_sql(
                        "INSERT INTO conversations (title, created_at, updated_at) "
                        "VALUES ('Previous chat', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                    )
                    connection.exec_driver_sql(
                        "UPDATE chat_messages SET conversation_id = ? WHERE conversation_id IS NULL",
                        (result.lastrowid,),
                    )
        _db_initialized = True


def get_db() -> Generator:
    init_db()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
