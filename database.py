import os
from sqlmodel import SQLModel, Session, create_engine

#define the database to use
DATABASE_URL = os.getenv('DATABASE_URL')

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable not set")

#config for database
engine = create_engine(
    DATABASE_URL,
    echo=True,
    pool_pre_ping=True,
)

#create the table
def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

#create a session
def get_session():
    with Session(engine) as session:
        yield session