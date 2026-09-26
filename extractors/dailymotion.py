# -*- coding: utf-8 -*-
"""
Dailymotion Native Stream Extractor.
"""

import re
from extractors.base import BaseExtractor, ExtractorResult
from logger import get_logger

logger = get_logger("extractors.dailymotion")


class DailymotionExtractor(BaseExtractor):
    @property
    def name(self) -> str:
        return "Dailymotion"

    def can_handle(self, url: str) -> bool:
        return bool(re.search(r'dailymotion\.com/(?:video|embed/video)/([a-zA-Z0-9]+)|dai\.ly/([a-zA-Z0-9]+)', url))

    def extract(self, url: str, session=None, log_callback=None) -> ExtractorResult:
        dm_match = re.search(r'dailymotion\.com/(?:video|embed/video)/([a-zA-Z0-9]+)|dai\.ly/([a-zA-Z0-9]+)', url)
        if not dm_match or not session:
            return None

        vid_id = dm_match.group(1) or dm_match.group(2)
        meta_url = f"https://www.dailymotion.com/player/metadata/video/{vid_id}"
        dm_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": f"https://www.dailymotion.com/video/{vid_id}"
        }

        try:
            r_meta = session.get(meta_url, headers=dm_headers, timeout=10)
            if r_meta.status_code == 200:
                m_data = r_meta.json()
                dm_title = m_data.get("title", f"Dailymotion_{vid_id}")
                qualities = m_data.get("qualities", {})
                auto_streams = qualities.get("auto", [])
                if auto_streams:
                    master_m3u8 = auto_streams[0].get("url")
                    return ExtractorResult(
                        success=True,
                        title=dm_title,
                        video_url=master_m3u8,
                        video_headers=dm_headers,
                        audio_tracks=[],
                        total_segments=0,
                        direct_file=False,
                        raw_url=url
                    )
        except Exception as ex:
            logger.warning(f"Dailymotion API resolution error: {ex}")

        return None
