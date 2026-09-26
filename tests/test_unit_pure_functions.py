# -*- coding: utf-8 -*-
"""
Pure Function Unit Tests (100% Offline / Zero Network).
Tests parsing, crypto, string transforms, unpack_js, and subtitle conversions.
"""

import unittest
import os
import sys
import re

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine import vtt_to_srt, sanitize_filename, format_human_duration, format_human_filesize
from extractors.generic_hls import decrypt_cryptojs_aes, unpack_js
from tests.fixtures import SAMPLE_VTT_SUBTITLE, SAMPLE_CURL_COMMAND


class TestPureFunctions(unittest.TestCase):
    
    def test_vtt_to_srt_conversion(self):
        """VTT to SRT subtitle format conversion test."""
        srt = vtt_to_srt(SAMPLE_VTT_SUBTITLE)
        
        self.assertIn("00:00:01,500 --> 00:00:04,000", srt)
        self.assertIn("00:00:04,500 --> 00:00:08,200", srt)
        self.assertIn("Video Downloader Pro Test Altyazısı", srt)
        self.assertNotIn("WEBVTT", srt)

    def test_vtt_to_srt_empty_or_none(self):
        """Empty or None VTT input returns empty string gracefully."""
        self.assertEqual(vtt_to_srt(""), "")
        self.assertEqual(vtt_to_srt(None), "")

    def test_filename_sanitization(self):
        """Disallowed OS characters and player-breaking commas/semicolons must be stripped while preserving Turkish chars."""
        unsafe_title = 'Ted Lasso: 4. Sezon 3. Bölüm <Full HD> | 2026? / *Türkçe Dublaj*, Altyazılı &amp; Özel \\'
        safe_title = sanitize_filename(unsafe_title)
        
        forbidden_chars = set('\\/*?:"<>|\x00\x1f,;')
        self.assertFalse(any(c in safe_title for c in forbidden_chars))
        self.assertTrue(len(safe_title) > 0)
        self.assertIn("Ted Lasso", safe_title)
        self.assertIn("4. Sezon 3. Bölüm", safe_title)
        self.assertIn("Türkçe Dublaj", safe_title)
        self.assertIn("Altyazılı", safe_title)
        self.assertIn("& Özel", safe_title)
        self.assertNotIn("<Full HD>", safe_title)
        self.assertNotIn("&amp;", safe_title)
        self.assertNotIn(",", safe_title)

    def test_filename_sanitization_edge_cases(self):
        """Test edge cases: empty strings, reserved Windows names, trailing dots, length limits."""
        self.assertEqual(sanitize_filename(""), "film")
        self.assertEqual(sanitize_filename(None), "film")
        self.assertEqual(sanitize_filename("CON"), "_CON")
        self.assertEqual(sanitize_filename("prn"), "_prn")
        self.assertEqual(sanitize_filename("Film Adı... "), "Film Adı")
        
        long_title = "Çok Uzun Film Başlığı " * 10
        sanitized = sanitize_filename(long_title, max_length=50)
        self.assertLessEqual(len(sanitized), 50)
        self.assertTrue(sanitized.startswith("Çok Uzun"))

    def test_format_human_duration(self):
        """Human duration formatting tests."""
        self.assertEqual(format_human_duration(0), "0 sn")
        self.assertEqual(format_human_duration(45), "45 sn")
        self.assertEqual(format_human_duration(60), "1 dk")
        self.assertEqual(format_human_duration(125), "2 dk 5 sn")
        self.assertEqual(format_human_duration(3600), "1 sa")
        self.assertEqual(format_human_duration(3750), "1 sa 2 dk")
        self.assertEqual(format_human_duration(-5), "")

    def test_format_human_filesize(self):
        """Human file size formatting tests."""
        self.assertEqual(format_human_filesize(512), "0.5 KB")
        self.assertEqual(format_human_filesize(1024 * 1024 * 15), "15.00 MB")
        self.assertEqual(format_human_filesize(int(1024 * 1024 * 1024 * 2.45)), "2.45 GB")
        self.assertEqual(format_human_filesize(-1), "")

    def test_cryptojs_aes_empty_or_invalid(self):
        """CryptoJS AES decrypt gracefully handles empty/invalid ciphertext."""
        self.assertEqual(decrypt_cryptojs_aes("", "dummy_pass"), "")
        self.assertEqual(decrypt_cryptojs_aes(None, "dummy_pass"), "")
        self.assertEqual(decrypt_cryptojs_aes("invalid_base64", "dummy_pass"), "")

    def test_unpack_js_eval_packer(self):
        """Unpack eval(function(p,a,c,k,e,d)...) obfuscated JavaScript."""
        packed = '}("0 1 2",3,3,"hello|world|test".split("|"))'
        unpacked = unpack_js(packed)
        self.assertIn("hello", unpacked)
        self.assertIn("world", unpacked)

    def test_curl_command_parsing(self):
        """Extract URL and headers from a raw cURL command."""
        url_match = re.search(r"curl\s+['\"]([^'\"]+)['\"]", SAMPLE_CURL_COMMAND)
        self.assertIsNotNone(url_match)
        self.assertEqual(url_match.group(1), "https://video.example.com/stream/hls/master.m3u8")
        
        headers = {}
        header_matches = re.findall(r"-H\s+['\"]([^:]+):\s*([^'\"]+)['\"]", SAMPLE_CURL_COMMAND)
        for k, v in header_matches:
            headers[k.strip()] = v.strip()
            
    def test_format_seconds(self):
        """Test formatting of elapsed/remaining seconds into mm:ss or hh:mm:ss."""
        from gui import format_seconds
        self.assertEqual(format_seconds(0), "00:00")
        self.assertEqual(format_seconds(45), "00:45")
        self.assertEqual(format_seconds(65), "01:05")
        self.assertEqual(format_seconds(3665), "01:01:05")
        self.assertEqual(format_seconds(None), "--:--")
        self.assertEqual(format_seconds(-10), "--:--")


if __name__ == "__main__":
    unittest.main()
