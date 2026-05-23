import os
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# PostgreSQL database URL - use environment variable or default
DATABASE_URL = os.getenv(
    'SQLALCHEMY_DATABASE_URI', 
    'postgresql+psycopg2://postgres:123@127.0.0.1:5432/db_botbuilder'
)

# Create the SQLAlchemy engine with connection pooling
engine = create_engine(DATABASE_URL, echo=False, pool_size=10, max_overflow=20, pool_timeout=30)

# Create a sessionmaker factory
Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def db_session():
    """Context manager for database session."""
    session = Session()  # Create a new session
    try:
        yield session  # Yield the session to the calling function
        session.commit()  # Commit the session if no exceptions occur
    except Exception:
        session.rollback()  # Rollback in case of error
        raise  # Re-raise the exception
    finally:
        session.close()  # Close the session after use

# Function to commit a session with error handling
def commit_session(session):
    """Commit a transaction and handle any errors."""
    try:
        session.commit()
        logger.info("Transaction committed successfully.")
    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Error during commit: {e}")
        raise e

# Function to rollback a session with error handling
def rollback_session(session):
    """Rollback a transaction and handle any errors."""
    try:
        session.rollback()
        logger.info("Transaction rolled back successfully.")
    except SQLAlchemyError as e:
        logger.error(f"Error during rollback: {e}")
        raise e

# Function to initialize the database (create tables, etc.)
def init_db():
    """Initialize the database by creating all tables."""
    try:
        # Import your models here to create tables (ensure all models are loaded)
        import app.models  # Ensure models are imported for table creation

        # Check if the database exists and create it if necessary
        with engine.connect() as connection:
            connection.execute(
                text("CREATE DATABASE db_botbuilder")
            )  # PostgreSQL-specific: Cannot use `CREATE DATABASE` in SQLAlchemy directly
        logger.info("Database initialized successfully.")
    except SQLAlchemyError as e:
        logger.error(f"Error during database initialization: {e}")
        raise e

# Example of how to query the database
def test_database_connection():
    """Function to test the database connection."""
    try:
        # Create a new session
        with next(db_session()) as session:
            query = text("SELECT * FROM tbl_loginuser")  # Wrap query with text()
            result = session.execute(query)

            # Fetch and print query results
            for row in result:
                print(row)
            logger.info("Query executed successfully.")
    except SQLAlchemyError as e:
        logger.error(f"Error while connecting to the database: {e}")
