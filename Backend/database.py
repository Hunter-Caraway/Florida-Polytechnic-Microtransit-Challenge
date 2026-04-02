from sqlmodel import SQLModel, Session, create_engine

#define the database to use
DATABASE_URL = "sqlite:///tracker.db"

#config for database
engine = create_engine(
    DATABASE_URL,
    echo=True,
    connect_args={"check_same_thread": False}
)

#create the table
def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

#create a session
def get_session():
    with Session(engine) as session:
        yield session