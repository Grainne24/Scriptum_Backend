'''
    This file establishes the connection to PostgreSQL
'''

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv
import os

#Loads environment variables from env. 
load_dotenv()

#Gets database url
DATABASE_URL = os.getenv("DATABASE_URL")

#Creates an engine and manages connection pool to database
engine = create_engine(DATABASE_URL)

#Creates session - which stores the database operations
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

#Base class for models 
Base = declarative_base()

#This creates a new session for each case
def get_db():
    db = SessionLocal()
    try:
        yield db #This gives the session to the route
    finally:
        db.close()