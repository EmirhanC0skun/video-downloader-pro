"""P0 regression for audio master-playlist selection in the download pipeline."""

from __future__ import annotations

import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from engine import VideoDownloadEngine


class _AudioManifestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        self.server.requests_seen.append((self.path, dict(self.headers)))
        payloads = {
            "/audio/master.m3u8": b"""#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=96000
low.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=192000
high.m3u8
""",
            "/audio/high.m3u8": b"""#EXTM3U
#EXT-X-MAP:URI=\"init.mp4\"
#EXTINF:6.0,
segment-1.m4s
#EXTINF:6.0,
segment-2.m4s
""",
            "/audio/low.m3u8": b"""#EXTM3U
#EXTINF:6.0,
low-segment.m4s
""",
        }
        body = payloads.get(self.path)
        if body is None:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/vnd.apple.mpegurl")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


class TestAudioMasterPlaylist(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _AudioManifestHandler)
        cls.httpd.requests_seen = []
        cls.server_thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.server_thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.httpd.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.server_thread.join(timeout=5)

    def setUp(self) -> None:
        self.httpd.requests_seen.clear()

    def test_audio_master_uses_highest_variant_media_segments(self) -> None:
        """Audio master child playlists must be resolved before download tasks are built."""
        engine = VideoDownloadEngine()
        captured_calls = []
        headers = {
            "Referer": "https://player.example/episode",
            "Origin": "https://player.example",
            "User-Agent": "VDP-P0-Test/1.0",
        }

        def write_segment_samples(tasks, request_headers, thread_count, progress_callback=None, log_callback=None):
            captured_calls.append((list(tasks), dict(request_headers)))
            downloaded = 0
            for _, _, path in tasks:
                Path(path).write_bytes(b"segment-data-" * 64)
                downloaded += Path(path).stat().st_size
            return len(tasks), downloaded, []

        video_url = f"{self.base_url}/video-segment.ts"
        audio_master_url = f"{self.base_url}/audio/master.m3u8"
        with tempfile.TemporaryDirectory() as temp_dir, \
             patch.object(engine, "download_stream_segments", side_effect=write_segment_samples), \
             patch.object(engine, "mux_multi_audio_and_video", return_value=True):
            ok, result = engine.run_multi_audio_download(
                video_url=video_url,
                video_segments=[video_url],
                audio_tracks=[{
                    "name": "Türkçe Dublaj",
                    "lang": "tur",
                    "sample_segment_url": audio_master_url,
                    "headers": headers,
                }],
                output_filepath=str(Path(temp_dir) / "output.mp4"),
                video_headers=headers,
                thread_count=4,
            )

        self.assertTrue(ok, result)
        audio_tasks = [
            task
            for tasks, _ in captured_calls
            for task in tasks
            if "/audio/" in task[1]
        ]
        self.assertEqual(
            [task[1] for task in audio_tasks],
            [
                f"{self.base_url}/audio/init.mp4",
                f"{self.base_url}/audio/segment-1.m4s",
                f"{self.base_url}/audio/segment-2.m4s",
            ],
        )
        self.assertTrue(all(not task[1].endswith(".m3u8") for task in audio_tasks))
        self.assertFalse(any(path == "/audio/low.m3u8" for path, _ in self.httpd.requests_seen))

        manifest_requests = [
            request_headers
            for path, request_headers in self.httpd.requests_seen
            if path in {"/audio/master.m3u8", "/audio/high.m3u8"}
        ]
        self.assertEqual(len(manifest_requests), 2)
        for request_headers in manifest_requests:
            self.assertEqual(request_headers.get("Referer"), headers["Referer"])
            self.assertEqual(request_headers.get("Origin"), headers["Origin"])
            self.assertEqual(request_headers.get("User-Agent"), headers["User-Agent"])
