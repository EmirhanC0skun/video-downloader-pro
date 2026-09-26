# -*- coding: utf-8 -*-
"""
Video Downloader Pro — Diziyou Platform Extractor.
Extracts dual audio (Turkish Dubbing & Original/Subtitled) and HLS streams from Diziyou.
"""

import re
from urllib.parse import urljoin, urlsplit, urlunsplit
import requests
from extractors.base import BaseExtractor, ExtractorResult, DEFAULT_HEADERS
from extractors.variants import extract_master_quality_variants, extract_media_playlist_timeline
from logger import get_logger

logger = get_logger("extractors.platforms.diziyou")


class DiziyouExtractor(BaseExtractor):
    """Strategy extractor for Diziyou series and dual audio players."""

    @property
    def name(self) -> str:
        return "Diziyou Platform"

    def can_handle(self, url: str) -> bool:
        low = url.lower()
        return "diziyou" in low

    def extract(self, url: str, session=None, log_callback=None) -> ExtractorResult:
        self.log(f"[*] Diziyou taranıyor: {url}", log_callback)
        sess = session or requests.Session()
        headers = dict(DEFAULT_HEADERS)
        headers["Referer"] = url

        try:
            r_page = sess.get(url, headers=headers, timeout=12)
            if r_page.status_code != 200:
                return None
            r_page.encoding = "utf-8"
            page_html = r_page.text
        except Exception as e:
            logger.debug(f"Diziyou page fetch error: {e}")
            return None

        title_m = re.search(r'<title>([^<]+)</title>', page_html)
        film_title = title_m.group(1).split("izle")[0].strip() if title_m else "Diziyou Video"

        # Çift dil (Türkçe Dublaj & Altyazılı) tespiti
        if re.search(r'id=["\']turkceDublaj["\']', page_html, re.I):
            try:
                diziyou_iframes = re.findall(r'<iframe[^>]+src=["\']([^"\']+)["\']', page_html, re.IGNORECASE)
                if diziyou_iframes:
                    orig_ifr_url = urljoin(url, diziyou_iframes[0].strip())
                    tr_ifr_url = orig_ifr_url.replace(".html", "_tr.html")
                    self.log("2. 🎭 Diziyou Türkçe Dublaj ve Altyazı köprüleri taranıyor...", log_callback)

                    r_tr_p = sess.get(tr_ifr_url, headers={"User-Agent": headers["User-Agent"], "Referer": url}, timeout=8)
                    r_orig_p = sess.get(orig_ifr_url, headers={"User-Agent": headers["User-Agent"], "Referer": url}, timeout=8)

                    tr_m3u8 = re.findall(r'https?://[^\s"\'<>]+\.m3u8(?:\?[^\s"\'<>]*)?', r_tr_p.text)
                    orig_m3u8 = re.findall(r'https?://[^\s"\'<>]+\.m3u8(?:\?[^\s"\'<>]*)?', r_orig_p.text)

                    if tr_m3u8 and orig_m3u8:
                        def resolve_dy_m3u8_segs(m_url):
                            cand_h = {"User-Agent": headers["User-Agent"], "Referer": url}
                            r_m = sess.get(m_url, headers=cand_h, timeout=8)
                            if r_m.status_code != 200:
                                return [], [], None

                            variants = extract_master_quality_variants(m_url, r_m.text)
                            playlist_candidates = []
                            for variant in variants:
                                resolution = variant.get("resolution", "")
                                height_match = re.search(r"x(\d+)$", resolution)
                                declared_height = int(height_match.group(1)) if height_match else 0
                                declared_url = variant.get("url", "")

                                # Diziyou bazen 1080p satirini 720p.m3u8'e bagliyor.
                                # Ayni dizindeki ilan edilen kalite dosyasini kontrollu
                                # olarak dene ve sadece gercek media playlist kabul et.
                                if declared_height and declared_url:
                                    parts = urlsplit(declared_url)
                                    sibling_path = re.sub(
                                        r"[^/]+\.m3u8$",
                                        f"{declared_height}p.m3u8",
                                        parts.path,
                                        flags=re.IGNORECASE,
                                    )
                                    sibling_url = urlunsplit(
                                        (parts.scheme, parts.netloc, sibling_path, parts.query, parts.fragment)
                                    )
                                    playlist_candidates.append((sibling_url, variant))
                                playlist_candidates.append((declared_url, variant))

                            if not playlist_candidates:
                                playlist_candidates.append((m_url, None))

                            seen_urls = set()
                            for target_u, variant in playlist_candidates:
                                if not target_u or target_u in seen_urls:
                                    continue
                                seen_urls.add(target_u)
                                r_sub = r_m if target_u == m_url else sess.get(
                                    target_u, headers=cand_h, timeout=8
                                )
                                has_media_lines = any(
                                    line.strip() and not line.strip().startswith("#")
                                    for line in r_sub.text.splitlines()
                                )
                                is_media_playlist = "#EXTINF:" in r_sub.text or (
                                    not variants and has_media_lines
                                )
                                if r_sub.status_code != 200 or not is_media_playlist:
                                    continue
                                response_url = getattr(r_sub, "url", None)
                                final_playlist_url = response_url if isinstance(response_url, str) else target_u
                                segs, durations = extract_media_playlist_timeline(
                                    final_playlist_url,
                                    r_sub.text,
                                )
                                if segs:
                                    selected_quality = dict(variant) if variant else None
                                    if selected_quality is not None:
                                        selected_quality["url"] = target_u
                                    return segs, durations, selected_quality
                            return [], [], None

                        tr_segs, tr_durations, tr_quality = resolve_dy_m3u8_segs(tr_m3u8[0])
                        orig_segs, orig_durations, orig_quality = resolve_dy_m3u8_segs(orig_m3u8[0])

                        if tr_segs and orig_segs:
                            self.log(f"[+] 🎯 Diziyou İki Dil Birden Çözüldü: 🇹🇷 ({len(tr_segs)} parça) + 🇬🇧 ({len(orig_segs)} parça)", log_callback)
                            subs = []
                            for sub_track in re.findall(r'<track[^>]+src=["\']([^"\']+)["\'][^>]*srclang=["\']([^"\']+)["\']', r_orig_p.text):
                                subs.append({"url": urljoin(orig_ifr_url, sub_track[0]), "lang": sub_track[1]})

                            dy_headers = {"User-Agent": headers["User-Agent"], "Referer": url}
                            return ExtractorResult(
                                success=True,
                                title=film_title,
                                video_url=tr_segs[0],
                                video_headers=dy_headers,
                                video_segments=tr_segs,
                                audio_tracks=[
                                    {
                                        "name": "🇹🇷 Türkçe Dublaj",
                                        "lang": "tur",
                                        "sample_segment_url": tr_segs[0],
                                        "segments": tr_segs,
                                        "video_segments": tr_segs,
                                        "video_url": tr_segs[0],
                                        "video_headers": dy_headers,
                                        "durations": tr_durations,
                                        "video_durations": tr_durations,
                                        "count": len(tr_segs),
                                        "headers": dy_headers,
                                        "is_standalone_stream": True,
                                    },
                                    {
                                        "name": "🇬🇧 Orijinal / Türkçe Altyazılı",
                                        "lang": "eng",
                                        "sample_segment_url": orig_segs[0],
                                        "segments": orig_segs,
                                        "video_segments": orig_segs,
                                        "video_url": orig_segs[0],
                                        "video_headers": dy_headers,
                                        "durations": orig_durations,
                                        "video_durations": orig_durations,
                                        "count": len(orig_segs),
                                        "headers": dy_headers,
                                        "is_standalone_stream": True,
                                    }
                                ],
                                subtitles=subs,
                                total_segments=len(tr_segs),
                                direct_file=False,
                                raw_url=url,
                                video_durations=tr_durations,
                                qualities=[tr_quality] if tr_quality else [],
                            )
            except Exception as e_dy:
                logger.debug(f"Diziyou dual audio resolution error: {e_dy}")

        return None


__all__ = ["DiziyouExtractor"]
