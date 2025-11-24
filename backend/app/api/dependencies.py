from typing import Generator
from app.core.database import SessionLocal


def get_db() -> Generator:
    """
    Dependency function to get database session.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

