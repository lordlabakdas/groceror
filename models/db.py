from sqlmodel import Session, SQLModel, create_engine

from config import DBConfig

engine = create_engine(DBConfig.DB_URL, echo=True)
db_session = Session(engine)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)
