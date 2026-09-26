# -*- coding: utf-8 -*-
"""
Video Downloader Pro — VOE Embed Extractor.
Resolves voe.sx and voe-network video streams.
"""

import re
import base64
import requests
from extractors.base import BaseExtractor, ExtractorResult
from logger import get_logger

logger = get_logger("extractors.embeds.voe")


def resolve_voe_embed(embed_url, session=None, headers=None):
    """VOE (voe.sx, voe-network.net) video akışını çözer."""
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
            hls_m = re.search(r'["\']hls["\']\s*:\s*["\'](https?://[^"\']+)["\']', text)
            if hls_m:
                return hls_m.group(1)
            mp4_m = re.search(r'["\']mp4["\']\s*:\s*["\'](https?://[^"\']+)["\']', text)
            if mp4_m:
                return mp4_m.group(1)
            b64_m = re.search(r'let\s+\w+\s*=\s*["\']([a-zA-Z0-9+/=]{50,})["\']', text)
            if b64_m:
                try:
                    dec = base64.b64decode(b64_m.group(1)).decode('utf-8', errors='ignore')
                    if "http" in dec:
                        urls = re.findall(r'https?://[^\s"\'<>]+', dec)
                        if urls:
                            return urls[0]
                except Exception as e:
                    logger.debug(f"VOE base64 decode error: {e}")
    except Exception as e:
        logger.debug(f"resolve_voe_embed error: {e}")
    return None


class VoeExtractor(BaseExtractor):
    """Strategy extractor for VOE embeds."""

    @property
    def name(self) -> str:
        return "VOE Embed"

    def can_handle(self, url: str) -> bool:
        low = url.lower()
        return any(k in low for k in ["voe.sx", "voe-network", "voe."])

    def extract(self, url: str, session=None, log_callback=None) -> ExtractorResult:
        self.log(f"[+] VOE embed çözülüyor: {url}", log_callback)
        stream_url = resolve_voe_embed(url, session=session)
        if not stream_url:
            return None

        is_direct = not (".m3u8" in stream_url)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": url
        }
        return ExtractorResult(
            success=True,
            title="VOE Video",
            video_url=stream_url,
            video_headers=headers,
            audio_tracks=[],
            subtitles=[],
            total_segments=0,
            direct_file=is_direct,
            raw_url=url
        )


__all__ = ["VoeExtractor", "resolve_voe_embed"]
