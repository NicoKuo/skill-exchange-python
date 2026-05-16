import os
import sqlite3

DB_PATH = os.environ.get("DB_PATH", "skillswap.db")

def run():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(users)")
    columns = [row[1] for row in cur.fetchall()]
    if "portfolio" not in columns:
        cur.execute("ALTER TABLE users ADD COLUMN portfolio TEXT")
        conn.commit()
        print("[OK] 已新增 users.portfolio 欄位。")
    else:
        print("[SKIP] users.portfolio 欄位已存在，略過。")
    conn.close()

if __name__ == "__main__":
    run()