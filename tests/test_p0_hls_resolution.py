"""P0 behavior tests for master-to-media HLS resolution."""

from __future__ import annotations

from dataclasses import dataclass

from extractors.base import BaseExtractor


@dataclass
class _Response:
    status_code: int
    text: str
    url: str


class _Session:
    def __init__(self, responses: dict[str, _Response]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, str]]] = []

    def get(self, url: str, headers: dict[str, str], timeout: int, allow_redirects: bool) -> _Response:
        self.calls.append((url, dict(headers)))
        return self.responses[url]


class _Extractor(BaseExtractor):
    @property
    def name(self) -> str:
        return "test"

    def can_handle(self, url: str) -> bool:
        return True

    def extract(self, url: str, session=None, log_callback=None):
        return None


def test_master_playlist_chooses_highest_bandwidth_even_when_it_is_not_last() -> None:
    """Master playlist order must not decide which media playlist becomes segments."""
    master_url = "https://cdn.example.test/hls/master.m3u8"
    high_url = "https://cdn.example.test/hls/high/index.m3u8"
    low_url = "https://cdn.example.test/hls/low/index.m3u8"
    headers = {"Referer": "https://player.example.test/", "Origin": "https://player.example.test"}
    session = _Session({
        master_url: _Response(200, """#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=6000000,RESOLUTION=1920x1080
high/index.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=640x360
low/index.m3u8
""", master_url),
        high_url: _Response(200, """#EXTM3U
#EXT-X-MAP:URI=\"init.mp4\"
#EXTINF:6.0,
seg-1.m4s
#EXTINF:6.0,
seg-2.m4s
""", high_url),
        low_url: _Response(200, "#EXTM3U\n#EXTINF:6.0,\nlow.m4s\n", low_url),
    })

    segments = _Extractor()._resolve_m3u8_segments(session, master_url, headers)

    assert segments == [
        "https://cdn.example.test/hls/high/init.mp4",
        "https://cdn.example.test/hls/high/seg-1.m4s",
        "https://cdn.example.test/hls/high/seg-2.m4s",
    ]
    assert [url for url, _ in session.calls] == [master_url, high_url]
    assert all(request_headers == headers for _, request_headers in session.calls)
