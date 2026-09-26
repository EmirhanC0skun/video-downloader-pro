# -*- coding: utf-8 -*-
"""
Video Downloader Pro — Dizilla & RoketDizi Platform Extractor.
Resolves NEXT_DATA JSON payloads and Pichive player streams.
"""

import re
import json
import base64
import hashlib
from urllib.parse import urljoin
import requests

try:
    from curl_cffi import requests as c_requests
except Exception:
    c_requests = None

try:
    from Crypto.Cipher import AES
except ImportError:
    try:
        from Cryptodome.Cipher import AES
    except ImportError:
        AES = None

from extractors.base import BaseExtractor, ExtractorResult, DEFAULT_HEADERS
from extractors.embeds.players import resolve_pichive_embed
from logger import get_logger

logger = get_logger("extractors.platforms.dizilla")


class DizillaExtractor(BaseExtractor):
    """Strategy extractor for Dizilla and RoketDizi series/movie mirrors."""

    @property
    def name(self) -> str:
        return "Dizilla & RoketDizi"

    def can_handle(self, url: str) -> bool:
        low = url.lower()
        return any(k in low for k in ["dizilla", "roketdizi"])

    def extract(self, url: str, session=None, log_callback=None) -> ExtractorResult:
        self.log(f"[*] Dizilla/RoketDizi taranıyor: {url}", log_callback)
        sess = session or requests.Session()
        headers = dict(DEFAULT_HEADERS)
        headers["Referer"] = url

        try:
            r = None
            if c_requests:
                try:
                    r = c_requests.get(url, headers=headers, impersonate="chrome124", timeout=12)
                except Exception:
                    r = None
            if not r or r.status_code != 200:
                r = sess.get(url, headers=headers, timeout=12)
            if not r or r.status_code != 200:
                return None
            page_html = r.text
        except Exception as e:
            logger.debug(f"Dizilla fetch error: {e}")
            return None

        title_m = re.search(r'<title>([^<]+)</title>', page_html)
        film_title = title_m.group(1).split("izle")[0].strip() if title_m else "Dizilla Video"

        try:
            next_data_m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page_html, re.DOTALL) or re.search(r'\{"props":\{"pageProps":.*\}\}', page_html, re.DOTALL)
            if next_data_m:
                next_json = json.loads(next_data_m.group(1) if '__NEXT_DATA__' in page_html else next_data_m.group(0))
                page_props = next_json.get("props", {}).get("pageProps", {})
                secure_raw = page_props.get("secureData")
                if secure_raw:
                    secure_json = None
                    try:
                        raw_dec = base64.b64decode(secure_raw)
                        for enc in ("utf-8", "utf-8-sig", "iso-8859-9", "windows-1254"):
                            try:
                                secure_json = json.loads(raw_dec.decode(enc))
                                break
                            except Exception:
                                continue
                    except Exception:
                        raw_dec = None

                    if not secure_json and raw_dec and AES:
                        try:
                            key_b64 = base64.b64encode(hashlib.sha256(b"!!22xx!!90!!").digest()).decode('utf-8')[:32]
                            key = key_b64.encode('utf-8')
                            iv = bytes(16)
                            pad_needed = (16 - (len(raw_dec) % 16)) % 16
                            padded = raw_dec + (bytes([pad_needed]) * pad_needed) if pad_needed > 0 else raw_dec
                            cipher = AES.new(key, AES.MODE_CBC, iv)
                            dec_padded = cipher.decrypt(padded)
                            pad_len = dec_padded[-1]
                            dec_bytes = dec_padded[:-pad_len] if 1 <= pad_len <= 16 else dec_padded
                            for enc in ("utf-8", "utf-8-sig", "iso-8859-9", "windows-1254"):
                                try:
                                    secure_json = json.loads(dec_bytes.decode(enc, errors='ignore'))
                                    break
                                except Exception:
                                    continue
                        except Exception as ex_aes:
                            logger.debug(f"Dizilla AES decrypt error: {ex_aes}")

                    if secure_json:
                        ci = secure_json.get("contentItem", {})
                        ep_title = ci.get("episode_title") or f"{ci.get('original_title', '')} {ci.get('season_text', '')} {ci.get('episode_text', '')}".strip()
                        if ep_title:
                            film_title = ep_title

                        sources_list = []
                        def find_episode_sources(obj):
                            if isinstance(obj, dict):
                                if "source_content" in obj and obj.get("source_content"):
                                    sources_list.append(obj)
                                elif "getEpisodeSources" in obj and isinstance(obj["getEpisodeSources"], dict):
                                    res = obj["getEpisodeSources"].get("result", [])
                                    if res:
                                        sources_list.extend(res)
                                for v in obj.values():
                                    find_episode_sources(v)
                            elif isinstance(obj, list):
                                for it in obj:
                                    find_episode_sources(it)

                        find_episode_sources(secure_json)

                        for src_item in sources_list:
                            s_content = src_item.get("source_content", "")
                            iframe_m = re.search(r'<iframe[^>]+src=["\']([^"\']+)["\']', s_content)
                            if not iframe_m:
                                continue
                            embed_src = iframe_m.group(1)
                            if embed_src.startswith("//"):
                                embed_src = "https:" + embed_src

                            p_info = resolve_pichive_embed(embed_src, session=sess, headers=headers, parent_url=url)
                            if isinstance(p_info, dict) and p_info.get("video_url"):
                                m_file = p_info["video_url"]
                                base_host = p_info.get("base_host")
                                m_hdrs = p_info.get("headers") or {'User-Agent': headers['User-Agent'], 'Referer': embed_src, 'Origin': base_host}
                                v_segs = p_info.get("video_segments") or []
                                a_tracks = p_info.get("audio_tracks", [])
                                return ExtractorResult(
                                    success=True,
                                    title=film_title,
                                    video_url=m_file,
                                    video_headers=m_hdrs,
                                    audio_tracks=a_tracks,
                                    subtitles=p_info.get("subtitles", []),
                                    total_segments=len(v_segs) if v_segs else p_info.get("total_segments", 0),
                                    direct_file=False,
                                    video_segments=v_segs if v_segs else None,
                                    raw_url=url
                                )
        except Exception as e:
            logger.debug(f"Dizilla extraction error: {e}")

        return None


__all__ = ["DizillaExtractor"]
