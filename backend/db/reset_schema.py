from database import engine
from models import Base

def reset_schema():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

if __name__ == "__main__":
    reset_schema()
    print("Schema reseteado correctamente")
