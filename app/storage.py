import sqlite3
import json
import os
from datetime import datetime
from typing import List, Dict, Optional, Any

from contextlib import contextmanager

# Render Free-safe SQLite path
DEFAULT_DB_PATH = "/tmp/memodiary.db"
DB_PATH = os.getenv("DB_PATH", DEFAULT_DB_PATH)

class DiaryStorage:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _get_db(self):
        # Ensure directory exists (important)
        if os.path.dirname(self.db_path):
             os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
             
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        """Initialize the database schema."""
        with self._get_db() as conn:
            cursor = conn.cursor()
            
            # Table for raw entries (chat history)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    timestamp TEXT NOT NULL,
                    role TEXT NOT NULL,  -- 'user' or 'model'
                    text TEXT NOT NULL,
                    processed BOOLEAN DEFAULT 0
                )
            ''')
            
            # Create indexes for performance
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_entries_session_timestamp ON entries(session_id, timestamp)')
            
            # Check if session_id column exists
            cursor.execute("PRAGMA table_info(entries)")
            columns = [info[1] for info in cursor.fetchall()]
            if "session_id" not in columns:
                import logging
                logger = logging.getLogger(__name__)
                logger.info("Migrating DB: Adding session_id to entries...")
                try:
                    cursor.execute("ALTER TABLE entries ADD COLUMN session_id TEXT")
                except Exception as e:
                    logger.warning(f"Migration warning: {e}")

            # Check if language_code column exists
            if "language_code" not in columns:
                try:
                    cursor.execute("ALTER TABLE entries ADD COLUMN language_code TEXT DEFAULT 'en'")
                except Exception as e:
                    pass # Log if needed

            # Table for extracted structured facts
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS extracted_facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entry_id INTEGER,
                    fact_type TEXT, -- 'event', 'person', 'emotion', 'detail'
                    content TEXT,
                    FOREIGN KEY (entry_id) REFERENCES entries (id)
                )
            ''')
            
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_facts_entry_id ON extracted_facts(entry_id)')

            # NEW: Users Table for Session Management & Onboarding
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    session_id TEXT PRIMARY KEY,
                    name TEXT,
                    age TEXT,
                    onboarding_complete BOOLEAN DEFAULT 0,
                    created_at TEXT
                )
            ''')
            
            conn.commit()

    # --- User / Session Management ---

    def get_user(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT session_id, name, age, onboarding_complete FROM users WHERE session_id = ?', (session_id,))
            row = cursor.fetchone()
            if row:
                return {
                    "session_id": row[0],
                    "name": row[1],
                    "age": row[2],
                    "onboarding_complete": bool(row[3])
                }
        return None

    def create_user(self, session_id: str):
        with self._get_db() as conn:
            cursor = conn.cursor()
            created_at = datetime.now().isoformat()
            try:
                cursor.execute('INSERT INTO users (session_id, created_at, onboarding_complete) VALUES (?, ?, 0)', (session_id, created_at))
                conn.commit()
            except sqlite3.IntegrityError:
                pass # Already exists

    def update_user_profile(self, session_id: str, name: str = None, age: str = None, onboarding_complete: bool = None):
        with self._get_db() as conn:
            cursor = conn.cursor()
            
            updates = []
            params = []
            if name is not None:
                updates.append("name = ?")
                params.append(name)
            if age is not None:
                updates.append("age = ?")
                params.append(age)
            if onboarding_complete is not None:
                updates.append("onboarding_complete = ?")
                params.append(1 if onboarding_complete else 0)
                
            if updates:
                params.append(session_id)
                sql = f"UPDATE users SET {', '.join(updates)} WHERE session_id = ?"
                cursor.execute(sql, params)
                conn.commit()

    # --- MemoDiary Entries ---

    def add_entry(self, session_id: str, role: str, text: str, language_code: str = "en") -> int:
        """Save a new diary entry."""
        with self._get_db() as conn:
            cursor = conn.cursor()
            timestamp = datetime.now().isoformat()
            
            cursor.execute('''
                INSERT INTO entries (session_id, timestamp, role, text, language_code)
                VALUES (?, ?, ?, ?, ?)
            ''', (session_id, timestamp, role, text, language_code))
            
            entry_id = cursor.lastrowid
            conn.commit()
            return entry_id

    def get_unprocessed_entries(self) -> List[Dict[str, Any]]:
        """Get entries that haven't been analyzed for facts yet."""
        with self._get_db() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, session_id, timestamp, role, text FROM entries
                WHERE processed = 0 AND role = 'user'
            ''')
            
            rows = cursor.fetchall()
            
            return [
                {"id": row[0], "session_id": row[1], "timestamp": row[2], "role": row[3], "text": row[4]}
                for row in rows
            ]

    def mark_processed(self, entry_id: int):
        """Mark an entry as processed."""
        with self._get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE entries SET processed = 1 WHERE id = ?', (entry_id,))
            conn.commit()

    def save_fact(self, entry_id: int, fact_type: str, content: str):
        """Save an extracted fact."""
        with self._get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO extracted_facts (entry_id, fact_type, content)
                VALUES (?, ?, ?)
            ''', (entry_id, fact_type, content))
            conn.commit()

    def get_entries_in_range(self, session_id: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """
        Fetch entries for a specific session within a date range (inclusive).
        Dates should be in ISO format or YYYY-MM-DD.
        """
        with self._get_db() as conn:
            cursor = conn.cursor()
            
            # We use a string comparison for ISO dates
            cursor.execute('''
                SELECT id, timestamp, role, text FROM entries
                WHERE session_id = ? AND timestamp >= ? AND timestamp <= ?
                ORDER BY timestamp ASC
            ''', (session_id, start_date, end_date))
            
            rows = cursor.fetchall()
            
            return [
                {"id": row[0], "timestamp": row[1], "role": row[2], "text": row[3]}
                for row in rows
            ]

    def search_entries(self, session_id: str, query: str = None, date: str = None, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Search for entries scoped to session, optionally by keyword or specific date.
        """
        with self._get_db() as conn:
            cursor = conn.cursor()
            
            sql = "SELECT DISTINCT e.id, e.timestamp, e.role, e.text FROM entries e LEFT JOIN extracted_facts f ON e.id = f.entry_id WHERE e.session_id = ?"
            params = [session_id]

            if date:
                sql += " AND e.timestamp LIKE ?"
                params.append(f"{date}%")
            
            if query:
                sql += " AND (e.text LIKE ? OR f.content LIKE ?)"
                params.append(f"%{query}%")
                params.append(f"%{query}%")

            sql += " ORDER BY e.timestamp DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            
            return [
                {"id": row[0], "timestamp": row[1], "role": row[2], "text": row[3]}
                for row in rows
            ]

    def get_recent_entries(self, session_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get the most recent entries for a session as a list of dictionaries.
        """
        with self._get_db() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, timestamp, role, text FROM entries
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
            ''', (session_id, limit))
            
            rows = cursor.fetchall()
            
            return [
                {"id": row[0], "timestamp": row[1], "role": row[2], "text": row[3]}
                for row in rows
            ]

    def get_recent_context(self, session_id: str, limit: int = 5) -> str:
        """Get the most recent conversation context as text for a specific session."""
        with self._get_db() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT role, text FROM entries
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
            ''', (session_id, limit,))
            
            rows = cursor.fetchall()
            
            updates = []
            for row in reversed(rows):
                role_name = "User" if row[0] == "user" else "MEMO"
                try:
                    # remove any potential JSON artifacts from older versions if they exist
                     clean_text = row[1].replace('"', '') 
                except:
                     clean_text = row[1]
                updates.append(f"{role_name}: {clean_text}")
                
            return "\n".join(updates)

# Global instance
storage = DiaryStorage()
