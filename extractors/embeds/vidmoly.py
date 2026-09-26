# -*- coding: utf-8 -*-
"""
Video Downloader Pro — VidMoly Embed Extractor.
Resolves vidmoly.to, vidmoly.me, and vidmoly.net streams.
"""

import re
import requests
from extractors.base import BaseExtractor, ExtractorResult
from extractors.generic_hls import decrypt_cryptojs_aes, unpack_js
from logger import get_logger

logger = get_logger("extractors.embeds.vidmoly")


def resolve_vidmoly_embed(embed_url, session=None, headers=None):
    """VidMoly (vidmoly.to, vidmoly.me, vidmoly.net) video akışını çözer."""
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
            aes_match = re.search(r'CryptoJS\.AES\.decrypt\(["\'](.*?)["\']\s*,\s*["\'](.*?)["\']\)', text, re.DOTALL)
            if aes_match:
                try:
                    text += "\n" + decrypt_cryptojs_aes(aes_match.group(1), aes_match.group(2))
                except Exception as e:
                    logger.debug(f"Vidmoly AES decrypt error: {e}")
            m3u8_m = re.findall(r'["\'](https?://[^"\']+\.m3u8[^"\']*)["\']', text)
            if m3u8_m:
                return m3u8_m[0]
            file_m = re.search(r'file\s*:\s*["\'](https?://[^"\']+)["\']', text)
            if file_m:
                return file_m.group(1)
    except Exception as e:
        logger.debug(f"resolve_vidmoly_embed error: {e}")
    return None


class VidmolyExtractor(BaseExtractor):
    """Strategy extractor for VidMoly embeds."""

    @property
    def name(self) -> str:
        return "VidMoly Embed"

    def can_handle(self, url: str) -> bool:
        low = url.lower()
        return any(k in low for k in ["vidmoly", "moly."])

    def extract(self, url: str, session=None, log_callback=None) -> ExtractorResult:
        self.log(f"[+] VidMoly embed çözülüyor: {url}", log_callback)
        m3u8_url = resolve_vidmoly_embed(url, session=session)
        if not m3u8_url:
            return None

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": url
        }
        return ExtractorResult(
            success=True,
            title="VidMoly Video",
            video_url=m3u8_url,
            video_headers=headers,
            audio_tracks=[],
            subtitles=[],
            total_segments=0,
            direct_file=False,
            raw_url=url
        )


__all__ = ["VidmolyExtractor", "resolve_vidmoly_embed"]
