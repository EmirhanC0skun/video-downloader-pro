# -*- coding: utf-8 -*-
"""
Video Downloader Pro — Anime Platform Extractor.
Resolves TurkAnime and Animecix streams via SPG.cerceve XOR and X-Sp token solver.
"""

import re
import random
import base64
import requests
from extractors.base import BaseExtractor, ExtractorResult, DEFAULT_HEADERS
from extractors.embeds.vidmoly import resolve_vidmoly_embed
from logger import get_logger

logger = get_logger("extractors.platforms.anime")


def decode_spg_cerceve(t_b64, n_b64):
    """SPG.cerceve içerisindeki base64 XOR şifreli iframe adresini çözer."""
    try:
        t_clean = t_b64.replace('\\/', '/').replace('\\', '')
        n_clean = n_b64.replace('\\/', '/').replace('\\', '')
        r = base64.b64decode(t_clean)
        o = base64.b64decode(n_clean)
        res = ""
        for c in range(len(r)):
            res += chr(r[c] ^ o[c % len(o)])
        return res.split("|")[0]
    except Exception as e:
        logger.debug(f"decode_spg_cerceve error: {e}")
        return ""


def solve_x_sp(html):
    """HTML içindeki SPG_A yapılandırmasından dinamik X-Sp jetonunu üretir."""
    sp_match = re.search(r'"sp":\s*"([^"]+)"', html)
    spt_match = re.search(r'"spT":\s*(\d+)', html)
    if not sp_match or not spt_match:
        return None
    sp = sp_match.group(1)
    sp_t = int(spt_match.group(1))

    r_val = hex(random.randint(0, 2176782335))[2:]
    key_str = f"{sp}|{sp_t}|{r_val}"

    # 32-bit FNV-1a Hash
    t = 2166136261
    for ch in key_str:
        t ^= ord(ch)
        t = (t * 16777619) & 0xFFFFFFFF

    return f"{sp_t}.{r_val}.{hex(t)[2:]}"


class AnimeExtractor(BaseExtractor):
    """Strategy extractor for TurkAnime and Animecix portals."""

    @property
    def name(self) -> str:
        return "Anime Portal (TurkAnime/Animecix)"

    def can_handle(self, url: str) -> bool:
        low = url.lower()
        return any(k in low for k in ["turkanime", "animecix"])

    def extract(self, url: str, session=None, log_callback=None) -> ExtractorResult:
        self.log(f"[*] Anime portalı taranıyor: {url}", log_callback)
        sess = session or requests.Session()
        headers = dict(DEFAULT_HEADERS)
        headers["Referer"] = url

        try:
            r = sess.get(url, headers=headers, timeout=12)
            if r.status_code != 200:
                return None
            page_html = r.text
        except Exception as e:
            logger.debug(f"Anime portal fetch error: {e}")
            return None

        title_m = re.search(r'<title>([^<]+)</title>', page_html)
        film_title = title_m.group(1).split("izle")[0].strip() if title_m else "Anime Video"

        spg_matches = re.findall(r'SPG\.cerceve\s*\(\s*["\']([^"\']+)["\']\s*,\s*["\']([^"\']+)["\']\s*\)', page_html)
        for t_b64, n_b64 in spg_matches:
            iframe_url = decode_spg_cerceve(t_b64, n_b64)
            if iframe_url and "http" in iframe_url:
                if "vidmoly" in iframe_url:
                    m3u8_url = resolve_vidmoly_embed(iframe_url, session=sess, headers=headers)
                    if m3u8_url:
                        return ExtractorResult(
                            success=True,
                            title=film_title,
                            video_url=m3u8_url,
                            video_headers=headers,
                            audio_tracks=[],
                            subtitles=[],
                            total_segments=0,
                            direct_file=False,
                            raw_url=url
                        )

        return None


__all__ = ["AnimeExtractor", "decode_spg_cerceve", "solve_x_sp"]
