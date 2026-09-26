# -*- coding: utf-8 -*-
"""
Video Downloader Pro — Sibnet Embed Extractor.
Resolves video.sibnet.ru MP4 video streams.
"""

import re
from urllib.parse import urljoin
import requests
from extractors.base import BaseExtractor, ExtractorResult
from logger import get_logger

logger = get_logger("extractors.embeds.sibnet")


def resolve_sibnet_embed(embed_url, session=None, headers=None):
    """Sibnet (video.sibnet.ru) MP4 video akışını çözer."""
    session = session or requests.Session()
    req_headers = dict(headers or {})
    req_headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": embed_url
    })
    try:
        r = session.get(embed_url, headers=req_headers, timeout=10)
        if r.status_code == 200:
            slug_m = re.search(r'["\'](/v/[^"\']+\.mp4)["\']', r.text)
            if slug_m:
                return urljoin("https://video.sibnet.ru", slug_m.group(1))
    except Exception as e:
        logger.debug(f"resolve_sibnet_embed error: {e}")
    return None


class SibnetExtractor(BaseExtractor):
    """Strategy extractor for Sibnet MP4 embeds."""

    @property
    def name(self) -> str:
        return "Sibnet Embed"

    def can_handle(self, url: str) -> bool:
        low = url.lower()
        return "sibnet.ru" in low or "sibnet" in low

    def extract(self, url: str, session=None, log_callback=None) -> ExtractorResult:
        self.log(f"[+] Sibnet embed çözülüyor: {url}", log_callback)
        mp4_url = resolve_sibnet_embed(url, session=session)
        if not mp4_url:
            return None

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": url
        }
        return ExtractorResult(
            success=True,
            title="Sibnet Video",
            video_url=mp4_url,
            video_headers=headers,
            audio_tracks=[],
            subtitles=[],
            total_segments=1,
            direct_file=True,
            raw_url=url
        )


__all__ = ["SibnetExtractor", "resolve_sibnet_embed"]
