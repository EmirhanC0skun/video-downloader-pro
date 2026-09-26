# -*- coding: utf-8 -*-
"""
Video Downloader Pro — Subtitle Extraction Utilities.
Parses WebVTT, SRT, and HLS #EXT-X-MEDIA:TYPE=SUBTITLES tracks.
"""

import re
import json
from urllib.parse import urljoin
from logger import get_logger

logger = get_logger("extractors.subtitles")


def extract_subtitles_from_m3u8(m3u8_text, base_url="", headers=None):
    """M3U8 master playlist içerisindeki #EXT-X-MEDIA:TYPE=SUBTITLES akışlarını ayrıştırır."""
    subtitles = []
    if not m3u8_text:
        return subtitles
    req_hdrs = dict(headers or {})
    req_hdrs.setdefault("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0")
    if base_url:
        req_hdrs.setdefault("Referer", base_url)

    for line in m3u8_text.splitlines():
        if "#EXT-X-MEDIA:TYPE=SUBTITLES" in line.upper():
            name_m = re.search(r'NAME=["\']([^"\']+)["\']', line, re.IGNORECASE)
            uri_m = re.search(r'URI=["\']([^"\']+)["\']', line, re.IGNORECASE)
            lang_m = re.search(r'LANGUAGE=["\']([^"\']+)["\']', line, re.IGNORECASE)
            forced_m = re.search(r'FORCED=([A-Za-z]+)', line, re.IGNORECASE)
            default_m = re.search(r'DEFAULT=([A-Za-z]+)', line, re.IGNORECASE)
            if uri_m:
                sub_uri = uri_m.group(1).strip()
                sub_url = urljoin(base_url, sub_uri) if base_url else sub_uri
                sub_name = name_m.group(1).strip() if name_m else "Altyazı"
                sub_lang = lang_m.group(1).strip().lower() if lang_m else ("tur" if any(k in sub_name.lower() for k in ["turk", "türk", "tr"]) else "eng")
                is_forced = (forced_m and forced_m.group(1).upper() == "YES") or any(k in sub_name.lower() for k in ["forced", "tabela", "sign", "ekran"])
                is_default = (default_m and default_m.group(1).upper() == "YES")
                subtitles.append({
                    "url": sub_url,
                    "name": sub_name,
                    "label": sub_name,
                    "lang": sub_lang,
                    "forced": is_forced,
                    "default": is_default,
                    "kind": "captions" if is_forced else "subtitles",
                    "headers": req_hdrs
                })
    return subtitles


def extract_subtitles_from_tracks(html_text, base_url="", headers=None):
    """HTML veya JS içindeki tracks / subtitles JSON dizilerinden ve track etiketlerinden WebVTT/SRT altyazılarını ayrıştırır."""
    subtitles = []
    if not html_text:
        return subtitles
    req_hdrs = dict(headers or {})
    req_hdrs.setdefault("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0")
    if base_url:
        req_hdrs.setdefault("Referer", base_url)

    # 1. JSON tabanlı tracks / subtitles listeleri
    tracks_m = re.findall(r'(?:tracks|subtitles)\s*:\s*(\[[^\]]+\])', html_text)
    for raw_m in tracks_m:
        try:
            raw_json = raw_m.replace(r'\/', '/')
            track_list = json.loads(raw_json)
            if isinstance(track_list, list):
                for t in track_list:
                    if not isinstance(t, dict):
                        continue
                    f_url = t.get("file") or t.get("src") or t.get("url")
                    lbl = t.get("label") or t.get("title") or t.get("name") or "Altyazı"
                    kind = (t.get("kind") or "subtitles").lower()
                    if f_url and isinstance(f_url, str):
                        full_f = urljoin(base_url, f_url) if base_url else f_url
                        is_tr = any(k in f"{lbl} {t.get('lang', '')}".lower() for k in ["turk", "türk", "tr"])
                        is_forced = (t.get("default") == "forced") or any(k in lbl.lower() for k in ["forced", "tabela", "sign"])
                        subtitles.append({
                            "url": full_f,
                            "name": lbl,
                            "label": lbl,
                            "lang": "tur" if is_tr else "eng",
                            "forced": is_forced,
                            "default": bool(t.get("default")),
                            "kind": kind,
                            "headers": req_hdrs
                        })
        except Exception:
            logger.debug("tracks ayrıştırma istisnası", exc_info=True)

    # 2. HTML5 <track> etiketleri
    for trk_m in re.finditer(r'<track[^>]+(?:src|file)=["\']([^"\']+)["\'][^>]*>', html_text, re.IGNORECASE):
        tag_str = trk_m.group(0)
        src = trk_m.group(1)
        lbl_m = re.search(r'label=["\']([^"\']+)["\']', tag_str, re.IGNORECASE)
        srclang_m = re.search(r'srclang=["\']([^"\']+)["\']', tag_str, re.IGNORECASE)
        kind_m = re.search(r'kind=["\']([^"\']+)["\']', tag_str, re.IGNORECASE)
        lbl = lbl_m.group(1) if lbl_m else "Altyazı"
        slang = srclang_m.group(1).lower() if srclang_m else ""
        kind = kind_m.group(1).lower() if kind_m else "subtitles"
        full_f = urljoin(base_url, src) if base_url else src
        is_tr = any(k in f"{lbl} {slang}".lower() for k in ["turk", "türk", "tr"])
        is_forced = any(k in lbl.lower() for k in ["forced", "tabela", "sign"])
        subtitles.append({
            "url": full_f,
            "name": lbl,
            "label": lbl,
            "lang": "tur" if is_tr else "eng",
            "forced": is_forced,
            "default": "default" in tag_str.lower(),
            "kind": kind,
            "headers": req_hdrs
        })

    # Tekilleştirme
    seen = set()
    dedup = []
    for s in subtitles:
        u = s.get("url")
        if u and u not in seen:
            seen.add(u)
            dedup.append(s)
    return dedup


# Facade uyumluluğu için aliaslar
_extract_subtitles_from_m3u8 = extract_subtitles_from_m3u8
_extract_subtitles_from_tracks = extract_subtitles_from_tracks
