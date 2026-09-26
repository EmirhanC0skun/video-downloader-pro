# -*- coding: utf-8 -*-
"""
Mock Download Engine Tests (100% Offline / Zero Network).
Verifies multi-thread segment worker, caching/resume, cancellation, and part file management.
"""

import unittest
import os
import sys
import tempfile
import shutil
from unittest.mock import MagicMock

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine import VideoDownloadEngine


class TestMockDownloadEngine(unittest.TestCase):
    
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="test_engine_")
        self.engine = VideoDownloadEngine()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_download_segment_file_success(self):
        """Single segment download writes temp part file and renames to target cleanly."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.iter_content.return_value = [b"MOCK_TS_DATA_CHUNK_1", b"MOCK_TS_DATA_CHUNK_2"]
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None

        self.engine._session.get = MagicMock(return_value=mock_resp)

        target_file = os.path.join(self.test_dir, "segment_001.ts")
        headers = {"User-Agent": "TestAgent"}
        
        ok, bytes_written = self.engine.download_segment_file(
            url="http://stream.example.com/seg1.ts",
            headers=headers,
            target_path=target_file,
            max_retries=1
        )

        self.assertTrue(ok)
        self.assertTrue(os.path.exists(target_file))
        self.assertEqual(bytes_written, len(b"MOCK_TS_DATA_CHUNK_1MOCK_TS_DATA_CHUNK_2"))
        
        # Ensure temporary .part is cleaned up
        temp_part = target_file + ".part"
        self.assertFalse(os.path.exists(temp_part))

    def test_resume_cache_detection(self):
        """Pre-existing valid segments (> 512 bytes) are skipped (cached) and not re-downloaded."""
        # Pre-create segment 0 on disk (> 512 bytes)
        seg0_path = os.path.join(self.test_dir, "seg_0.ts")
        with open(seg0_path, "wb") as f:
            f.write(b"X" * 1024)

        seg1_path = os.path.join(self.test_dir, "seg_1.ts")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.iter_content.return_value = [b"Y" * 1024]
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None

        self.engine._session.get = MagicMock(return_value=mock_resp)

        segment_tasks = [
            (0, "http://example.com/seg0.ts", seg0_path),
            (1, "http://example.com/seg1.ts", seg1_path)
        ]

        progress_calls = []
        def prog_cb(completed, total, total_bytes):
            progress_calls.append((completed, total, total_bytes))

        completed, total_b, failed = self.engine.download_stream_segments(
            segment_tasks=segment_tasks,
            headers={},
            thread_count=2,
            progress_callback=prog_cb
        )

        self.assertEqual(completed, 2)
        self.assertEqual(len(failed), 0)
        self.assertTrue(os.path.exists(seg1_path))
        
        # _session.get should only be called for seg1 (1 time), because seg0 was cached!
        self.assertEqual(self.engine._session.get.call_count, 1)

    def test_engine_cancellation(self):
        """Calling cancel() triggers cancel_event and reset_cancel() clears it."""
        self.engine.reset_cancel()
        self.assertFalse(self.engine.cancel_event.is_set())

        self.engine.cancel()
        self.assertTrue(self.engine.cancel_event.is_set())

        self.engine.reset_cancel()
        self.assertFalse(self.engine.cancel_event.is_set())


if __name__ == "__main__":
    unittest.main()
