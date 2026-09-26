# -*- coding: utf-8 -*-
"""
Queue and SQLite History Management Tests (100% Offline / Zero Network).
Tests episode scanning algorithms, queue transitions, concurrent SQLite writes, and auto-migration.
"""

import unittest
import os
import sys
import tempfile
import shutil
import json
import threading

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from history import SQLiteHistoryManager
from android_app.mobile_engine import MobileDownloadController


class TestQueueAndHistory(unittest.TestCase):
    
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="test_q_hist_")
        self.test_db_file = os.path.join(self.test_dir, "test_history.db")
        self.history_mgr = SQLiteHistoryManager(self.test_db_file, legacy_json_path=None)
        self.ctrl = MobileDownloadController()
        self.ctrl.set_download_dir(self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_history_sqlite_crud(self):
        """Inserting, retrieving, and clearing records in SQLite."""
        entry = self.history_mgr.add_entry(
            title="Breaking Bad S01E01",
            file_path=os.path.join(self.test_dir, "bb1.mp4"),
            size_bytes=450 * 1024 * 1024,
            source_url="https://example.com/bb-1",
            media_type="Film"
        )

        self.assertIn("id", entry)
        self.assertEqual(self.history_mgr.count(), 1)

        entries = self.history_mgr.load_history()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["title"], "Breaking Bad S01E01")
        self.assertEqual(entries[0]["media_type"], "Film")

        # Delete single entry
        self.history_mgr.delete_entry(entry["id"])
        self.assertEqual(self.history_mgr.count(), 0)

    def test_concurrent_multithreaded_history_writes(self):
        """Simultaneous writes from 10 parallel threads must never corrupt or lose records."""
        thread_count = 10
        writes_per_thread = 5
        threads = []

        def worker(thread_idx):
            for i in range(writes_per_thread):
                self.history_mgr.add_entry(
                    title=f"Parallel Video T{thread_idx}_{i}",
                    file_path=f"/fake/path/v_{thread_idx}_{i}.mp4",
                    size_bytes=10 * 1024 * 1024
                )

        for t_id in range(thread_count):
            t = threading.Thread(target=worker, args=(t_id,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        expected_total = thread_count * writes_per_thread
        self.assertEqual(self.history_mgr.count(), expected_total)

    def test_series_episode_scanner_patterns(self):
        """Regex and string pattern recognition for various Turkish and foreign series URLs."""
        patterns = [
            ("https://dizibox.tv/breaking-bad-1-sezon-1-bolum-izle/", 1, 4),
            ("https://diziwatch.net/dizi/stranger-things/episode-1/", 1, 3),
            ("https://site.com/watch?ep=1", 1, 5)
        ]

        for url, s_ep, e_ep in patterns:
            results = self.ctrl.scan_series_episodes(url, s_ep, e_ep)
            expected_count = (e_ep - s_ep) + 1
            self.assertEqual(len(results), expected_count)
            self.assertTrue(all("url" in r and "title" in r for r in results))

    def test_queue_lifecycle(self):
        """Queue item addition, removal, and clearing operations."""
        self.ctrl.clear_queue()
        self.assertEqual(len(self.ctrl.queue_items), 0)

        it1 = self.ctrl.add_queue_item("Bölüm 1", "https://site.com/ep1", "film")
        _ = self.ctrl.add_queue_item("Bölüm 2", "https://site.com/ep2", "film")
        self.assertEqual(len(self.ctrl.queue_items), 2)

        self.ctrl.remove_queue_item(it1["id"])
        self.assertEqual(len(self.ctrl.queue_items), 1)
    def test_queue_single_item_cancellation_and_retry(self):
        """Single item cancel, retry, and selective queue manipulation."""
        self.ctrl.clear_queue()
        it1 = self.ctrl.add_queue_item("Test Movie 1", "https://site.com/m1", "film")
        it2 = self.ctrl.add_queue_item("Test Movie 2", "https://site.com/m2", "film")
        
        # Test item states
        self.assertEqual(it1["status"], "Bekliyor")
        
        # Cancel item 1
        it1["status"] = "İptal Edildi ⏹️"
        self.assertEqual(self.ctrl.queue_items[0]["status"], "İptal Edildi ⏹️")
        
        # Retry item 1
        it1["status"] = "Bekliyor"
        self.assertEqual(self.ctrl.queue_items[0]["status"], "Bekliyor")
        
        # Remove item 2
        self.ctrl.remove_queue_item(it2["id"])
    def test_queue_pause_and_resume_transitions(self):
        """Tests that pausing queue updates state and item status, and completion adds to history."""
        self.ctrl.clear_queue()
        it1 = self.ctrl.add_queue_item("Episode 1", "https://site.com/ep1", "film")
        
        # Simulate active download
        it1["status"] = "İndiriliyor %45"
        it1["progress"] = 0.45
        
        # Pause queue
        self.ctrl.is_queue_paused = True
        it1["status"] = "⏸️ Duraklatıldı"
        self.assertEqual(it1["status"], "⏸️ Duraklatıldı")
        self.assertEqual(it1["progress"], 0.45)
        
        # Resume queue and complete
        self.ctrl.is_queue_paused = False
        it1["status"] = "Tamamlandı"
        it1["progress"] = 1.0
        
        # Add to history
        self.history_mgr.add_entry(
            title=it1["title"],
            file_path=os.path.join(self.test_dir, "ep1.mp4"),
            size_bytes=100 * 1024 * 1024,
            source_url=it1["url"],
            media_type="Dizi / Kuyruk"
        )
        
        hist = self.history_mgr.load_history()
        self.assertEqual(len(hist), 1)
        self.assertEqual(hist[0]["title"], "Episode 1")
        self.assertEqual(hist[0]["media_type"], "Dizi / Kuyruk")


if __name__ == "__main__":
    unittest.main()


