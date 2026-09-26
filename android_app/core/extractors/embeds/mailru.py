# -*- coding: utf-8 -*-
"""
Video Downloader Pro — Mail.ru Embed Extractor.
Resolves my.mail.ru/video/embed and API metadata streams.
"""

import re
import requests
from extractors.base import BaseExtractor, ExtractorResult
from logger import get_logger

logger = get_logger("extractors.embeds.mailru")


def resolve_mailru_embed(embed_url, session=None, headers=None):
    """
    Mail.ru video embedlerini (my.mail.ru/video/embed/ID) çözer.
    https://my.mail.ru/+/video/meta/ID JSON API'sini kullanarak doğrudan 1080p/720p MP4 bağlantısını alır.
    """
    try:
        m = re.search(r'/video/embed/(\d+)', embed_url) or re.search(r'/meta/(\d+)', embed_url)
        if not m:
            return None
        video_id = m.group(1)
        meta_url = f"https://my.mail.ru/+/video/meta/{video_id}"
        req_headers = {
            "User-Agent": (headers or {}).get("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"),
            "Referer": embed_url
        }
        client = session or requests
        r = client.get(meta_url, headers=req_headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            videos = data.get("videos", [])
            if videos:
                best_vid = videos[0].get("url")
                if best_vid.startswith("//"):
                    best_vid = "https:" + best_vid
                return {
                    "video_url": best_vid,
                    "title": data.get("meta", {}).get("title"),
                    "headers": {"User-Agent": req_headers["User-Agent"], "Referer": embed_url}
                }
    except Exception as e:
        logger.debug(f"resolve_mailru_embed error: {e}")
    return None


class MailruExtractor(BaseExtractor):
    """Strategy extractor for Mail.ru embeds."""

    @property
    def name(self) -> str:
        return "Mail.ru Embed"

    def can_handle(self, url: str) -> bool:
        low = url.lower()
        return "mail.ru/video" in low or "my.mail.ru" in low

    def extract(self, url: str, session=None, log_callback=None) -> ExtractorResult:
        self.log(f"[+] Mail.ru embed çözülüyor: {url}", log_callback)
        data = resolve_mailru_embed(url, session=session)
        if not data or not data.get("video_url"):
            return None

        title = data.get("title") or "Mail.ru Video"
        headers = data.get("headers", {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": url
        })
        return ExtractorResult(
            success=True,
            title=title,
            video_url=data["video_url"],
            video_headers=headers,
            audio_tracks=[],
            subtitles=[],
            total_segments=1,
            direct_file=True,
            raw_url=url
        )


__all__ = ["MailruExtractor", "resolve_mailru_embed"]
