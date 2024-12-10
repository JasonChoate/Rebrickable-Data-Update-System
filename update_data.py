#!/usr/bin/env python3
import os
import requests
import gzip
import shutil
import mysql.connector
import logging
from bs4 import BeautifulSoup
from datetime import datetime
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/data_update.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configuration
BASE_URL = "https://rebrickable.com/downloads/"
TEMP_DIR = "temp"
SQL_OUTPUT_DIR = "sql_output"
LOG_DIR = "logs"
REQUIRED_FILES = {
    'sets.csv.gz': 'sets',
    'inventory_sets.csv.gz': 'inventory_sets',
    'inventory_minifigs.csv.gz': 'inventory_minifigs',
    'minifigs.csv.gz': 'minifigs',
    'themes.csv.gz': 'themes',
    'inventories.csv.gz': 'inventories'
}

def setup_directories():
    """Create necessary directories if they don't exist."""
    for directory in [TEMP_DIR, SQL_OUTPUT_DIR, LOG_DIR]:
        os.makedirs(directory, exist_ok=True)

def download_and_extract_files():
    """Download required .gz files and extract them."""
    response = requests.get(BASE_URL)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    for link in soup.find_all('a'):
        filename = link.text.strip()
        if filename in REQUIRED_FILES:
            file_url = link.get('href')
            if not file_url.startswith('http'):
                file_url = f"https://rebrickable.com{file_url}"
            
            # Download .gz file
            gz_path = os.path.join(TEMP_DIR, filename)
            logger.info(f"Downloading {filename}")
            response = requests.get(file_url)
            with open(gz_path, 'wb') as f:
                f.write(response.content)
            
            # Extract .gz file
            csv_path = os.path.join(TEMP_DIR, filename[:-3])  # Remove .gz extension
            with gzip.open(gz_path, 'rb') as f_in:
                with open(csv_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            
            # Clean up .gz file
            os.remove(gz_path)

def execute_sql_files(host, user, password, database):
    """Execute all generated SQL files against the database."""
    try:
        conn = mysql.connector.connect(
            host=host, user=user, password=password, database=database
        )
        cursor = conn.cursor()
        
        # Existing table checks - Add popular_themes check here
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS popular_themes (
                id int NOT NULL AUTO_INCREMENT,
                theme_id int NOT NULL,
                collection_count int NOT NULL,
                snapshot_date timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (id),
                KEY theme_id (theme_id),
                KEY snapshot_date (snapshot_date),
                CONSTRAINT popular_themes_ibfk_1 FOREIGN KEY (theme_id) REFERENCES themes (id)
            )
        """)
        conn.commit()

        # Add recent_set_additions table check
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS recent_set_additions (
                id int NOT NULL AUTO_INCREMENT,
                set_num varchar(20) DEFAULT NULL,
                theme_id int DEFAULT NULL,
                added_date timestamp NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (id),
                KEY set_num (set_num),
                KEY theme_id (theme_id),
                CONSTRAINT recent_set_additions_ibfk_1 FOREIGN KEY (set_num) REFERENCES sets (set_num),
                CONSTRAINT recent_set_additions_ibfk_2 FOREIGN KEY (theme_id) REFERENCES themes (id)
            )
        """)
        conn.commit()
        
        # Create temporary table for existing sets (existing code)
        cursor.execute("CREATE TEMPORARY TABLE existing_sets AS SELECT set_num FROM sets")
        conn.commit()
        
        # Execute files in order (existing code)
        order = ['themes', 'sets', 'minifigs', 'inventories', 'inventory_minifigs', 'inventory_sets']
        
        for table in order:
            file = f"{table}_inserts.sql"
            if file in os.listdir(SQL_OUTPUT_DIR):
                file_path = os.path.join(SQL_OUTPUT_DIR, file)
                logger.info(f"Executing SQL file: {file}")
                
                with open(file_path, 'r', encoding='utf-8') as f:
                    sql_commands = f.read().split(';')
                    
                    for command in sql_commands:
                        if command.strip():
                            try:
                                cursor.execute(command)
                                conn.commit()
                            except mysql.connector.Error as err:
                                logger.error(f"Error executing SQL: {err}")
                                continue
        
        # Update recent_set_additions
        cursor.execute("""
            DELETE r FROM recent_set_additions r
            WHERE EXISTS (
                SELECT 1 FROM sets s
                LEFT JOIN existing_sets e ON s.set_num = e.set_num
                WHERE e.set_num IS NULL
                AND s.theme_id = r.theme_id
            )
        """)
        conn.commit()
        
        cursor.execute("""
            INSERT INTO recent_set_additions (set_num, theme_id)
            SELECT s.set_num, s.theme_id
            FROM sets s
            LEFT JOIN existing_sets e ON s.set_num = e.set_num
            WHERE e.set_num IS NULL
            AND (
                SELECT COUNT(*)
                FROM recent_set_additions r2
                WHERE r2.theme_id = s.theme_id
            ) < 3
            ORDER BY s.year DESC, s.set_num DESC
        """)
        conn.commit()
        
        # Update popular themes
        logger.info("Updating popular themes statistics")
        try:
            cursor.execute("""
                INSERT INTO popular_themes (theme_id, collection_count)
                SELECT 
                    t.id AS theme_id,
                    SUM(c.collection_set_quantity) AS collection_count
                FROM themes t
                JOIN sets s ON s.theme_id = t.id
                JOIN collection c ON c.set_num = s.set_num
                GROUP BY t.id
                ORDER BY collection_count DESC
                LIMIT 5
            """)
            conn.commit()
            
            # Clean up old records
            cursor.execute("""
                DELETE FROM popular_themes 
                WHERE snapshot_date < DATE_SUB(NOW(), INTERVAL 12 WEEK)
            """)
            conn.commit()
            
        except mysql.connector.Error as err:
            logger.error(f"Error updating popular themes: {err}")
        
        cursor.execute("DROP TEMPORARY TABLE existing_sets")
        conn.commit()
        
        return cursor, conn
        
    except mysql.connector.Error as err:
        logger.error(f"Database connection error: {err}")
        raise

def cleanup():
    """Clean up temporary files."""
    logger.info("Cleaning up temporary files")
    for file in os.listdir(TEMP_DIR):
        if file != '.gitkeep':  # Skip .gitkeep files
            os.remove(os.path.join(TEMP_DIR, file))

def main():
    try:
        # Load environment variables
        load_dotenv('.env')
        
        # Get database credentials from environment
        db_host = os.getenv('SQL_DB_HOST')  # Using the service name from docker-compose
        db_user = os.getenv('SQL_DB_USER')
        db_pass = os.getenv('SQL_DB_PASS')
        db_name = os.getenv('SQL_DB_NAME') # Database name
        
        # Create necessary directories
        setup_directories()
        
        # Download and extract files
        download_and_extract_files()
        
        # Generate SQL insert statements using your existing script
        os.system(f'python3 generate_sql_insert.py')
        
        # Execute SQL files
        cursor, conn = execute_sql_files(db_host, db_user, db_pass, db_name)
        conn.close()
        
        # Cleanup
        cleanup()
        
        logger.info("Data update completed successfully")
        
    except Exception as e:
        logger.error(f"Error in main process: {e}")
        raise

if __name__ == "__main__":
    main()