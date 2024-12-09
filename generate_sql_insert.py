import pandas as pd
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def escape_string(s):
    if pd.isna(s):
        return 'NULL'
    return f"'{str(s).replace(chr(39), chr(39)+chr(39))}'"

def create_insert_statements(csv_path: str, table_name: str) -> None:
    try:
        df = pd.read_csv(csv_path)
        output_file = os.path.join('sql_output', f'{table_name}_inserts.sql')
        
        with open(output_file, 'w', encoding='utf-8') as f:
            unique_constraints = {
                'sets': ['set_num'],
                'inventory_sets': ['inventory_id', 'set_num'],
                'inventory_minifigs': ['inventory_id', 'fig_num'],
                'inventories': ['id', 'set_num'],
                'themes': ['id'],
                'minifigs': ['fig_num']
            }
            
            for _, row in df.iterrows():
                values = [str(val) if pd.notna(val) else 'NULL' for val in row]
                values = [escape_string(val) if val != 'NULL' else val for val in values]
                values_str = ', '.join(values)
                
                exists_conditions = []
                for field in unique_constraints[table_name]:
                    exists_conditions.append(f"{field} = {values[df.columns.get_loc(field)]}")
                exists_condition = ' OR '.join(exists_conditions)
                
                columns = ', '.join(df.columns)
                insert_statement = (
                    f"INSERT INTO {table_name} ({columns})\n"
                    f"SELECT {values_str}\n"
                    f"WHERE NOT EXISTS (\n"
                    f"    SELECT 1 FROM {table_name}\n"
                    f"    WHERE {exists_condition}\n"
                    f");\n"
                )
                f.write(insert_statement)
                
    except Exception as e:
        logger.error(f"Error processing {csv_path}: {str(e)}")

def main():
    file_mapping = {
        'temp/sets.csv': 'sets',
        'temp/inventory_sets.csv': 'inventory_sets',
        'temp/inventory_minifigs.csv': 'inventory_minifigs',
        'temp/minifigs.csv': 'minifigs',
        'temp/themes.csv': 'themes',
        'temp/inventories.csv': 'inventories'
    }
    
    os.makedirs('sql_output', exist_ok=True)
    
    for csv_file, table_name in file_mapping.items():
        if os.path.exists(csv_file):
            create_insert_statements(csv_file, table_name)
        else:
            logger.warning(f"File not found: {csv_file}")

if __name__ == "__main__":
    main()