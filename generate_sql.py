from sqlalchemy.schema import CreateTable
from sqlalchemy import MetaData
from app.models import db  # Import the initialized db instance
from app.models import LoginUser, Role, Tenant, BotPlan, TenantSubscription, Error, SuperAdmin, CustomBot, EmbeddingModel, LLM, KnowledgeBase, SystemEmbeddingModel, SystemLLM

# Specify the output SQL file path
output_file = "schema.sql"

# Create a metadata object
metadata = MetaData()

# Ensure that the app context is active before reflecting the metadata
from run import app  # Ensure the app is imported here for context
with app.app_context():
    metadata.reflect(bind=db.engine)

    # Open the file in write mode
    with open(output_file, "w") as f:
        for table in metadata.sorted_tables:
            # Generate SQL for each table
            create_table_sql = str(CreateTable(table).compile(db.engine))
            f.write(create_table_sql + ";\n\n")

    print(f"SQL schema has been written to {output_file}")
