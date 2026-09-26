# -*- coding: utf-8 -*-
"""
Logging System and Exception Hierarchy Tests (100% Offline / Zero Network).
Verifies structured logging, UI log dispatching, and custom domain exceptions.
"""

import unittest
import os
import sys
import logging
import subprocess

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from logger import get_logger, register_ui_log_listener, unregister_ui_log_listener
from exceptions import (
    VideoDownloaderError,
    ExtractorError,
    ISPBlockError,
    DecryptionError,
    DownloadError,
    SegmentDownloadError,
    MuxingError,
    FFmpegNotFoundError,
    CancelledError
)


class TestLoggingAndExceptions(unittest.TestCase):

    def test_console_logging_survives_legacy_windows_codepage(self):
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "cp1254:strict"
        script = (
            "import sys; "
            f"sys.path.insert(0, {project_root!r}); "
            "import logger; "
            "logger.configure_logging(log_to_file=False).info('emoji: \\U0001f3af')"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            timeout=15,
            env=env,
        )
        self.assertEqual(result.returncode, 0)
        self.assertNotIn(b"Logging error", result.stderr)
    
    def test_component_loggers(self):
        """Component loggers inherit root namespace and log levels correctly."""
        eng_log = get_logger("engine")
        ext_log = get_logger("extractor")
        hist_log = get_logger("history")

        self.assertEqual(eng_log.name, "video_downloader.engine")
        self.assertEqual(ext_log.name, "video_downloader.extractor")
        self.assertEqual(hist_log.name, "video_downloader.history")

    def test_ui_log_listener_dispatch(self):
        """Messages emitted through logger are dispatched to registered UI listeners."""
        received_logs = []
        def my_ui_callback(lvl, formatted, raw):
            received_logs.append((lvl, raw))

        register_ui_log_listener(my_ui_callback)
        test_logger = get_logger("test_ui")
        test_logger.info("Canlı UI Test Bildirimi")

        unregister_ui_log_listener(my_ui_callback)
        test_logger.info("Bu mesaj yakalanmamalı")

        self.assertTrue(len(received_logs) >= 1)
        self.assertEqual(received_logs[0][0], "INFO")
        self.assertEqual(received_logs[0][1], "Canlı UI Test Bildirimi")

    def test_configure_logging(self):
        """Configuring logging registers file, console, and UI handlers."""
        from logger import configure_logging
        root = configure_logging(level=logging.DEBUG, log_to_file=True)
        self.assertIsNotNone(root)
        self.assertTrue(len(root.handlers) >= 2)

    def test_exception_hierarchy(self):
        """All domain-specific exceptions inherit from VideoDownloaderError."""
        self.assertTrue(issubclass(ExtractorError, VideoDownloaderError))
        self.assertTrue(issubclass(ISPBlockError, ExtractorError))
        self.assertTrue(issubclass(DecryptionError, ExtractorError))
        self.assertTrue(issubclass(DownloadError, VideoDownloaderError))
        self.assertTrue(issubclass(SegmentDownloadError, DownloadError))
        self.assertTrue(issubclass(MuxingError, VideoDownloaderError))
        self.assertTrue(issubclass(FFmpegNotFoundError, MuxingError))
        self.assertTrue(issubclass(CancelledError, VideoDownloaderError))

    def test_exception_formatting_and_details(self):
        """Exceptions format error details and failed segment indices cleanly."""
        base_err = VideoDownloaderError("Base error without details")
        self.assertEqual(str(base_err), "Base error without details")

        err = SegmentDownloadError("Failed downloading 3 segments", failed_indices=[4, 5, 6])
        self.assertEqual(err.failed_indices, [4, 5, 6])
        self.assertIn("failed_indices", str(err))

        isp_err = ISPBlockError("Site blocked", details={"host": "test.com"})
        self.assertIn("test.com", str(isp_err))


if __name__ == "__main__":
    unittest.main()
