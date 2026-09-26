"""P0 regression for keeping HLS decryption metadata out of HTTP headers."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from engine_core.ffmpeg import fetch_and_save_subtitle


class _SubtitleResponse:
    status_code = 200
    content = b"WEBVTT\n\n00:00.000 --> 00:01.000\nMerhaba\n"

    def __bool__(self) -> bool:
        return True

    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _StrictHeaderSession:
    def __init__(self) -> None:
        self.headers_seen = None
        self.response = _SubtitleResponse()
        self.closed = False

    def get(self, url, headers, timeout):
        self.headers_seen = dict(headers)
        assert "aes_key" not in headers
        assert "aes_iv" not in headers
        assert all(isinstance(value, str) for value in headers.values())
        return self.response

    def close(self) -> None:
        self.closed = True


def test_subtitle_fetch_strips_hls_crypto_metadata_from_default_headers() -> None:
    session = _StrictHeaderSession()
    headers = {
        "Referer": "https://player.example/",
        "User-Agent": "VDP-Test",
        "aes_key": b"0123456789abcdef",
        "aes_iv": bytes(16),
    }
    with tempfile.TemporaryDirectory() as temp_dir, patch("engine_core.ffmpeg.c_requests", None):
        subtitle_path = fetch_and_save_subtitle(
            subtitles=[{"name": "Türkçe", "url": "https://cdn.example/subtitle.vtt"}],
            output_filepath=str(Path(temp_dir) / "video.mp4"),
            session=session,
            default_headers=headers,
        )

        assert subtitle_path is not None
        assert Path(subtitle_path).read_text(encoding="utf-8").startswith("1\n00:00:00,000")
    assert session.headers_seen == {
        "Referer": "https://player.example/",
        "User-Agent": "VDP-Test",
    }
    assert session.response.closed is True
    assert session.closed is False


def test_subtitle_fetch_closes_the_session_it_creates() -> None:
    session = _StrictHeaderSession()
    with (
        tempfile.TemporaryDirectory() as temp_dir,
        patch("engine_core.ffmpeg.c_requests", None),
        patch("engine_core.ffmpeg.requests.Session", return_value=session),
    ):
        subtitle_path = fetch_and_save_subtitle(
            subtitles=[{"name": "TÃ¼rkÃ§e", "url": "https://cdn.example/subtitle.vtt"}],
            output_filepath=str(Path(temp_dir) / "video.mp4"),
        )

    assert subtitle_path is not None
    assert session.response.closed is True
    assert session.closed is True
