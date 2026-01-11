
import sqlite3
import os
from datetime import datetime

DB_PATH = "memodiary.db"

def inspect_db():
    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print(f"--- DATABASE INSPECTION: {datetime.now()} ---")

    # 1. Recent Sessions
    print("\n[1] RECENT SESSIONS (Last 5):")
    cursor.execute("SELECT session_id, MAX(timestamp) as last_active, COUNT(*) as entry_count FROM entries GROUP BY session_id ORDER BY last_active DESC LIMIT 5")
    sessions = cursor.fetchall()
    for s in sessions:
        print(f"   SID: {s[0]} | Last Active: {s[1]} | Entries: {s[2]}")

    if not sessions:
        print("   (No sessions found)")
        conn.close()
        return

    # Pick the most recent session
    target_session = sessions[0][0]
    print(f"\n[2] INSPECTING LATEST SESSION: {target_session}")

    # 2. Recent Entries (Text)
    print("\n   --- Recent User Entries (Last 10) ---")
    cursor.execute("SELECT timestamp, role, text FROM entries WHERE session_id = ? ORDER BY id DESC LIMIT 10", (target_session,))
    rows = cursor.fetchall()
    for r in rows:
        print(f"   [{r[0]}] {r[1].upper()}: {r[2][:100]}...")

    # 3. Memory Index (Structured Facts)
    print("\n   --- Memory Index (Facts) ---")
    cursor.execute("SELECT memory_key, memory_value, confidence FROM memory_index WHERE session_id = ?", (target_session,))
    facts = cursor.fetchall()
    if facts:
        for f in facts:
            print(f"   * {f[0]}: {f[1]} (Conf: {f[2]})")
    else:
        print("   (No structured memories found)")

    # 4. Daily Metrics
    print("\n   --- Daily Metrics ---")
    cursor.execute("SELECT date, energy, stress, sleep FROM daily_metrics WHERE session_id = ? ORDER BY date DESC LIMIT 5", (target_session,))
    metrics = cursor.fetchall()
    if metrics:
        for m in metrics:
            print(f"   {m[0]}: Energy={m[1]}, Stress={m[2]}, Sleep={m[3]}")
    else:
        print("   (No metrics found)")

    conn.close()

if __name__ == "__main__":
    inspect_db()
