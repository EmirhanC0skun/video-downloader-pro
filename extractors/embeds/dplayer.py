# -*- coding: utf-8 -*-
"""
Video Downloader Pro — DPlayer Embed Extractor.
Resolves four.dplayer82.site, sn.dplayer, and related stream mirrors.
"""

import re
import json
from urllib.parse import urljoin
import requests

try:
    from curl_cffi import requests as c_requests
except Exception:
    c_requests = None

from extractors.base import BaseExtractor, ExtractorResult
from logger import get_logger

logger = get_logger("extractors.embeds.dplayer")


def resolve_dplayer_embed(embed_url, session=None, headers=None):
    """
    DPlayer (four.dplayer82.site/iframe.php?v=...) oynatıcı çözücü.
    openPlayer('...') -> source2.php?v=... endpointinden HLS master.m3u8 akışlarını döndürür.
    """
    session = session or requests.Session()
    req_headers = dict(headers or {})
    req_headers.setdefault("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    req_headers.setdefault("Referer", embed_url)

    try:
        if c_requests:
            r = c_requests.get(embed_url, headers=req_headers, impersonate="chrome124", timeout=12)
        else:
            r = session.get(embed_url, headers=req_headers, timeout=12)

        if r.status_code == 200:
            html_text = r.text
            subs_list = []
            m_call = re.search(r'openPlayer\s*\(([\s\S]*?)\)\s*;', html_text)
            if m_call:
                sub_matches = re.findall(r'\[\s*\{\s*[\'"]file[\'"]\s*:[\s\S]*?\}\s*\]', m_call.group(1))
                for sm in sub_matches:
                    try:
                        s_items = json.loads(sm)
                        for sit in s_items:
                            s_f = sit.get("file")
                            if s_f:
                                s_lbl = sit.get("label") or "Türkçe Altyazı"
                                s_lng = sit.get("lang") or "tur"
                                is_tr = any(k in f"{s_lbl} {s_lng}".lower() for k in ["türk", "turk", "tr"])
                                subs_list.append({
                                    "url": s_f,
                                    "name": s_lbl,
                                    "label": s_lbl,
                                    "lang": "tur" if is_tr else "eng",
                                    "headers": {"User-Agent": req_headers["User-Agent"], "Referer": embed_url}
                                })
                    except Exception as e:
                        logger.debug(f"DPlayer altyazı ayrıştırma hatası: {e}")

            op_m = re.search(r"openPlayer\(\s*['\"]([^'\"]+)['\"]", html_text)
            if op_m:
                playlist_arg = op_m.group(1)
                source_url = urljoin(embed_url, "source2.php?v=" + playlist_arg)
                src_headers = dict(req_headers)
                src_headers["Referer"] = embed_url

                if c_requests:
                    r_src = c_requests.get(source_url, headers=src_headers, impersonate="chrome124", timeout=12)
                else:
                    r_src = session.get(source_url, headers=src_headers, timeout=12)

                if r_src.status_code == 200:
                    data = r_src.json()
                    streams = []
                    for item in data.get("playlist", []):
                        for src in item.get("sources", []):
                            m3u8_url = src.get("file", "").replace("m.php", "master.m3u8")
                            t = src.get("title", "Orijinal")
                            streams.append({"title": t, "url": m3u8_url})
                        for trk in item.get("tracks", []):
                            if isinstance(trk, dict) and trk.get("file"):
                                f_u = trk.get("file")
                                if f_u.startswith("//"): f_u = "https:" + f_u
                                elif f_u.startswith("/"): f_u = urljoin(embed_url, f_u)
                                lbl = trk.get("label") or "Türkçe Altyazı"
                                is_tr = any(k in f"{lbl} {trk.get('kind','')}".lower() for k in ["türk", "turk", "tr"])
                                subs_list.append({
                                    "url": f_u,
                                    "name": lbl,
                                    "label": lbl,
                                    "lang": "tur" if is_tr else "eng",
                                    "headers": {"User-Agent": req_headers["User-Agent"], "Referer": embed_url}
                                })
                    if streams:
                        # Deduplicate subtitles by url
                        seen_sub_u = set()
                        dedup_subs = []
                        for s in subs_list:
                            u = s.get("url")
                            if u and u not in seen_sub_u:
                                seen_sub_u.add(u)
                                dedup_subs.append(s)
                        return {
                            "streams": streams,
                            "embed_url": embed_url,
                            "subtitles": dedup_subs
                        }
    except Exception as e:
        logger.debug(f"resolve_dplayer_embed error: {e}")
    return None


class DPlayerExtractor(BaseExtractor):
    """Strategy extractor for DPlayer embeds."""

    @property
    def name(self) -> str:
        return "DPlayer Embed"

    def can_handle(self, url: str) -> bool:
        low = url.lower()
        return "dplayer" in low

    def extract(self, url: str, session=None, log_callback=None) -> ExtractorResult:
        self.log(f"[+] DPlayer embed çözülüyor: {url}", log_callback)
        data = resolve_dplayer_embed(url, session=session)
        if not data or not data.get("streams"):
            return None

        streams = data["streams"]
        best_stream = streams[0]["url"]
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": url
        }
        return ExtractorResult(
            success=True,
            title="DPlayer Video",
            video_url=best_stream,
            video_headers=headers,
            audio_tracks=[],
            subtitles=data.get("subtitles", []),
            total_segments=0,
            direct_file=False,
            raw_url=url
        )


__all__ = ["DPlayerExtractor", "resolve_dplayer_embed"]
