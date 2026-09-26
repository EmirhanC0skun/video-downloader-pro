# -*- coding: utf-8 -*-
"""
Video Downloader Pro — Thread-Safe SQLite History Manager with JSON Migration.
Supports WAL journal mode for high concurrency and zero data loss.
"""

import os
import time
import json
import sqlite3
import threading
from typing import List, Dict, Any, Optional

try:
    from logger import get_logger
except ImportError:
    try:
        from core.logger import get_logger
    except ImportError:
        import logging
        def get_logger(name):
            return logging.getLogger(name)

logger = get_logger("history")

_STORAGE_DIR_CACHE = None


def _get_history_storage_dir():
    """
    Yazilabilir bir gecmis dizini secer ve sonucu onbellekler.

    NOT: PYTHONHOME adayi bilerek kaldirildi; yorumlayici kurulum dizini bir
    kullanici veri konumu degildir (bkz. D6).
    """
    global _STORAGE_DIR_CACHE
    if _STORAGE_DIR_CACHE is not None:
        return _STORAGE_DIR_CACHE

    candidates = [
        os.environ.get("VDP_DATA_DIR"),
        os.path.join(os.path.expanduser("~"), ".video_downloader"),
        "/storage/emulated/0/Download/VideoDownloader",
        os.environ.get("TMPDIR"),
        os.path.expanduser("~"),
        ".",
    ]
    for c in candidates:
        if not c:
            continue
        try:
            os.makedirs(c, exist_ok=True)
            test_p = os.path.join(c, f".perm_{int(time.time()*1000)}.tmp")
            with open(test_p, "w") as f:
                f.write("1")
            os.remove(test_p)
            _STORAGE_DIR_CACHE = c
            return c
        except Exception:
            continue

    _STORAGE_DIR_CACHE = "."
    return _STORAGE_DIR_CACHE


_UNSET = object()

# JS tarzi milisaniye zaman damgasinin makul alt siniri (2001-09-09).
_MS_TIMESTAMP_FLOOR = 1_000_000_000_000


def _legacy_created_at(item):
    """
    Eski JSON kaydindaki `id` alanindan sirlama zaman damgasi turetir.

    Onceki kod her `id` degerini 1000'e boluyordu; id kucuk bir tamsayi (1, 2, 3)
    oldugunda created_at ~0 cikiyor ve gecmis sirasi bozuluyordu (bkz. D6).
    """
    raw = item.get("id")
    try:
        raw = float(raw)
    except (TypeError, ValueError):
        return time.time()
    if raw >= _MS_TIMESTAMP_FLOOR:
        return raw / 1000.0
    if raw >= 946_684_800:  # saniye cinsinden makul bir epoch (2000-01-01 sonrasi)
        return raw
    return time.time()


class SQLiteHistoryManager:
    """Thread-safe SQLite history storage with atomic locks and migration."""

    def __init__(self, db_path: Optional[str] = None, legacy_json_path: Optional[str] = _UNSET):
        storage_dir = _get_history_storage_dir()
        self.db_path = db_path or os.path.join(storage_dir, "history.db")
        if legacy_json_path is _UNSET:
            legacy_json_path = os.path.join(storage_dir, "history.json")
        self.legacy_json_path = legacy_json_path
        self._lock = threading.RLock()
        self._init_db()
        if self.legacy_json_path:
            self._auto_migrate_legacy_json()

    def _get_connection(self) -> sqlite3.Connection:
        """Returns a connection configured with WAL mode and row factory."""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
        except Exception:
            logger.debug("[history.py:72] _get_connection() sessiz istisna yutuldu", exc_info=True)
        return conn

    def _init_db(self):
        """Creates the history table and indices if they do not exist."""
        with self._lock:
            try:
                with self._get_connection() as conn:
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS download_history (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            title TEXT NOT NULL,
                            file_path TEXT NOT NULL,
                            size_mb REAL DEFAULT 0.0,
                            source_url TEXT,
                            media_type TEXT DEFAULT 'Film',
                            timestamp TEXT NOT NULL,
                            created_at REAL NOT NULL
                        );
                    """)
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_hist_created ON download_history(created_at DESC);")
                logger.debug(f"History database initialized at: {self.db_path}")
            except Exception as ex:
                logger.error(f"Failed to initialize history database: {ex}")

    def _auto_migrate_legacy_json(self):
        """Migrates older JSON history entries into SQLite automatically on first run."""
        if not self.legacy_json_path or not os.path.exists(self.legacy_json_path):
            return

        with self._lock:
            try:
                # Check if SQLite already has rows
                if self.count() > 0:
                    return

                with open(self.legacy_json_path, "r", encoding="utf-8") as f:
                    legacy_entries = json.load(f)

                if isinstance(legacy_entries, list) and legacy_entries:
                    logger.info(f"Migrating {len(legacy_entries)} legacy JSON history items to SQLite...")
                    with self._get_connection() as conn:
                        for item in legacy_entries:
                            conn.execute("""
                                INSERT INTO download_history 
                                (title, file_path, size_mb, source_url, media_type, timestamp, created_at)
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                            """, (
                                item.get("title", "Bilinmeyen Medya"),
                                item.get("file_path", ""),
                                item.get("size_mb", 0.0),
                                item.get("source_url", ""),
                                item.get("media_type", "Film"),
                                item.get("timestamp", time.strftime("%Y-%m-%d %H:%M:%S")),
                                _legacy_created_at(item)
                            ))
                    logger.info("Legacy JSON history successfully migrated to SQLite.")
            except Exception as ex:
                logger.warning(f"Legacy JSON migration note: {ex}")

    def add_entry(self, title: str, file_path: str, size_bytes: int = 0, source_url: str = "", media_type: str = "Film") -> Dict[str, Any]:
        """Inserts a new download record thread-safely."""
        now_ts = time.time()
        date_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now_ts))
        
        if size_bytes > 0:
            size_mb = round(size_bytes / (1024 * 1024), 2)
        elif os.path.exists(file_path):
            size_mb = round(os.path.getsize(file_path) / (1024 * 1024), 2)
        else:
            size_mb = 0.0

        clean_title = title or os.path.basename(file_path)
        abs_path = os.path.abspath(file_path)

        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.execute("""
                        INSERT INTO download_history 
                        (title, file_path, size_mb, source_url, media_type, timestamp, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (clean_title, abs_path, size_mb, source_url, media_type, date_str, now_ts))
                    new_id = cursor.lastrowid

                entry = {
                    "id": new_id,
                    "title": clean_title,
                    "file_path": abs_path,
                    "size_mb": size_mb,
                    "source_url": source_url,
                    "media_type": media_type,
                    "timestamp": date_str
                }
                logger.info(f"Added history record #{new_id}: '{clean_title}' ({size_mb} MB)")
                return entry
            except Exception as ex:
                logger.error(f"Failed to insert history record: {ex}")
                return {}

    def load_history(self, limit: int = 200) -> List[Dict[str, Any]]:
        """Retrieves recent history entries sorted by newest first."""
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.execute("""
                        SELECT id, title, file_path, size_mb, source_url, media_type, timestamp 
                        FROM download_history 
                        ORDER BY created_at DESC 
                        LIMIT ?
                    """, (limit,))
                    return [dict(row) for row in cursor.fetchall()]
            except Exception as ex:
                logger.error(f"Failed to load history: {ex}")
                return []

    def delete_entry(self, entry_id: int) -> bool:
        """Deletes a single history record by ID."""
        with self._lock:
            try:
                with self._get_connection() as conn:
                    conn.execute("DELETE FROM download_history WHERE id = ?", (entry_id,))
                logger.debug(f"Deleted history record #{entry_id}")
                return True
            except Exception as ex:
                logger.error(f"Failed to delete history record #{entry_id}: {ex}")
                return False

    def clear_history(self) -> bool:
        """Clears all history records."""
        with self._lock:
            try:
                with self._get_connection() as conn:
                    conn.execute("DELETE FROM download_history;")
                logger.info("All history records cleared.")
                return True
            except Exception as ex:
                logger.error(f"Failed to clear history: {ex}")
                return False

    def count(self) -> int:
        """Returns total count of download records."""
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.execute("SELECT COUNT(*) FROM download_history;")
                    row = cursor.fetchone()
                    return row[0] if row else 0
            except sqlite3.Error as ex:
                logger.error(f"Database error counting records: {ex}")
                return 0


# Varsayilan yonetici tembel olusturulur: `import history` artik dosya sistemine
# dokunmaz, veritabani ilk kullanimda acilir (bkz. D6).
_default_manager: Optional["SQLiteHistoryManager"] = None
_manager_lock = threading.Lock()


def get_manager() -> "SQLiteHistoryManager":
    """Surec genelinde tek bir gecmis yoneticisi dondurur (tembel, thread-safe)."""
    global _default_manager
    if _default_manager is None:
        with _manager_lock:
            if _default_manager is None:
                _default_manager = SQLiteHistoryManager()
    return _default_manager


# Functional API for backward compatibility
def load_history(limit: int = 200) -> List[Dict[str, Any]]:
    return get_manager().load_history(limit)


def add_history_entry(title: str, file_path: str, size_bytes: int = 0, source_url: str = "", media_type: str = "Film") -> Dict[str, Any]:
    return get_manager().add_entry(title, file_path, size_bytes, source_url, media_type)


def clear_all_history():
    return get_manager().clear_history()


def delete_history_entry(entry_id: int) -> bool:
    """Tekil gecmis kaydini siler (SQLiteHistoryManager.delete_entry sarmalayicisi)."""
    return get_manager().delete_entry(entry_id)
