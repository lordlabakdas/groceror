from sqlalchemy_utils import create_database, database_exists
from sqlmodel import Session, SQLModel, create_engine

from config import DBConfig

engine = create_engine(DBConfig.DB_URL, echo=True)
db_session = Session(engine)


def create_db_and_tables():
    if not database_exists(engine.url):
        create_database(engine.url)
    # SQLModel.metadata.clear()
    SQLModel.metadata.create_all(bind=engine)
