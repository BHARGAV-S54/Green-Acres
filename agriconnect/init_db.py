import os
import mysql.connector

# Database setup configurations
DB_CONFIG = {
    'host':     '127.0.0.1',
    'user':     'root',
    'password': 'root',
    'charset':  'utf8mb4'
}

def init_db():
    try:
        # Connect to MySQL server (without specifying DB, as it might not exist yet)
        print("[*] Connecting to MySQL server...")
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # Read the schema.sql file
        schema_path = os.path.join(os.path.dirname(__file__), 'schema.sql')
        if not os.path.exists(schema_path):
            print(f"[!] Cannot find {schema_path}")
            return
            
        print(f"[*] Reading {schema_path}...")
        with open(schema_path, 'r', encoding='utf-8') as f:
            sql_statements = f.read()

        # Execute multiple statements
        print("[*] Executing schema queries...")
        # MySQL Connector executes multiple queries iteratively when multi=True
        for result in cursor.execute(sql_statements, multi=True):
            if result.with_rows:
                result.fetchall()
                
        # Commit any changes
        conn.commit()
        print("[+] Real-time Database 'agriconnect_db' successfully created and seeded!")
        
    except mysql.connector.Error as err:
        print(f"[!] Database Error: {err}")
        print("Please ensure MySQL is running (e.g., via XAMPP) and root has no password by default.")
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()
            print("[*] MySQL connection closed.")

if __name__ == '__main__':
    init_db()
