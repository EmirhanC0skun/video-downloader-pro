# -*- coding: utf-8 -*-
"""
Mock Extractor Tests (100% Offline / Zero Network).
Uses unittest.mock to simulate network responses and verify extractor behavior.
"""

import unittest
import os
import sys
from unittest.mock import patch, MagicMock

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from extractor import resolve_film_page, decrypt_cryptojs_aes, unpack_js
from tests.fixtures import (
    SAMPLE_MASTER_M3U8,
    SAMPLE_MEDIA_M3U8,
    SAMPLE_HTML_WITH_JWPLAYER,
    SAMPLE_HTML_WITH_IFRAME
)


class TestMockExtractors(unittest.TestCase):

    @patch("requests.Session.get")
    def test_resolve_film_page_direct_m3u8(self, mock_get):
        """Resolving a direct master.m3u8 URL extracts streams and tracks offline."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = SAMPLE_MASTER_M3U8
        mock_get.return_value = mock_response

        res = resolve_film_page("https://stream.example.com/master.m3u8")
        self.assertIsNotNone(res)
        self.assertTrue(res.get("success"))
        self.assertIn("video_url", res)
        self.assertTrue(len(res.get("audio_tracks", [])) >= 2)
        
        # Verify tracks parsed
        track_names = [t["name"] for t in res["audio_tracks"]]
        self.assertIn("Turkish Dubbing", track_names)
        self.assertIn("English Original", track_names)

    @patch("requests.Session.get")
    def test_invalid_or_down_page_graceful_handling(self, mock_get):
        """HTTP connection failure must be handled gracefully without crashing the application."""
        mock_get.side_effect = Exception("Connection Timeout / Offline")

        try:
            res = resolve_film_page("https://nonexistent-site.example.com/video")
            self.assertFalse(res.get("success", False))
        except RuntimeError:
            # Expected behavior when no media stream found
            pass

    @patch("requests.Session.get")
    def test_resolve_vidmoly_embed(self, mock_get):
        """VidMoly embed resolution extracts HLS m3u8 stream from page HTML."""
        from extractor import resolve_vidmoly_embed
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = 'sources: [{file: "https://vidmoly.to/stream/master.m3u8"}]'
        mock_get.return_value = mock_resp

        res = resolve_vidmoly_embed("https://vidmoly.to/embed-xyz.html")
        self.assertEqual(res, "https://vidmoly.to/stream/master.m3u8")

    @patch("requests.Session.get")
    def test_resolve_voe_embed(self, mock_get):
        """VOE embed resolution extracts HLS stream from sources object."""
        from extractor import resolve_voe_embed
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = 'let sources = {"hls": "https://delivery.voe.sx/engine/hls/master.m3u8"};'
        mock_get.return_value = mock_resp

        res = resolve_voe_embed("https://voe.sx/e/xyz123")
        self.assertEqual(res, "https://delivery.voe.sx/engine/hls/master.m3u8")

    @patch("requests.Session.get")
    def test_resolve_streamwish_embed(self, mock_get):
        """StreamWish embed resolution extracts file URL from player config."""
        from extractor import resolve_streamwish_embed
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = 'sources: [{file: "https://streamwish.to/hls/test.m3u8"}]'
        mock_get.return_value = mock_resp

        res = resolve_streamwish_embed("https://streamwish.to/e/sw123")
        self.assertEqual(res, "https://streamwish.to/hls/test.m3u8")

    @patch("requests.Session.get")
    def test_resolve_sibnet_embed(self, mock_get):
        """Sibnet embed resolution constructs direct MP4 URL from /v/ slug."""
        from extractor import resolve_sibnet_embed
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '<video src="/v/sibnet_sample_12345.mp4"></video>'
        mock_get.return_value = mock_resp

        res = resolve_sibnet_embed("https://video.sibnet.ru/shell.php?videoid=12345")
        self.assertEqual(res, "https://video.sibnet.ru/v/sibnet_sample_12345.mp4")

    @patch("requests.Session.get")
    def test_resolve_closeload_embed(self, mock_get):
        """CloseLoad embed resolution extracts m3u8 playlist URL."""
        from extractor import resolve_closeload_embed
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = 'var file = "https://closeload.com/stream/index.m3u8";'
        mock_get.return_value = mock_resp

        res = resolve_closeload_embed("https://closeload.com/embed/cl123")
        self.assertIsNotNone(res)
        self.assertEqual(res.get("video_url"), "https://closeload.com/stream/index.m3u8")

    def test_cryptojs_aes_and_unpack_js_roundtrip(self):
        """Evaluates decrypt_cryptojs_aes and unpack_js utility functions."""
        self.assertEqual(decrypt_cryptojs_aes("", "pass"), "")
        self.assertEqual(decrypt_cryptojs_aes("not_base64", "pass"), "")
        
        packed = "eval(function(p,a,c,k,e,d){return p}('0 1',2,2,'hello|world'.split('|')))"
        unpacked = unpack_js(packed)
        self.assertIn("hello", unpacked)
        self.assertIn("world", unpacked)


if __name__ == "__main__":
    unittest.main()
