from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError

def test_database_connection():
    # Database URL
    DATABASE_URL = "mysql+pymysql://root:ZAQ!xsw2CDE#@127.0.0.1:3306/db_botbuilder"
    
    try:
        # Create database engine
        engine = create_engine(DATABASE_URL)
        
        # Create sessionmaker
        Session = sessionmaker(bind=engine)
        session = Session()
        
        # Optional: Execute a test query
        query = text("SELECT * FROM tbl_loginuser")  # Wrap query with text()
        result = session.execute(query)
        
        # Fetch and print query results
        for row in result:
            print(row)
        
        # Commit any transactions if needed (optional for SELECT queries)
        session.commit()
        
        # Close the session
        session.close()
        print("Database connection closed.")

    except SQLAlchemyError as e:
        print("Error while connecting to the database:", str(e))

# Run the test function
test_database_connection()
