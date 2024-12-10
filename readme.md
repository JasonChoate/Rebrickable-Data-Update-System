# Rebrickable Data Update System

Automated system to fetch and import LEGO database updates from Rebrickable.com into a MySQL database. Downloads CSV files, converts them to SQL statements, and imports while maintaining referential integrity.

## Directory Structure
```
/srv/maintenance/
├── docker-compose.yml    # Container configuration
├── Dockerfile           # Python environment setup
├── update_data.py       # Main orchestration script  
├── generate_sql_insert.py # CSV to SQL conversion
├── requirements.txt     # Python dependencies
├── .env                # Database credentials
└── directories:
    ├── temp/          # Temporary CSV storage
    ├── sql_output/    # Generated SQL files
    └── logs/          # Operation logs
```

## Database Schema
Most tables follow Rebrickable's schema as defined in their CSV files. However, this system adds two custom tables:

### recent_set_additions
Tracks newly added sets per theme (automatically created if not present)
```sql
CREATE TABLE recent_set_additions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    set_num VARCHAR(20),
    theme_id INT,
    added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    KEY set_num (set_num),
    KEY theme_id (theme_id),
    FOREIGN KEY (set_num) REFERENCES sets(set_num),
    FOREIGN KEY (theme_id) REFERENCES themes(id)
)
```
Stores up to 3 most recent sets per theme. Records persist until new sets are available for that theme.

### popular_themes
Tracks theme popularity based on collection counts (automatically created if not present)
```sql
CREATE TABLE popular_themes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    theme_id INT NOT NULL,
    collection_count INT NOT NULL,
    snapshot_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY theme_id (theme_id),
    KEY snapshot_date (snapshot_date),
    FOREIGN KEY (theme_id) REFERENCES themes(id)
)
```
Stores the top 5 most collected themes, updated weekly. Records older than 12 weeks are automatically purged.

For Rebrickable's schema documentation, visit: https://rebrickable.com/downloads/

## Setup

1. Create the maintenance directory:
```bash
mkdir -p /srv/maintenance/{temp,sql_output,logs}
```

2. Copy the required files into `/srv/maintenance/`:
- docker-compose.yml
- Dockerfile
- update_data.py
- generate_sql_insert.py
- requirements.txt

3. Create `.env` file with database credentials:
```
SQL_DB_HOST='your_db_host'
SQL_DB_USER='your_username'
SQL_DB_PASS='your_password'
SQL_DB_NAME='rebrickable_db'
```

4. Set up cron job for weekly updates:
```bash
sudo nano /etc/cron.weekly/update-brick-data
```

Add:
```bash
#!/bin/bash
cd /srv/maintenance && docker-compose run --rm maintenance
```

Make executable:
```bash
sudo chmod +x /etc/cron.weekly/update-brick-data
```

## Components

### Docker Configuration
The system runs in a Docker container configured via docker-compose.yml:
- Uses Python 3.9 base image
- Installs required dependencies from requirements.txt
- Networks with existing MySQL database container
- Runs on-demand rather than continuously

### Scripts
**update_data.py**
- Downloads and extracts CSV files from Rebrickable
- Orchestrates the update process
- Manages logging and cleanup
- Creates required tables if they don't exist
- Updates popular themes statistics
- Tracks new set additions

**generate_sql_insert.py**
- Converts CSV data to SQL insert statements
- Handles duplicate records
- Maintains referential integrity

### Data Flow
1. Downloads compressed CSV files from Rebrickable
2. Extracts to temporary directory
3. Converts to SQL insert statements
4. Executes SQL in correct order:
   - themes
   - sets
   - minifigs
   - inventories
   - inventory_minifigs
   - inventory_sets
5. Updates custom tracking tables:
   - recent_set_additions
   - popular_themes

### Error Handling
- Continues processing on foreign key violations
- Maintains database referential integrity
- Logs all operations to `logs/data_update.log`

## Manual Execution
```bash
cd /srv/maintenance
docker-compose run --rm maintenance
```

## Dependencies
- Python 3.9
- MySQL 8.0
- Python packages:
  - pandas
  - requests
  - beautifulsoup4
  - mysql-connector-python
  - python-dotenv