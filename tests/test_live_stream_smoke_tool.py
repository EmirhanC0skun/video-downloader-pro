"""Offline contract tests for the manual live smoke CLI."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_smoke_tool():
    path = Path(__file__).resolve().parents[1] / "tools" / "live_stream_smoke_test.py"
    spec = importlib.util.spec_from_file_location("live_stream_smoke_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_smoke_cli_defaults_to_a_bounded_twelve_media_segment_sample() -> None:
    tool = _load_smoke_tool()

    args = tool.parse_arguments([])

    assert args.segments == 12
    assert args.workers == 4


def test_smoke_cli_accepts_fifty_mib_primary_download_gate() -> None:
    tool = _load_smoke_tool()

    args = tool.parse_arguments(["--target-mib", "50", "--primary-only"])

    assert args.target_mib == 50
    assert args.primary_only is True


def test_live_catalog_has_fifteen_unique_page_targets() -> None:
    tool = _load_smoke_tool()

    names = [target["name"] for target in tool.TARGETS]
    pages = [target["url"] for target in tool.TARGETS]

    assert len(names) == 15
    assert len(set(names)) == 15
    assert len(set(pages)) == 15


def test_direct_probe_downloads_requested_fifty_mib_budget(monkeypatch) -> None:
    tool = _load_smoke_tool()
    requested_headers = {}
    chunk = b"x" * (1024 * 1024)

    class Response:
        status_code = 206
        headers = {"Content-Range": "bytes 0-52428799/100000000"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def iter_content(self, chunk_size):
            assert chunk_size == 64 * 1024
            yield from [chunk] * 50

    def get(_url, headers, **_kwargs):
        requested_headers.update(headers)
        return Response()

    monkeypatch.setattr(tool.requests, "get", get)

    result = tool._direct_range_probe(
        "https://cdn.example/movie.mp4",
        {"Referer": "https://page.example/"},
        timeout=20,
        target_bytes=50 * 1024 * 1024,
    )

    assert requested_headers["Range"] == "bytes=0-52428799"
    assert result["downloaded_bytes"] == 50 * 1024 * 1024
    assert result["ok"] is True


def test_hls_byte_budget_stops_after_first_complete_segment_over_target(tmp_path) -> None:
    tool = _load_smoke_tool()
    downloaded_urls = []

    class Engine:
        def download_stream_segments(self, tasks, **_kwargs):
            for _index, url, path in tasks:
                downloaded_urls.append(url)
                Path(path).write_bytes(b"abc")
            return len(tasks), 3 * len(tasks), []

    result = tool._stream_sample(
        Engine(),
        "video",
        [
            "https://cdn.example/one.ts",
            "https://cdn.example/two.ts",
            "https://cdn.example/three.ts",
        ],
        {},
        tmp_path,
        media_count=12,
        workers=4,
        target_bytes=5,
    )

    assert downloaded_urls == [
        "https://cdn.example/one.ts",
        "https://cdn.example/two.ts",
    ]
    assert result["downloaded_bytes"] == 6
    assert result["ok"] is True


def test_smoke_error_redaction_removes_signed_query_values() -> None:
    tool = _load_smoke_tool()
    error = RuntimeError("failed https://cdn.example/video.ts?token=secret-value&expires=123")

    redacted = tool.redacted_error(error)

    assert "secret-value" not in redacted
    assert "expires=123" not in redacted
    assert "https://cdn.example/video.ts" in redacted


def test_smoke_result_fails_when_a_declared_subtitle_cannot_be_probed() -> None:
    tool = _load_smoke_tool()
    result = {
        "resolve_ok": True,
        "renditions": [{"ok": True}],
        "subtitles": [{"ok": False, "status": 403}],
    }

    assert not tool.result_is_success(result)


def test_smoke_transport_headers_exclude_hls_crypto_metadata() -> None:
    tool = _load_smoke_tool()

    headers = tool._transport_headers(
        tool._safe_headers(
            {
                "video_headers": {
                    "Referer": "https://player.example/",
                    "aes_key": b"0123456789abcdef",
                    "aes_iv": bytes(16),
                }
            }
        )
    )

    assert headers["Referer"] == "https://player.example/"
    assert "aes_key" not in headers
    assert "aes_iv" not in headers
    assert all(isinstance(value, str) for value in headers.values())


def test_muxed_audio_track_is_not_duplicated_as_a_primary_video_rendition() -> None:
    tool = _load_smoke_tool()
    shared_url = "https://cdn.example/seg-001.ts?token=secret"
    audio_tracks = [{"sample_segment_url": shared_url, "segments": [shared_url]}]

    assert not tool.primary_video_is_distinct(shared_url, None, audio_tracks)
    assert not tool.primary_video_is_distinct("", None, audio_tracks)
    assert tool.primary_video_is_distinct(
        "https://cdn.example/video-001.ts",
        None,
        audio_tracks,
    )


def test_muxed_track_manifest_and_primary_segments_are_recognized_as_same_source() -> None:
    tool = _load_smoke_tool()
    first_segment = "https://cdn.example/segment-001.ts"
    audio_tracks = [{
        "url": "https://cdn.example/master.m3u8",
        "sample_segment_url": first_segment,
        "segments": [first_segment],
        "video_url": "https://cdn.example/master.m3u8",
        "video_segments": [first_segment],
    }]

    assert not tool.primary_video_is_distinct(
        "https://cdn.example/master.m3u8",
        [first_segment],
        audio_tracks,
    )
