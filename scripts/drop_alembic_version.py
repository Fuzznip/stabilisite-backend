import os
import logging
from sqlalchemy import create_engine, text

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database connection URL
DATABASE_URL = "postgresql://{}:{}@{}".format(
    os.getenv('DATABASE_USERNAME'),
    os.getenv('DATABASE_PASSWORD'),
    os.getenv('DATABASE_URL')
)

def drop_alembic_version_table():
    try:
        # Create database engine
        engine = create_engine(DATABASE_URL)
        with engine.connect() as connection:
            logger.info("Dropping table 'alembic_version'...")
            connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
            connection.commit()
            logger.info("Table 'alembic_version' dropped successfully.")

            # Verify the table has been dropped
            result = connection.execute(
                text("SELECT to_regclass('public.alembic_version')")
            ).scalar()
            if result is None:
                logger.info("Verification successful: 'alembic_version' table does not exist.")
            else:
                logger.warning("Verification failed: 'alembic_version' table still exists.")
    except Exception as e:
        logger.error(f"Error dropping table 'alembic_version': {e}")
    finally:
        engine.dispose()

if __name__ == "__main__":
    drop_alembic_version_table()
