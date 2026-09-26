# -*- coding: utf-8 -*-
"""
Video Downloader Pro — Generic Media, HLS & DASH Extractor.
Resolves direct video files, M3U8 playlists, and DASH manifests.
"""

import os
import re
from urllib.parse import urljoin
import requests

from extractors.base import BaseExtractor, ExtractorResult, DEFAULT_HEADERS
from extractors.direct import DirectMediaExtractor
from logger import get_logger

logger = get_logger("extractors.generic")


class GenericMediaExtractor(BaseExtractor):
    """Handles direct video files, HLS (.m3u8) and DASH (.mpd) stream manifests."""

    DIRECT_EXTENSIONS = (
        ".mp4", ".mkv", ".webm", ".avi", ".mov", ".flv",
        ".m4v", ".m3u8", ".mpd", ".ts"
    )

    @property
    def name(self) -> str:
        return "Generic Media / Manifest Extractor"

    def can_handle(self, url: str) -> bool:
        clean_u = url.split("?")[0].split("#")[0].lower()
        return any(clean_u.endswith(ext) for ext in self.DIRECT_EXTENSIONS)

    def extract(self, url: str, session=None, log_callback=None) -> ExtractorResult:
        sess = session or requests.Session()
        clean_u = url.split("?")[0].split("#")[0]
        ext = os.path.splitext(clean_u)[1].lower()

        # 1. HLS Stream Playlist (.m3u8)
        if ext == ".m3u8":
            fname = os.path.basename(clean_u).replace(".m3u8", "") or "HLS Medya Akışı"
            self.log(f"[+] HLS çalma listesi ayrıştırılıyor: {fname}", log_callback)
            audio_tracks = []
            subtitles = []
            total_segments = 0

            try:
                r = sess.get(url, headers=DEFAULT_HEADERS, timeout=12)
                if r.status_code == 200:
                    text = r.text
                    for line in text.splitlines():
                        if line.startswith("#EXT-X-MEDIA:TYPE=AUDIO"):
                            n_m = re.search(r'NAME=["\']([^"\']+)["\']', line)
                            u_m = re.search(r'URI=["\']([^"\']+)["\']', line)
                            a_name = n_m.group(1) if n_m else "Ses Akışı"
                            a_uri = urljoin(url, u_m.group(1)) if u_m else url
                            audio_tracks.append({"name": a_name, "url": a_uri})
                        elif line.startswith("#EXT-X-MEDIA:TYPE=SUBTITLES"):
                            n_m = re.search(r'NAME=["\']([^"\']+)["\']', line)
                            u_m = re.search(r'URI=["\']([^"\']+)["\']', line)
                            s_name = n_m.group(1) if n_m else "Altyazı"
                            s_uri = urljoin(url, u_m.group(1)) if u_m else url
                            subtitles.append({"name": s_name, "label": s_name, "url": s_uri, "lang": "und"})

                    seg_matches = re.findall(r'#EXTINF:', text)
                    if seg_matches:
                        total_segments = len(seg_matches)
            except Exception as e:
                logger.debug(f"HLS manifest parsing note: {e}")

            return ExtractorResult(
                success=True,
                title=fname,
                video_url=url,
                video_headers=DEFAULT_HEADERS,
                audio_tracks=audio_tracks,
                subtitles=subtitles,
                total_segments=total_segments,
                direct_file=False,
                raw_url=url
            )

        # 2. DASH Manifest (.mpd)
        if ext == ".mpd":
            fname = os.path.basename(clean_u).replace(".mpd", "") or "DASH Medya Akışı"
            return ExtractorResult(
                success=True,
                title=fname,
                video_url=url,
                video_headers=DEFAULT_HEADERS,
                audio_tracks=[],
                subtitles=[],
                total_segments=0,
                direct_file=False,
                raw_url=url
            )

        # 3. Direct Binary Video File (.mp4, .mkv, .webm, etc.)
        fname = os.path.basename(clean_u) or "Doğrudan Video Dosyası"
        return ExtractorResult(
            success=True,
            title=fname,
            video_url=url,
            video_headers=DEFAULT_HEADERS,
            audio_tracks=[],
            subtitles=[],
            total_segments=1,
            direct_file=True,
            raw_url=url
        )


__all__ = ["GenericMediaExtractor", "DirectMediaExtractor"]
