import sqlite3
import json
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any


from contextlib import contextmanager

# Render Free-safe SQLite path
DEFAULT_DB_PATH = "/tmp/memodiary.db"
DB_PATH = os.getenv("DB_PATH", DEFAULT_DB_PATH)

class DiaryStorage:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()
        # Simple RAM Cache
        self._memory_cache = {} 
        self._summary_cache = {}

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
            
            # Enable Write-Ahead Logging for concurrency (Optimization #1)
            cursor.execute('PRAGMA journal_mode=WAL;')
            # Optimization #2: Reduce disk syncs (safe for non-critical data)
            cursor.execute('PRAGMA synchronous = NORMAL;') 
            # Optimization #3: Increase cache size (approx 2MB)
            cursor.execute('PRAGMA cache_size = -2000;')
            # Optimization #4: Store temp tables in RAM
            cursor.execute('PRAGMA temp_store = MEMORY;')

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
            
            # Redundant index removed

            
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

            # NEW: Memory Optimization Columns (keeping for backward compatibility/metadata)
            if "event_type" not in columns:
                try:
                    cursor.execute("ALTER TABLE entries ADD COLUMN event_type TEXT")
                    cursor.execute("ALTER TABLE entries ADD COLUMN topics TEXT") 
                    cursor.execute("ALTER TABLE entries ADD COLUMN importance TEXT")
                except Exception as e:
                    pass

            # Create index for event_type AFTER columns exist
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_entries_event_type ON entries(session_id, event_type)')

            # Table for extracted structured facts (Existing one, can be kept or ignored, but strict new rules require memory_index)
            # keeping it so we don't break existing behavior if any, but we are moving to memory_index
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
            
            # --- NEW LAYER 2: Structured Memory Index ---
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS memory_index (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    memory_type TEXT,     -- profile, pet, event, preference, work, education, health, location
                    memory_key TEXT,      -- dog_name, job_title, birthday, etc.
                    memory_value TEXT,    -- Bhima, Data Engineer, etc.
                    source_entry_id INTEGER,
                    confidence REAL,      -- 0.0 - 1.0
                    last_updated TEXT,
                    FOREIGN KEY (source_entry_id) REFERENCES entries (id)
                )
            ''')
            
            # Indexes for memory_index
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_memory_session_key ON memory_index(session_id, memory_key)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_memory_session_type ON memory_index(session_id, memory_type)')

            # --- NEW LAYER 3: Date Intelligence ---
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS daily_summary (
                    session_id TEXT,
                    date TEXT,            -- YYYY-MM-DD
                    summary TEXT,
                    key_events TEXT,      -- JSON or text
                    dominant_mood TEXT,
                    PRIMARY KEY (session_id, date)
                )
            ''')
            
            # Indexes for daily_summary
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_daily_session_date ON daily_summary(session_id, date)')

            # --- NEW LAYER 4: Topic Profiles (The "Current State") ---
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS topic_state (
                    session_id TEXT,
                    topic TEXT,           -- health, food, routine, work, preferences
                    state TEXT,           -- Consolidated summary of this aspect
                    last_updated TEXT,
                    PRIMARY KEY (session_id, topic)
                )
            ''')

            # --- NEW LAYER 5: Hierarchical Summaries (Rolling Memory) ---
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS weekly_summary (
                    session_id TEXT,
                    start_date TEXT,      -- YYYY-MM-DD (Monday)
                    end_date TEXT,        -- YYYY-MM-DD (Sunday)
                    summary TEXT,
                    dominant_mood TEXT,
                    PRIMARY KEY (session_id, start_date)
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS monthly_summary (
                    session_id TEXT,
                    month TEXT,           -- YYYY-MM
                    summary TEXT,
                    dominant_mood TEXT,
                    PRIMARY KEY (session_id, month)
                )
            ''')

            # Additional required index from instructions
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_entries_session_time ON entries(session_id, timestamp)')
            
            # --- NEW LAYER 6: Daily Metrics (Audit Compliance) ---
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS daily_metrics (
                    session_id TEXT,
                    date TEXT,            -- YYYY-MM-DD
                    energy INTEGER,       -- 1-10
                    stress INTEGER,       -- 1-10
                    sleep INTEGER,        -- Hours or Quality 1-10
                    PRIMARY KEY (session_id, date)
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

    def update_entry_metadata(self, entry_id: int, event_type: str = None, topics: List[str] = None, importance: str = None):
        """Update memory optimization metadata for an entry."""
        with self._get_db() as conn:
            cursor = conn.cursor()
            updates = []
            params = []
            
            if event_type is not None:
                updates.append("event_type = ?")
                params.append(event_type)
            
            if topics is not None:
                updates.append("topics = ?")
                import json
                params.append(json.dumps(topics))
                
            if importance is not None:
                updates.append("importance = ?")
                params.append(importance)
                
            if updates:
                params.append(entry_id)
                sql = f"UPDATE entries SET {', '.join(updates)} WHERE id = ?"
                cursor.execute(sql, params)
                conn.commit()

    def save_fact(self, entry_id: int, fact_type: str, content: str):
        """Save an extracted fact (Legacy Layer)."""
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

    def search_entries(self, session_id: str, query: str = None, date: str = None, event_type: str = None, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Search for entries scoped to session, optionally by keyword, date, or event type.
        """
        with self._get_db() as conn:
            cursor = conn.cursor()
            
            # Select columns including new metadata
            sql = "SELECT DISTINCT e.id, e.timestamp, e.role, e.text, e.event_type, e.topics, e.importance FROM entries e LEFT JOIN extracted_facts f ON e.id = f.entry_id WHERE e.session_id = ?"
            params = [session_id]

            if date:
                sql += " AND e.timestamp LIKE ?"
                params.append(f"{date}%")
            
            if event_type:
                sql += " AND e.event_type = ?"
                params.append(event_type)

            if query:
                # Advanced Search: Check Text, Extracted Facts, AND Tags/Topics
                sql += " AND (e.text LIKE ? OR f.content LIKE ? OR e.topics LIKE ?)"
                params.append(f"%{query}%")
                params.append(f"%{query}%")
                params.append(f"%{query}%")

            sql += " ORDER BY e.timestamp DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            
            return [
                {
                    "id": row[0], 
                    "timestamp": row[1], 
                    "role": row[2], 
                    "text": row[3],
                    "event_type": row[4],
                    "topics": row[5], # Returns raw string (JSON)
                    "importance": row[6]
                }
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
                     clean_text = row[1].replace('"', '') 
                except:
                     clean_text = row[1]
                updates.append(f"{role_name}: {clean_text}")
                
            return "\n".join(updates)

    def get_entries_in_date_range(self, session_id: str, start_date: str, end_date: str) -> List[Dict]:
        """Get all user entries within a date range (inclusive)."""
        with self._get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT text, timestamp, event_type, topics FROM entries 
                WHERE session_id = ? AND role = 'user' AND timestamp BETWEEN ? AND ?
                ORDER BY timestamp ASC
            ''', (session_id, start_date, end_date))
            
            rows = cursor.fetchall()
            return [
                {"text": r[0], "timestamp": r[1], "event_type": r[2], "topics": r[3]} 
                for r in rows
            ]

    def get_streak_count(self, session_id: str) -> int:
        """Calculate current consecutive days streak."""
        with self._get_db() as conn:
            cursor = conn.cursor()
            # Get distinct dates of user activity
            cursor.execute('''
                SELECT DISTINCT date(timestamp) as entry_date 
                FROM entries 
                WHERE session_id = ? AND role = 'user'
                ORDER BY entry_date DESC
            ''', (session_id,))
            
            rows = cursor.fetchall()
            if not rows:
                return 0
            
            def parse_date(date_str):
                return datetime.strptime(date_str, "%Y-%m-%d").date()

            dates = [parse_date(r[0]) for r in rows]
            
            today = datetime.now().date()
            if dates[0] != today and dates[0] != (today - timedelta(days=1)):
                return 0 # Streak broken
                
            streak = 1
            curr = dates[0]
            
            for i in range(1, len(dates)):
                prev = dates[i]
                if (curr - prev).days == 1:
                    streak += 1
                    curr = prev
                else:
                    break
                    
            return streak

    # --- NEW: Layer 2 - Structured Memory Access ---
    
    def add_memory_item(self, session_id: str, memory_type: str, memory_key: str, memory_value: str, source_entry_id: int, confidence: float = 1.0):
        """Add or Update a structured memory item."""
        with self._get_db() as conn:
            cursor = conn.cursor()
            last_updated = datetime.now().isoformat()
            
            # Check if exists (upsert logic somewhat)
            cursor.execute('SELECT id FROM memory_index WHERE session_id = ? AND memory_key = ?', (session_id, memory_key))
            row = cursor.fetchone()
            
            if row:
                # Update
                cursor.execute('''
                    UPDATE memory_index 
                    SET memory_value = ?, memory_type = ?, source_entry_id = ?, confidence = ?, last_updated = ?
                    WHERE id = ?
                ''', (memory_value, memory_type, source_entry_id, confidence, last_updated, row[0]))
            else:
                # Insert
                cursor.execute('''
                    INSERT INTO memory_index (session_id, memory_type, memory_key, memory_value, source_entry_id, confidence, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (session_id, memory_type, memory_key, memory_value, source_entry_id, confidence, last_updated))
            
            conn.commit()
        
        # Invalidate cache for this session (Simple approach)
        if session_id in self._memory_cache:
            del self._memory_cache[session_id]

    def get_memory_items(self, session_id: str, memory_key: str = None, memory_type: str = None) -> List[Dict]:
        """Retrieve structured memory items."""
        # Check Cache (Only if looking for specific key to match "search usage")
        cache_key = f"{session_id}_{memory_key}_{memory_type}"
        if session_id in self._memory_cache and cache_key in self._memory_cache[session_id]:
             return self._memory_cache[session_id][cache_key]

        with self._get_db() as conn:
            cursor = conn.cursor()
            sql = "SELECT memory_type, memory_key, memory_value, confidence, last_updated FROM memory_index WHERE session_id = ?"
            params = [session_id]
            
            if memory_key:
                sql += " AND memory_key = ?"
                params.append(memory_key)
            
            if memory_type:
                sql += " AND memory_type = ?"
                params.append(memory_type)
                
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            
            results = [
                {
                    "memory_type": r[0],
                    "memory_key": r[1],
                    "memory_value": r[2],
                    "confidence": r[3],
                    "last_updated": r[4]
                }
                for r in rows
            ]
            
            # Update Cache
            if session_id not in self._memory_cache: self._memory_cache[session_id] = {}
            if len(self._memory_cache[session_id]) > 20: self._memory_cache[session_id].clear() # Simple Limit
            self._memory_cache[session_id][cache_key] = results
            
            return results

    def get_memory_items_batch(self, session_id: str, memory_keys: List[str]) -> List[Dict]:
        """Retrieve multiple memory items in a single query."""
        if not memory_keys:
            return []
            
        with self._get_db() as conn:
            cursor = conn.cursor()
            # Prepare placeholders: ?,?,?
            placeholders = ','.join(['?'] * len(memory_keys))
            sql = f"SELECT memory_type, memory_key, memory_value, confidence, last_updated FROM memory_index WHERE session_id = ? AND memory_key IN ({placeholders})"
            
            params = [session_id] + memory_keys
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            
            return [
                 {
                    "memory_type": r[0],
                    "memory_key": r[1],
                    "memory_value": r[2],
                    "confidence": r[3],
                    "last_updated": r[4]
                }
                for r in rows
            ]

    # --- NEW: Layer 3 - Daily Summary Access ---

    def upsert_daily_summary(self, session_id: str, date: str, summary: str, key_events: str, mood: str):
        """Insert or Update the daily summary."""
        with self._get_db() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO daily_summary (session_id, date, summary, key_events, dominant_mood)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(session_id, date) DO UPDATE SET
                    summary = excluded.summary,
                    key_events = excluded.key_events,
                    dominant_mood = excluded.dominant_mood
            ''', (session_id, date, summary, key_events, mood))
            
            conn.commit()
            
            # Update Cache
            self._summary_cache[f"{session_id}_{date}"] = {
                "summary": summary,
                "key_events": key_events,
                "dominant_mood": mood
            }

    def get_daily_summary(self, session_id: str, date: str) -> Optional[Dict]:
        """Get summary for a specific date."""
        # Check Cache
        cache_key = f"{session_id}_{date}"
        if cache_key in self._summary_cache:
            return self._summary_cache[cache_key]

        with self._get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT summary, key_events, dominant_mood FROM daily_summary WHERE session_id = ? AND date = ?', (session_id, date))
            row = cursor.fetchone()
            
            if row:
                res = {
                    "summary": row[0],
                    "key_events": row[1],
                    "dominant_mood": row[2]
                }
                self._summary_cache[cache_key] = res
                return res
            return None

    # --- NEW: Layer 4 & 5 Access Methods ---

    def upsert_topic_state(self, session_id: str, topic: str, state: str):
        """Update the consolidated state of a life topic."""
        with self._get_db() as conn:
            cursor = conn.cursor()
            last_updated = datetime.now().isoformat()
            
            cursor.execute('''
                INSERT INTO topic_state (session_id, topic, state, last_updated)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id, topic) DO UPDATE SET
                    state = excluded.state,
                    last_updated = excluded.last_updated
            ''', (session_id, topic, state, last_updated))
            conn.commit()

    def get_topic_states(self, session_id: str, topics: List[str] = None) -> Dict[str, str]:
        """Get the current state of specific topics (or all if None)."""
        with self._get_db() as conn:
            cursor = conn.cursor()
            if topics:
                placeholders = ','.join(['?'] * len(topics))
                sql = f"SELECT topic, state FROM topic_state WHERE session_id = ? AND topic IN ({placeholders})"
                params = [session_id] + topics
            else:
                sql = "SELECT topic, state FROM topic_state WHERE session_id = ?"
                params = [session_id]
                
            cursor.execute(sql, params)
            return {row[0]: row[1] for row in cursor.fetchall()}

    def upsert_weekly_summary(self, session_id: str, start_date: str, end_date: str, summary: str, mood: str):
        with self._get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO weekly_summary (session_id, start_date, end_date, summary, dominant_mood)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(session_id, start_date) DO UPDATE SET
                    summary = excluded.summary,
                    dominant_mood = excluded.dominant_mood
            ''', (session_id, start_date, end_date, summary, mood))
            conn.commit()

    def get_weekly_summaries(self, session_id: str, limit: int = 4) -> List[Dict]:
        with self._get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT start_date, end_date, summary, dominant_mood FROM weekly_summary WHERE session_id = ? ORDER BY start_date DESC LIMIT ?', (session_id, limit))
            cols = ["start_date", "end_date", "summary", "dominant_mood"]
            return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def upsert_monthly_summary(self, session_id: str, month: str, summary: str, mood: str):
        with self._get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO monthly_summary (session_id, month, summary, dominant_mood)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id, month) DO UPDATE SET
                    summary = excluded.summary,
                    dominant_mood = excluded.dominant_mood
            ''', (session_id, month, summary, mood))
            conn.commit()

    def get_monthly_summaries(self, session_id: str, limit: int = 6) -> List[Dict]:
        with self._get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT month, summary, dominant_mood FROM monthly_summary WHERE session_id = ? ORDER BY month DESC LIMIT ?', (session_id, limit))
            cols = ["month", "summary", "dominant_mood"]
            return [dict(zip(cols, row)) for row in cursor.fetchall()]

    # --- NEW: Layer 6 Methods (Metrics) ---

    def upsert_daily_metrics(self, session_id: str, date: str, energy: int = None, stress: int = None, sleep: int = None):
        """Insert or Update daily numeric metrics."""
        with self._get_db() as conn:
            cursor = conn.cursor()
            
            # Simple upsert with partial updates is tricky in pure SQL without reading first or complex COALESCE
            # But since this comes from daily summary, we usually write all at once.
            # We'll rely on ON CONFLICT DO UPDATE
            
            cursor.execute('''
                INSERT INTO daily_metrics (session_id, date, energy, stress, sleep)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(session_id, date) DO UPDATE SET
                    energy = COALESCE(excluded.energy, daily_metrics.energy),
                    stress = COALESCE(excluded.stress, daily_metrics.stress),
                    sleep = COALESCE(excluded.sleep, daily_metrics.sleep)
            ''', (session_id, date, energy, stress, sleep))
            conn.commit()

    def get_daily_metrics_range(self, session_id: str, start_date: str, end_date: str) -> List[Dict]:
        """Get structured metrics for a date range."""
        with self._get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT date, energy, stress, sleep FROM daily_metrics
                WHERE session_id = ? AND date BETWEEN ? AND ?
                ORDER BY date ASC
            ''', (session_id, start_date, end_date))
            
            return [
                {"date": r[0], "energy": r[1], "stress": r[2], "sleep": r[3]}
                for r in cursor.fetchall()
            ]

    # --- ADMIN ANALYTICS ---

    def get_analytics_stats(self) -> Dict[str, Any]:
        """
        Get aggregated analytics for the admin dashboard.
        Returns:
            - total_users
            - new_users_today
            - active_users_24h
            - total_messages
            - daily_growth (last 7 days)
            - activity_trend (last 7 days)
        """
        stats = {}
        with self._get_db() as conn:
            cursor = conn.cursor()

            # 1. Total Users
            cursor.execute("SELECT COUNT(*) FROM users")
            stats['total_users'] = cursor.fetchone()[0]

            # 2. Total Messages
            cursor.execute("SELECT COUNT(*) FROM entries")
            stats['total_messages'] = cursor.fetchone()[0]

            # 3. New Users Today (Using ISO string slicing for YYYY-MM-DD)
            today_str = datetime.now().strftime("%Y-%m-%d")
            cursor.execute("SELECT COUNT(*) FROM users WHERE substr(created_at, 1, 10) = ?", (today_str,))
            stats['new_users_today'] = cursor.fetchone()[0]

            # 4. Active Users (24h) - Distinct sessions in entries
            yesterday_iso = (datetime.now() - timedelta(days=1)).isoformat()
            cursor.execute("SELECT COUNT(DISTINCT session_id) FROM entries WHERE timestamp > ?", (yesterday_iso,))
            stats['active_users_24h'] = cursor.fetchone()[0]

            # 5. User Growth Trend (Last 7 Days)
            # SQLite doesn't have convenient generate_series, so we query groupings and fill gaps in Python if strictly needed, 
            # or just return what we have.
            cursor.execute('''
                SELECT substr(created_at, 1, 10) as day, COUNT(*) 
                FROM users 
                GROUP BY day 
                ORDER BY day DESC 
                LIMIT 7
            ''')
            # List of [date, count], newest first
            stats['daily_growth'] = cursor.fetchall()[::-1] 

            # 6. Activity Trend (Last 7 Days) - Message count by day
            cursor.execute('''
                SELECT substr(timestamp, 1, 10) as day, COUNT(*) 
                FROM entries 
                GROUP BY day 
                ORDER BY day DESC 
                LIMIT 7
            ''')
            stats['activity_trend'] = cursor.fetchall()[::-1]

        return stats

# Global instance
storage = DiaryStorage()
