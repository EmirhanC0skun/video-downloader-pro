# -*- coding: utf-8 -*-
"""
Video Downloader Pro — 720pizle Platform Extractor.
Resolves 720pizle player mounts, Pichive embed streams, subtitles and multi-player mirrors.
"""

import re
from urllib.parse import urljoin
import requests

from extractors.base import BaseExtractor, ExtractorResult, DEFAULT_HEADERS
from extractors.embeds.players import resolve_pichive_embed
from logger import get_logger

logger = get_logger("extractors.platforms.seven20p")


class Seven20pExtractor(BaseExtractor):
    """Strategy extractor for 720pizle film and series platform."""

    @property
    def name(self) -> str:
        return "720pizle Platform"

    def can_handle(self, url: str) -> bool:
        return "720pizle" in url.lower()

    def extract(self, url: str, session=None, log_callback=None) -> ExtractorResult:
        self.log(f"[*] 720pizle taranıyor: {url}", log_callback)
        sess = session or requests.Session()
        headers = dict(DEFAULT_HEADERS)
        headers["Referer"] = url

        try:
            r = sess.get(url, headers=headers, timeout=12)
            if r.status_code != 200:
                return None
            html = r.text
        except Exception as ex:
            logger.debug(f"720pizle fetch error: {ex}")
            return None

        # Film / Dizi başlığı çözümleme
        title_m = re.search(r'<title>([^<]+)</title>', html, re.I)
        film_title = "720pizle Video"
        if title_m:
            raw_title = title_m.group(1)
            clean_title = raw_title.split(" - ")[0]
            clean_title = clean_title.split("izle")[0].strip()
            if clean_title:
                film_title = clean_title

        # Oynatıcı iframe'lerini tara (src ve data-src)
        iframes = re.findall(r'<iframe[^>]+src=["\']([^"\']+)["\']', html, re.I)
        for d_src in re.findall(r'<iframe[^>]+data-src=["\']([^"\']+)["\']', html, re.I):
            if d_src not in iframes:
                iframes.append(d_src)

        for ifr in iframes:
            if ifr.startswith("//"):
                ifr = "https:" + ifr
            elif ifr.startswith("/"):
                ifr = urljoin(url, ifr)

            # 1. Pichive / four.pichive oynatıcısı
            if any(k in ifr.lower() for k in ["pichive", "four.", "source2.php"]):
                p_info = resolve_pichive_embed(ifr, session=sess, headers=headers, parent_url=url)
                if isinstance(p_info, dict) and p_info.get("video_url"):
                    base_host = p_info.get("base_host")
                    m_hdrs = p_info.get("headers") or {'User-Agent': headers['User-Agent'], 'Referer': ifr}
                    if base_host and "Origin" not in m_hdrs:
                        m_hdrs['Origin'] = base_host
                    v_segs = p_info.get("video_segments") or []
                    a_tracks = p_info.get("audio_tracks", [])
                    return ExtractorResult(
                        success=True,
                        title=film_title,
                        video_url=p_info["video_url"],
                        video_headers=m_hdrs,
                        audio_tracks=a_tracks,
                        subtitles=p_info.get("subtitles", []),
                        total_segments=len(v_segs) if v_segs else p_info.get("total_segments", 0),
                        direct_file=False,
                        video_segments=v_segs if v_segs else None,
                        raw_url=url
                    )

            # 2. Diğer gömülü oynatıcıları genel kayıt defteri üzerinden dene
            try:
                from extractors.registry import default_registry
                sub_res = default_registry.resolve(ifr, session=sess, log_callback=log_callback)
                if sub_res and sub_res.get("success") and sub_res.get("video_url"):
                    return ExtractorResult(
                        success=True,
                        title=film_title,
                        video_url=sub_res.get("video_url"),
                        video_headers=sub_res.get("video_headers", headers),
                        audio_tracks=sub_res.get("audio_tracks", []),
                        subtitles=sub_res.get("subtitles", []),
                        total_segments=sub_res.get("total_segments", 0),
                        direct_file=sub_res.get("direct_file", False),
                        raw_url=url
                    )
            except Exception as _e_sub:
                logger.debug(f"720pizle embed dispatch error for {ifr}: {_e_sub}")

        return None


def resolve_seven20p_page(url: str, session=None, log_callback=None):
    """Yardımcı doğrudan çağrı fonksiyonu."""
    extractor = Seven20pExtractor()
    res = extractor.extract(url, session=session, log_callback=log_callback)
    return res.to_dict() if res else None


__all__ = ["Seven20pExtractor", "resolve_seven20p_page"]
