"""P0 direct-download regressions exercised against a real local HTTP server."""

from __future__ import annotations

import re
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import MagicMock, patch

from engine import VideoDownloadEngine


class _RangeMediaHandler(BaseHTTPRequestHandler):
    """Serves an in-memory media payload and honors byte-range requests."""

    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        payload = self.server.payload
        if self.server.fail_first_request:
            with self.server.state_lock:
                if self.server.request_count == 0:
                    self.server.request_count += 1
                    self.send_response(503)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                self.server.request_count += 1
        elif self.server.truncate_second_request:
            with self.server.state_lock:
                self.server.request_count += 1
                request_number = self.server.request_count
            if request_number >= 2:
                body = payload[:4096]
                self.send_response(200)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(body)
                self.close_connection = True
                return
        range_header = self.headers.get("Range")
        if range_header and not self.server.ignore_ranges:
            match = re.fullmatch(r"bytes=(\d+)-(\d+)", range_header)
            if not match:
                self.send_error(416)
                return
            start, end = (int(value) for value in match.groups())
            if start >= len(payload) or end < start:
                self.send_error(416)
                return
            end = min(end, len(payload) - 1)
            body = payload[start:end + 1]
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{len(payload)}")
        else:
            body = payload
            self.send_response(200)

        self.send_header("Content-Type", "video/mp4")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


class TestParallelRangeDownload(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = (b"VDP-MEDIA-" * 600_000)[:5 * 1024 * 1024 + 4096]
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _RangeMediaHandler)
        cls.httpd.payload = cls.payload
        cls.httpd.ignore_ranges = False
        cls.httpd.fail_first_request = False
        cls.httpd.truncate_second_request = False
        cls.httpd.request_count = 0
        cls.httpd.state_lock = threading.Lock()
        cls.server_thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.server_thread.start()
        cls.url = f"http://127.0.0.1:{cls.httpd.server_port}/video.mp4"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.server_thread.join(timeout=5)

    def test_parallel_range_download_writes_the_original_payload(self) -> None:
        """A >5 MB Range resource must complete through the parallel branch losslessly."""
        engine = VideoDownloadEngine()
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "video.mp4"

            ok, result = engine.download_direct_file(
                self.url,
                str(output_path),
                thread_count=4,
            )

            self.assertTrue(ok, result)
            self.assertEqual(output_path.read_bytes(), self.payload)

    def test_range_ignoring_origin_falls_back_without_duplicate_payload(self) -> None:
        """A 200 response to a Range request must never be concatenated as four full files."""
        self.httpd.ignore_ranges = True
        engine = VideoDownloadEngine()
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                output_path = Path(temp_dir) / "video.mp4"

                ok, result = engine.download_direct_file(
                    self.url,
                    str(output_path),
                    thread_count=4,
                )

                self.assertTrue(ok, result)
                self.assertEqual(output_path.read_bytes(), self.payload)
        finally:
            self.httpd.ignore_ranges = False

    def test_invalid_direct_probe_response_is_closed(self) -> None:
        response = MagicMock()
        response.status_code = 200
        response.headers = {
            "Content-Length": "32",
            "Content-Type": "application/json",
        }
        engine = VideoDownloadEngine()
        engine._session.get = MagicMock(return_value=response)

        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "engine_core.downloader.c_requests", None
        ):
            ok, _result = engine.download_direct_file(
                "https://cdn.example/error.mp4",
                str(Path(temp_dir) / "error.mp4"),
                thread_count=1,
            )

        self.assertFalse(ok)
        response.close.assert_called_once_with()

    def test_transient_cold_probe_failure_is_retried_before_ytdlp_fallback(self) -> None:
        """A cold-origin 503 must not send a valid direct MP4 URL to yt-dlp."""
        self.httpd.fail_first_request = True
        self.httpd.request_count = 0
        engine = VideoDownloadEngine()
        try:
            with tempfile.TemporaryDirectory() as temp_dir, patch(
                "engine_core.downloader.c_requests", None
            ), patch.object(
                engine,
                "download_youtube_media",
                return_value=(False, "yt-dlp must not be needed"),
            ):
                output_path = Path(temp_dir) / "cold-origin.mp4"
                ok, result = engine.download_direct_file(
                    self.url,
                    str(output_path),
                    thread_count=1,
                )

                self.assertTrue(ok, result)
                self.assertEqual(output_path.read_bytes(), self.payload)
        finally:
            self.httpd.fail_first_request = False
            self.httpd.request_count = 0

    def test_truncated_direct_stream_is_rejected_and_removed(self) -> None:
        """A closed response shorter than Content-Length must never report success."""
        self.httpd.truncate_second_request = True
        self.httpd.request_count = 0
        engine = VideoDownloadEngine()
        try:
            with tempfile.TemporaryDirectory() as temp_dir, patch(
                "engine_core.downloader.c_requests", None
            ):
                output_path = Path(temp_dir) / "truncated.mp4"
                ok, _result = engine.download_direct_file(
                    self.url,
                    str(output_path),
                    thread_count=1,
                )

                self.assertFalse(ok)
                self.assertFalse(output_path.exists())
        finally:
            self.httpd.truncate_second_request = False
            self.httpd.request_count = 0
