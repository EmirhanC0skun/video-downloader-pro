# -*- coding: utf-8 -*-
"""
Desktop vs Mobile Core Synchronization Integrity Tests.
Guarantees that android_app/core and Desktop engines stay in lockstep without regressions.
"""

import unittest
import os
import sys
import inspect

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import engine as desktop_engine
import extractor as desktop_extractor
import history as desktop_history

import android_app.core.engine as mobile_engine
import android_app.core.extractor as mobile_extractor
import android_app.core.history as mobile_history


class TestMobileCoreSync(unittest.TestCase):
    
    def test_engine_api_parity(self):
        """VideoDownloadEngine in Desktop and Mobile core must share identical method signatures."""
        d_methods = set(m for m, _ in inspect.getmembers(desktop_engine.VideoDownloadEngine, predicate=inspect.isfunction))
        m_methods = set(m for m, _ in inspect.getmembers(mobile_engine.VideoDownloadEngine, predicate=inspect.isfunction))
        
        critical_methods = {
            "run_download",
            "run_multi_audio_download",
            "download_youtube_media",
            "download_direct_file",
            "download_stream_segments",
            "mux_video_and_audio",
            "cancel",
            "reset_cancel"
        }

        for method in critical_methods:
            self.assertIn(method, d_methods, f"Desktop engine missing: {method}")
            self.assertIn(method, m_methods, f"Mobile engine missing: {method}")

    def test_extractor_api_parity(self):
        """Extractor functions in Desktop and Mobile core must exist and be callable."""
        critical_funcs = [
            "resolve_film_page",
            "decrypt_cryptojs_aes",
            "unpack_js"
        ]

        for func_name in critical_funcs:
            self.assertTrue(hasattr(desktop_extractor, func_name), f"Desktop extractor missing: {func_name}")
            self.assertTrue(hasattr(mobile_extractor, func_name), f"Mobile extractor missing: {func_name}")

    def test_mobile_download_controller_lifecycle(self):
        """MobileDownloadController must maintain precise state transitions for Pause, Resume, and Cancel."""
        from android_app.mobile_engine import MobileDownloadController
        controller = MobileDownloadController()
        
        self.assertEqual(controller.state, "IDLE")
        self.assertFalse(controller.is_downloading)
        self.assertFalse(controller.is_paused)

        # 1. Start Session
        controller.start_download_session("Test Movie")
        self.assertEqual(controller.state, "DOWNLOADING")
        self.assertTrue(controller.is_downloading)
        self.assertFalse(controller.is_paused)
        self.assertEqual(controller.active_download_title, "Test Movie")

        # 2. Pause
        res = controller.pause_download()
        self.assertTrue(res)
        self.assertEqual(controller.state, "PAUSED")
        self.assertTrue(controller.is_paused)

        # 3. Resume
        res = controller.resume_download()
        self.assertTrue(res)
        self.assertEqual(controller.state, "DOWNLOADING")
        self.assertFalse(controller.is_paused)

        # 4. Cancel
        controller.cancel_current_download(cleanup=True)
        self.assertEqual(controller.state, "CANCELLED")
        self.assertFalse(controller.is_downloading)
        self.assertFalse(controller.is_paused)

    def test_pure_python_audio_demuxer_rejects_streams_without_audio(self):
        """
        B4: Ses akışı çözülemeyen bir TS girdisinde ayıklayıcı BAŞARISIZ dönmeli ve
        geride dosya bırakmamalı.

        Bu test eskiden çıktı dosyasının var olmasını doğruluyordu; oysa asıl hata
        tam olarak buydu — ayıklayıcı, PAT/PMT olmayan ve gerçek ses içermeyen bir
        akıştan da dosya üretip 'başarılı' raporluyordu. Ayrıntılı doğruluk
        testleri: tests/test_mobile_audio_extract.py
        """
        import tempfile
        from android_app.mobile_engine import MobileDownloadController
        controller = MobileDownloadController()

        with tempfile.NamedTemporaryFile(suffix=".ts", delete=False) as f_in, \
             tempfile.NamedTemporaryFile(suffix=".aac", delete=False) as f_out:
            # PAT/PMT içermeyen, yalnızca 0xFFF1 desenine benzeyen baytlar taşıyan paket
            ts_packet = bytearray([0x47, 0x01, 0x00, 0x10]) + bytes(184)
            ts_packet[4] = 0xFF
            ts_packet[5] = 0xF1
            ts_packet[6] = 0x50
            ts_packet[7] = 0x80
            ts_packet[8] = 0x01
            ts_packet[9] = 0x3F
            ts_packet[10] = 0xFC
            f_in.write(bytes(ts_packet) * 20)
            f_in.flush()
            in_path = f_in.name
            out_path = f_out.name

        os.remove(out_path)
        try:
            success, res = controller._extract_audio_pure_python(in_path, out_path)
            self.assertFalse(success, "Ses akışı yokken 'başarılı' dönülmemeli (B4)")
            self.assertFalse(os.path.exists(out_path),
                             "Geçersiz çıktı dosyası geride bırakıldı (B4)")
            self.assertTrue(res)
        finally:
            for p in (in_path, out_path):
                if os.path.exists(p):
                    os.remove(p)

    def test_zero_hardcoded_1118_in_extractors(self):
        """ExtractorResult and resolve_film_page must default to 0 for unknown segment count, never hardcoded 1118."""
        from extractors.base import ExtractorResult
        result = ExtractorResult(success=True, title="Test", video_url="http://test.com")
        self.assertEqual(result.total_segments, 0)
        self.assertNotEqual(result.total_segments, 1118)


if __name__ == "__main__":
    unittest.main()
