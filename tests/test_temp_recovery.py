# -*- coding: utf-8 -*-
"""
Unit tests for Crash Recovery & Stale Temp Disk Hygiene (100% Offline / Zero Network).
Verifies .vdp_state.json persistence, progress tracking, candidate scanning, and garbage collection.
"""

import os
import sys
import time
import json
import shutil
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine_core.recovery import (
    STATE_FILENAME,
    get_base_temp_dir,
    write_recovery_state,
    update_recovery_progress,
    read_recovery_state,
    delete_recovery_state,
    scan_incomplete_downloads,
    cleanup_stale_temp_dirs,
)
from engine_core.utils import cleanup_filesystem_path, is_valid_segment_file
from ui.controllers.recovery import RecoveryControllerMixin
from ui.controllers.resolve import ResolveControllerMixin
from engine import VideoDownloadEngine


class _FakeEntry:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def delete(self, *_args):
        self.value = ""

    def insert(self, _index, value):
        self.value = value


class _FakeOption:
    def __init__(self):
        self.value = ""
        self.values = []

    def get(self):
        return self.value

    def set(self, value):
        self.value = value

    def configure(self, **kwargs):
        if "values" in kwargs:
            self.values = kwargs["values"]


class _FakeLabel:
    def __init__(self):
        self.text = ""

    def configure(self, **kwargs):
        self.text = kwargs.get("text", self.text)

    def cget(self, key):
        return self.text if key == "text" else None


class TestTempRecovery(unittest.TestCase):

    def setUp(self):
        self.test_root = tempfile.mkdtemp(prefix="vdp_test_recovery_")

    def tearDown(self):
        if os.path.exists(self.test_root):
            shutil.rmtree(self.test_root, ignore_errors=True)

    def test_write_and_read_recovery_state(self):
        """write_recovery_state should atomically persist state and read_recovery_state should deserialize it."""
        temp_dir = os.path.join(self.test_root, ".temp_test_film")
        os.makedirs(temp_dir, exist_ok=True)

        state_data = {
            "url": "https://example.com/video.m3u8",
            "title": "Test Film 2026",
            "output_filepath": "C:\\Downloads\\Test_Film_2026.mp4",
            "total_segments": 150,
            "downloaded_segments": 42,
            "is_multi_audio": False,
            "raw_url": "https://example.com/watch/film",
        }

        ok = write_recovery_state(temp_dir, state_data)
        self.assertTrue(ok)
        self.assertTrue(os.path.exists(os.path.join(temp_dir, STATE_FILENAME)))

        read_data = read_recovery_state(temp_dir)
        self.assertIsNotNone(read_data)
        self.assertEqual(read_data["title"], "Test Film 2026")
        self.assertEqual(read_data["total_segments"], 150)
        self.assertEqual(read_data["downloaded_segments"], 42)
        self.assertEqual(read_data["url"], "https://example.com/video.m3u8")
        self.assertIn("timestamp", read_data)

    def test_update_recovery_progress(self):
        """update_recovery_progress should update downloaded_segments without corrupting other fields."""
        temp_dir = os.path.join(self.test_root, ".temp_update_test")
        os.makedirs(temp_dir, exist_ok=True)

        write_recovery_state(temp_dir, {
            "url": "https://example.com/stream.m3u8",
            "title": "Series S01E01",
            "total_segments": 80,
            "downloaded_segments": 10,
        })

        # Update progress to 45 segments
        updated = update_recovery_progress(temp_dir, 45)
        self.assertTrue(updated)

        state = read_recovery_state(temp_dir)
        self.assertEqual(state["downloaded_segments"], 45)
        self.assertEqual(state["title"], "Series S01E01")
        self.assertEqual(state["total_segments"], 80)

    def test_delete_recovery_state(self):
        """delete_recovery_state should delete the state file cleanly."""
        temp_dir = os.path.join(self.test_root, ".temp_del_test")
        os.makedirs(temp_dir, exist_ok=True)

        write_recovery_state(temp_dir, {"title": "Delete Me", "total_segments": 5})
        self.assertTrue(os.path.exists(os.path.join(temp_dir, STATE_FILENAME)))

        deleted = delete_recovery_state(temp_dir)
        self.assertTrue(deleted)
        self.assertFalse(os.path.exists(os.path.join(temp_dir, STATE_FILENAME)))

    def test_resume_candidate_targets_film_entry_and_marks_automatic_download(self):
        candidate = {
            "url": "https://site.test/current-episode",
            "output_filepath": "C:\\Videos\\current-episode.mp4",
            "title": "Current Episode",
            "downloaded_segments": 12,
            "total_segments": 40,
        }
        controller = SimpleNamespace(
            entry_url=_FakeEntry("https://site.test/social-tab"),
            entry_film_page=_FakeEntry("https://site.test/previous-resolution"),
            entry_output=_FakeEntry(),
            _show_page=MagicMock(),
            _log=MagicMock(),
            _set_status=MagicMock(),
            _resolve_film_threaded=MagicMock(),
        )

        RecoveryControllerMixin._resume_incomplete_candidate(controller, candidate)

        self.assertEqual(controller.entry_film_page.get(), candidate["url"])
        self.assertEqual(controller.entry_url.get(), "https://site.test/social-tab")
        self.assertEqual(controller.entry_output.get(), candidate["output_filepath"])
        self.assertIs(controller._recovery_resume_candidate, candidate)
        controller._resolve_film_threaded.assert_called_once_with()

    def test_successful_recovery_resolution_preserves_output_and_starts_download(self):
        candidate = {
            "url": "https://site.test/current-episode",
            "output_filepath": "C:\\Videos\\custom-name.mp4",
        }
        resolved = {
            "success": True,
            "title": "Server Title",
            "video_url": "https://cdn.test/high.m3u8",
            "video_segments": ["https://cdn.test/seg-1.ts"],
            "total_segments": 1,
            "video_headers": {},
            "audio_tracks": [],
            "qualities": [],
            "subtitles": [],
        }

        class ImmediateThread:
            def __init__(self, target, **_kwargs):
                self.target = target

            def start(self):
                self.target()

        controller = SimpleNamespace(
            entry_film_page=_FakeEntry(candidate["url"]),
            entry_output=_FakeEntry(candidate["output_filepath"]),
            btn_resolve=MagicMock(),
            btn_start=MagicMock(),
            lbl_resolved_title=_FakeLabel(),
            lbl_resolved_url=_FakeLabel(),
            opt_quality=_FakeOption(),
            opt_audio_track=_FakeOption(),
            custom_headers={},
            resolved_film_data={"title": "Stale Result"},
            _recovery_resume_candidate=candidate,
            _log=MagicMock(),
            _set_status=MagicMock(),
            _set_film_meta=MagicMock(),
            _set_film_state=MagicMock(),
            _show_resolution_modal=MagicMock(),
            _start_film_download_threaded=MagicMock(),
            after=lambda _delay, callback: callback(),
            after_idle=lambda callback: callback(),
        )

        with patch("ui.controllers.resolve.threading.Thread", ImmediateThread), patch(
            "ui.controllers.resolve.resolve_film_page", return_value=resolved
        ):
            ResolveControllerMixin._resolve_film_threaded(controller)

        self.assertEqual(controller.entry_output.get(), candidate["output_filepath"])
        controller._start_film_download_threaded.assert_called_once_with()
        controller._show_resolution_modal.assert_not_called()
        self.assertFalse(hasattr(controller, "_recovery_resume_candidate"))

    def test_engine_recovery_state_keeps_original_page_url(self):
        captured_states = []
        engine = VideoDownloadEngine()
        engine.download_stream_segments = MagicMock(return_value=(0, 0, ["missing"]))

        with patch(
            "engine_core.pipeline.write_recovery_state",
            side_effect=lambda _temp_dir, state: captured_states.append(state) or True,
        ):
            success, _message = engine.run_download(
                sample_url="https://cdn.test/segment-000.ts",
                output_filepath=os.path.join(self.test_root, "recoverable.mp4"),
                segment_urls=["https://cdn.test/segment-000.ts"],
                total_segments=1,
                recovery_url="https://site.test/show/episode-1",
            )

        self.assertFalse(success)
        self.assertEqual(captured_states[0]["url"], "https://cdn.test/segment-000.ts")
        self.assertEqual(captured_states[0]["raw_url"], "https://site.test/show/episode-1")

    def test_scan_incomplete_downloads_finds_candidates(self):
        """scan_incomplete_downloads should detect folders with valid .vdp_state.json and segment files."""
        base_temp = os.path.join(self.test_root, ".vdp_temp")
        os.makedirs(base_temp, exist_ok=True)

        # 1. Candidate: 30 of 100 segments downloaded
        dir_cand = os.path.join(base_temp, ".temp_crashed_film")
        os.makedirs(dir_cand, exist_ok=True)
        write_recovery_state(dir_cand, {
            "url": "https://site.com/movie.m3u8",
            "title": "Crashed Movie",
            "output_filepath": os.path.join(self.test_root, "Crashed_Movie.mp4"),
            "total_segments": 100,
            "downloaded_segments": 30,
            "timestamp": time.time() - 600,
        })
        # Create some dummy valid segment files (>= 16 bytes, not m3u8/html)
        valid_chunk = b"G" + (b"\x00" * 187)  # standard MPEG-TS sync packet header
        for i in range(30):
            with open(os.path.join(dir_cand, f"seg_{i:07d}.tmp"), "wb") as f:
                f.write(valid_chunk * 10)

        # 2. Ignored: Completed movie whose output file already exists
        dir_comp = os.path.join(base_temp, ".temp_finished_film")
        os.makedirs(dir_comp, exist_ok=True)
        dummy_out = os.path.join(self.test_root, "Finished_Movie.mp4")
        with open(dummy_out, "wb") as f:
            f.write(b"0" * (2 * 1024 * 1024))  # 2 MB finished file
        write_recovery_state(dir_comp, {
            "title": "Finished Movie",
            "output_filepath": dummy_out,
            "total_segments": 50,
            "downloaded_segments": 50,
            "timestamp": time.time() - 3600,
        })

        # 3. Ignored: Directory with no state file
        dir_empty = os.path.join(base_temp, ".temp_no_state")
        os.makedirs(dir_empty, exist_ok=True)

        candidates = scan_incomplete_downloads(base_dirs=[base_temp])
        self.assertEqual(len(candidates), 1)
        c = candidates[0]
        self.assertEqual(c["title"], "Crashed Movie")
        self.assertEqual(c["total_segments"], 100)
        self.assertEqual(c["downloaded_segments"], 30)
        self.assertTrue(c["bytes_on_disk"] > 0)
        self.assertTrue(c["size_mb"] > 0)

    def test_cleanup_stale_temp_dirs(self):
        """cleanup_stale_temp_dirs should purge orphaned directories without state and sessions older than 48 hours."""
        base_temp = os.path.join(self.test_root, ".vdp_temp")
        os.makedirs(base_temp, exist_ok=True)

        # 1. Orphaned directory without state, older than 2 hours
        dir_old_orphan = os.path.join(base_temp, ".temp_old_orphan")
        os.makedirs(dir_old_orphan, exist_ok=True)
        with open(os.path.join(dir_old_orphan, "junk.tmp"), "wb") as f:
            f.write(b"x" * 1024)
        old_time = time.time() - 10000  # ~2.7 hours ago
        os.utime(dir_old_orphan, (old_time, old_time))

        # 2. Incomplete download with state, but older than 48 hours (e.g. 60 hours)
        dir_ancient = os.path.join(base_temp, ".temp_ancient_movie")
        os.makedirs(dir_ancient, exist_ok=True)
        with open(os.path.join(dir_ancient, "seg_0000000.tmp"), "wb") as f:
            f.write(b"x" * 2048)
        write_recovery_state(dir_ancient, {
            "title": "Ancient Movie",
            "total_segments": 50,
            "downloaded_segments": 5,
            "timestamp": time.time() - (60 * 3600),
        })

        # 3. Recent incomplete download (1 hour ago) -> MUST BE PRESERVED
        dir_fresh = os.path.join(base_temp, ".temp_fresh_movie")
        os.makedirs(dir_fresh, exist_ok=True)
        with open(os.path.join(dir_fresh, "seg_0000000.tmp"), "wb") as f:
            f.write(b"x" * 4096)
        write_recovery_state(dir_fresh, {
            "title": "Fresh Movie",
            "total_segments": 100,
            "downloaded_segments": 10,
            "timestamp": time.time() - 3600,
        })

        cleaned_count, freed_bytes = cleanup_stale_temp_dirs(base_dirs=[base_temp], max_age_hours=48.0)
        self.assertEqual(cleaned_count, 2)
        self.assertTrue(freed_bytes >= 3072)
        self.assertFalse(os.path.exists(dir_old_orphan))
        self.assertFalse(os.path.exists(dir_ancient))
        self.assertTrue(os.path.exists(dir_fresh))


if __name__ == "__main__":
    unittest.main()
