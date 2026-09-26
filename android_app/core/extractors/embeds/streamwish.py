# -*- coding: utf-8 -*-
"""
Video Downloader Pro — StreamWish & FileLions Embed Extractor.
Resolves streamwish.to, filelions.to, swish.to, and related video mirrors.
"""

import re
import requests
from extractors.base import BaseExtractor, ExtractorResult
from extractors.generic_hls import unpack_js
from logger import get_logger

logger = get_logger("extractors.embeds.streamwish")


def resolve_streamwish_embed(embed_url, session=None, headers=None):
    """StreamWish & FileLions (streamwish.to, filelions.to, swish.to, filelions.online) akışını çözer."""
    session = session or requests.Session()
    req_headers = dict(headers or {})
    req_headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": embed_url
    })
    try:
        r = session.get(embed_url, headers=req_headers, timeout=10)
        if r.status_code == 200:
            text = r.text
            if "eval(function(p,a,c,k,e,d" in text:
                text += "\n" + unpack_js(text)
            m3u8_m = re.findall(r'["\'](https?://[^"\']+\.m3u8[^"\']*)["\']', text)
            if m3u8_m:
                return m3u8_m[0]
            file_m = re.search(r'(?:file|source|src)\s*:\s*["\'](https?://[^"\']+)["\']', text)
            if file_m:
                return file_m.group(1)
    except Exception as e:
        logger.debug(f"resolve_streamwish_embed error: {e}")
    return None


class StreamwishExtractor(BaseExtractor):
    """Strategy extractor for StreamWish and FileLions embeds."""

    @property
    def name(self) -> str:
        return "StreamWish Embed"

    def can_handle(self, url: str) -> bool:
        low = url.lower()
        return any(k in low for k in ["streamwish", "filelions", "swish.", "filelion"])

    def extract(self, url: str, session=None, log_callback=None) -> ExtractorResult:
        self.log(f"[+] StreamWish embed çözülüyor: {url}", log_callback)
        stream_url = resolve_streamwish_embed(url, session=session)
        if not stream_url:
            return None

        is_direct = not (".m3u8" in stream_url)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": url
        }
        return ExtractorResult(
            success=True,
            title="StreamWish Video",
            video_url=stream_url,
            video_headers=headers,
            audio_tracks=[],
            subtitles=[],
            total_segments=0,
            direct_file=is_direct,
            raw_url=url
        )


__all__ = ["StreamwishExtractor", "resolve_streamwish_embed"]
