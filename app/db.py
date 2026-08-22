from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = "sqlite:///requirements_quality.db"


class Base(DeclarativeBase):
    pass


def get_engine(database_url: str = DATABASE_URL):
    engine = create_engine(database_url, future=True)

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine
