import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

def verify():
    try:
        conn = mysql.connector.connect(
            host=os.getenv("MYSQL_HOST"),
            user=os.getenv("MYSQL_USER"),
            password=os.getenv("MYSQL_PASSWORD"),
            database=os.getenv("MYSQL_DATABASE") or "defaultdb",
            port=int(os.getenv("MYSQL_PORT", 26614)),
            use_pure=True,
            ssl_disabled=False
        )
        cur = conn.cursor()
        
        print("--- Aiven Tables Verification ---")
        cur.execute("SHOW TABLES")
        tables = [t[0] for t in cur.fetchall()]
        print(f"Total Tables Found: {len(tables)}")
        for t in tables:
            cur.execute(f"SELECT COUNT(*) FROM {t}")
            count = cur.fetchone()[0]
            print(f" - {t:15} | Row Count: {count}")
        
        print("-------------------------------")
        if 'users' in tables:
            print("✅ Verification Successful! Your database is fully set up.")
        else:
            print("❌ Warning: 'users' table not found. Something went wrong.")
            
        conn.close()
    except Exception as e:
        print(f"❌ Verification Failed: {e}")

if __name__ == "__main__":
    verify()
