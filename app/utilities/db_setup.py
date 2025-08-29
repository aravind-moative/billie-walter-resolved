import os
import sqlite3


def setup_database():
    # Remove existing database file if it exists
    db_path = "app/databases/myusage.db"
    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"Removed existing database at {db_path}")

    # Connect to SQLite database (creates it if it doesn't exist)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Read and execute the SQL file
    with open("db_setup.sql") as sql_file:
        sql_script = sql_file.read()
        cursor.executescript(sql_script)

    # Commit the changes and close the connection
    conn.commit()
    conn.close()

    print("Database setup completed successfully!")


if __name__ == "__main__":
    setup_database()
