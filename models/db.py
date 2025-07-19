from sqlalchemy import text
from sqlalchemy_utils import create_database, database_exists
from sqlmodel import Session, SQLModel, create_engine

from config import DBConfig
# Import the SQLAlchemy model
from models.entity.entity1 import Base, Entity1

engine = create_engine(
    DBConfig.DB_URL, echo=True, connect_args={"options": "-c search_path=public"}
)
db_session = Session(engine)


def create_db_and_tables():
    if not database_exists(engine.url):
        create_database(engine.url)

    # Create schema if it doesn't exist
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS public"))
        # No need for explicit commit when using 'begin()'

    # Create SQLAlchemy tables
    Base.metadata.create_all(bind=engine)
    
    # Create SQLModel tables
    SQLModel.metadata.create_all(bind=engine)


def get_session():
    try:
        yield db_session
    finally:
        db_session.close()
