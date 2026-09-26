# -*- coding: utf-8 -*-
"""
Video Downloader Pro — YabancıDizi Platform Extractor.
Resolves VidMoly embeds, /ajax/service endpoints, and multi-language streams for YabancıDizi.
"""

import re
from urllib.parse import urlparse, urljoin
import requests

try:
    from curl_cffi import requests as c_requests
except Exception:
    c_requests = None

from extractors.base import BaseExtractor, ExtractorResult, DEFAULT_HEADERS
from extractors.subtitles import extract_subtitles_from_tracks
from logger import get_logger

logger = get_logger("extractors.platforms.yabancidizi")


class YabancidiziExtractor(BaseExtractor):
    """Strategy extractor for YabancıDizi mirrors and series episodes."""

    @property
    def name(self) -> str:
        return "YabancıDizi Platform"

    def can_handle(self, url: str) -> bool:
        low = url.lower()
        return "yabancidizi" in low

    def extract(self, url: str, session=None, log_callback=None) -> ExtractorResult:
        self.log(f"[*] YabancıDizi taranıyor: {url}", log_callback)
        sess = session or requests.Session()
        headers = dict(DEFAULT_HEADERS)
        headers["Referer"] = url

        try:
            r = sess.get(url, headers=headers, timeout=12)
            if r.status_code != 200:
                return None
            page_html = r.text
        except Exception as e:
            logger.debug(f"YabancıDizi fetch error: {e}")
            return None

        yd_title_m = re.search(r'<h1[^>]*class=["\']page-title["\'][^>]*>(.*?)</h1>', page_html, re.DOTALL)
        if yd_title_m:
            film_title = re.sub(r'<[^>]+>', ' ', yd_title_m.group(1)).strip()
            film_title = " ".join(film_title.split())
        else:
            title_m = re.search(r'<title>([^<]+)</title>', page_html)
            film_title = title_m.group(1).split("izle")[0].strip() if title_m else "YabancıDizi Video"

        audio_tracks = []
        primary_video_url = ""
        primary_headers = {}
        primary_segments = []

        dl_matches = re.findall(r'href=["\']https?://vidmoly\.[a-z]+/(?:dl/|w/|v/|embed-)?([a-zA-Z0-9]{8,16})["\'][^>]*>(.*?)</a>', page_html, re.DOTALL | re.IGNORECASE)
        code_label_map = {}
        for c, txt in dl_matches:
            t_clean = re.sub(r'<[^>]+>', ' ', txt).lower()
            if "dublaj" in t_clean:
                code_label_map[c] = ("🇹🇷 Türkçe Dublaj", "tur")
            elif "altyaz" in t_clean:
                code_label_map[c] = ("🇬🇧 Orijinal / Türkçe Altyazılı", "eng")

        v_codes = re.findall(r'vidmoly\.[a-z]+/(?:dl/|w/|v/|embed-)?([a-zA-Z0-9]{8,16})', page_html)
        subtitles = []

        for code in list(dict.fromkeys(v_codes)):
            vm_url = f"https://vidmoly.biz/embed-{code}.html"
            vm_hdrs = {'User-Agent': headers['User-Agent'], 'Referer': 'https://yabancidizi.news/'}
            try:
                r_vm = sess.get(vm_url, headers=vm_hdrs, timeout=12)
                if r_vm.status_code == 200:
                    v_subs = extract_subtitles_from_tracks(r_vm.text, vm_url)
                    if v_subs:
                        subtitles.extend(v_subs)

                    m_mst = re.search(r'sources:\s*\[\{\s*file:\s*[\'"]([^\'"]+)[\'"]', r_vm.text) or re.search(r'file:\s*[\'"](https?://[^\'"]+\.m3u8[^\'"]*)[\'"]', r_vm.text)
                    if m_mst:
                        mst_u = m_mst.group(1)
                        r_m = sess.get(mst_u, headers=vm_hdrs, timeout=12)
                        if r_m.status_code == 200:
                            v_lines = [l.strip() for l in r_m.text.splitlines() if l.strip() and not l.startswith('#')]
                            if v_lines:
                                sub_u = urljoin(mst_u, v_lines[0])
                                r_sub = sess.get(sub_u, headers=vm_hdrs, timeout=12)
                                if r_sub.status_code == 200:
                                    segs = [urljoin(sub_u, l.strip()) for l in r_sub.text.splitlines() if l.strip() and not l.startswith('#')]
                                    if segs:
                                        t_lbl, t_lang = code_label_map.get(code, (f"🎬 VidMoly ({code})", "tur" if len(audio_tracks) == 0 else "eng"))
                                        audio_tracks.append({
                                            "name": t_lbl,
                                            "lang": t_lang,
                                            "sample_segment_url": segs[0],
                                            "count": len(segs),
                                            "headers": vm_hdrs,
                                            "segments": segs,
                                            "video_segments": segs,
                                            "video_url": sub_u,
                                            "video_headers": vm_hdrs,
                                            "is_standalone_stream": True
                                        })
                                        if not primary_video_url:
                                            primary_video_url = segs[0]
                                            primary_headers = vm_hdrs
                                            primary_segments = segs
            except Exception as vm_err:
                logger.debug(f"YabanciDizi vidmoly iteration error: {vm_err}")

        if primary_video_url:
            return ExtractorResult(
                success=True,
                title=film_title,
                video_url=primary_video_url,
                video_headers=primary_headers,
                audio_tracks=audio_tracks,
                subtitles=subtitles,
                total_segments=len(primary_segments),
                direct_file=False,
                raw_url=url,
                video_segments=primary_segments,
            )

        return None


__all__ = ["YabancidiziExtractor"]
