# -*- coding: utf-8 -*-
"""Unit tests for downloader.py CLI entrypoint."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import downloader


class TestCLIDownloader(unittest.TestCase):

    def test_cli_help(self):
        """CLI --help raises SystemExit with code 0."""
        with patch.object(sys, 'argv', ['downloader.py', '--help']):
            with self.assertRaises(SystemExit) as cm:
                downloader.main_cli()
            self.assertEqual(cm.exception.code, 0)

    @patch('downloader.VideoDownloadEngine')
    def test_cli_run_success(self, mock_engine_cls):
        """CLI executes run_download with provided arguments and succeeds."""
        mock_instance = MagicMock()
        mock_instance.run_download.return_value = (True, "video.mp4")
        mock_engine_cls.return_value = mock_instance

        test_args = [
            'downloader.py',
            '--url', 'https://cdn.example.com/video/seg_001.ts',
            '--output', 'test_out.mp4',
            '--referer', 'https://example.com',
            '--threads', '4',
            '--start', '1',
            '--total', '10',
            '--merge', 'binary',
            '--keep-temp'
        ]

        with patch.object(sys, 'argv', test_args):
            downloader.main_cli()

        mock_instance.run_download.assert_called_once()
        _, kwargs = mock_instance.run_download.call_args
        self.assertEqual(kwargs['sample_url'], 'https://cdn.example.com/video/seg_001.ts')
        self.assertEqual(kwargs['output_filepath'], 'test_out.mp4')
        self.assertEqual(kwargs['referer'], 'https://example.com')
        self.assertEqual(kwargs['thread_count'], 4)
        self.assertEqual(kwargs['start_index'], 1)
        self.assertEqual(kwargs['total_segments'], 10)
        self.assertEqual(kwargs['merge_mode'], 'binary')
        self.assertTrue(kwargs['keep_temp'])

    @patch('downloader.VideoDownloadEngine')
    def test_cli_run_failure(self, mock_engine_cls):
        """CLI exits with code 1 when engine.run_download fails."""
        mock_instance = MagicMock()
        mock_instance.run_download.return_value = (False, "HTTP 403 Forbidden")
        mock_engine_cls.return_value = mock_instance

        test_args = [
            'downloader.py',
            '--url', 'https://cdn.example.com/video/seg_001.ts',
            '--output', 'test_fail.mp4'
        ]

        with patch.object(sys, 'argv', test_args):
            with self.assertRaises(SystemExit) as cm:
                downloader.main_cli()
            self.assertEqual(cm.exception.code, 1)

    @patch('builtins.input', return_value='')
    def test_cli_empty_url_interactive_exit(self, mock_input):
        """CLI prompts for URL interactively and exits if user provides empty string."""
        with patch.object(sys, 'argv', ['downloader.py']):
            with self.assertRaises(SystemExit) as cm:
                downloader.main_cli()
            self.assertEqual(cm.exception.code, 1)

    @patch('downloader.VideoDownloadEngine')
    def test_cli_callbacks(self, mock_engine_cls):
        """Progress and log callbacks in CLI operate without throwing exceptions."""
        mock_instance = MagicMock()
        
        def fake_run(**kwargs):
            prog = kwargs.get('progress_callback')
            log = kwargs.get('log_callback')
            if prog:
                prog(1, 10, 1024 * 1024, 512 * 1024)
                prog(5, 10, 5 * 1024 * 1024, 1024 * 1024)
            if log:
                log("Indiriliyor...")
            return True, "test_cb.mp4"

        mock_instance.run_download.side_effect = fake_run
        mock_engine_cls.return_value = mock_instance

        test_args = [
            'downloader.py',
            '--url', 'https://cdn.example.com/video/seg_001.ts',
            '--output', 'test_cb.mp4'
        ]

        with patch.object(sys, 'argv', test_args):
            downloader.main_cli()


if __name__ == '__main__':
    unittest.main()
