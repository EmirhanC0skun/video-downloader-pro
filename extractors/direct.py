# -*- coding: utf-8 -*-
"""
Direct Media and M3U8 Extractor.
Dynamically parses segment counts from HLS playlists without hard-coding.
"""

import os
import re
from urllib.parse import urljoin
from extractors.base import BaseExtractor, ExtractorResult
from logger import get_logger

logger = get_logger("extractors.direct")


class DirectMediaExtractor(BaseExtractor):
    @property
    def name(self) -> str:
        return "Direct Media / M3U8"

    def can_handle(self, url: str) -> bool:
        clean_u = url.split("?")[0].split("#")[0].lower()
        direct_exts = (".mp4", ".mkv", ".webm", ".avi", ".mov", ".flv", ".m4v", ".m3u8")
        return any(clean_u.endswith(ext) for ext in direct_exts)

    def extract(self, url: str, session=None, log_callback=None) -> ExtractorResult:
        clean_u = url.split("?")[0].split("#")[0]
        
        # 1. Direct M3U8 Playlist
        if clean_u.lower().endswith(".m3u8"):
            fname = os.path.basename(clean_u).replace(".m3u8", "") or "HLS Medya Akışı"
            audio_tracks = []
            total_segments = 1
            
            if session:
                try:
                    r_m3u8 = session.get(url, timeout=10)
                    if r_m3u8.status_code == 200:
                        m_text = r_m3u8.text
                        # Parse audio tracks
                        for line in m_text.splitlines():
                            if line.startswith("#EXT-X-MEDIA:TYPE=AUDIO"):
                                name_m = re.search(r'NAME=["\']([^"\']+)["\']', line)
                                uri_m = re.search(r'URI=["\']([^"\']+)["\']', line)
                                if name_m:
                                    a_name = name_m.group(1)
                                    full_a_uri = urljoin(url, uri_m.group(1)) if uri_m else url
                                    audio_tracks.append({"name": a_name, "url": full_a_uri})
                        
                        # Dynamically count EXTINF segments
                        extinf_count = len(re.findall(r'#EXTINF:', m_text))
                        if extinf_count > 0:
                            total_segments = extinf_count
                except Exception as ex:
                    logger.debug(f"Direct M3U8 metadata fetch note: {ex}")

            return ExtractorResult(
                success=True,
                title=fname,
                video_url=url,
                video_headers={"User-Agent": "Mozilla/5.0", "Accept": "*/*"},
                audio_tracks=audio_tracks,
                total_segments=total_segments,
                direct_file=False,
                raw_url=url
            )

        # 2. Direct Video File (.mp4, .mkv, etc.)
        fname = os.path.basename(clean_u) or "Doğrudan Video Dosyası"
        return ExtractorResult(
            success=True,
            title=fname,
            video_url=url,
            video_headers={"User-Agent": "Mozilla/5.0", "Accept": "*/*"},
            audio_tracks=[],
            total_segments=1,
            direct_file=True,
            raw_url=url
        )
