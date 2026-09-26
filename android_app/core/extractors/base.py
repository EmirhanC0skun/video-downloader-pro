# -*- coding: utf-8 -*-
"""
Video Downloader Pro — Base Extractor Interface & Data Models.
"""

import re
from urllib.parse import urljoin
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from logger import get_logger
from extractors.variants import select_best_variant_url

logger = get_logger("extractors.base")

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7"
}

RESULT_DEFAULTS = {
    "success": True,
    "title": "Medya",
    "video_url": "",
    "video_headers": {},
    "video_segments": None,
    "video_durations": None,
    "audio_tracks": [],
    "subtitles": [],
    "qualities": [],
    "total_segments": 0,
    "direct_file": False,
    "is_yt_dlp": False,
    "raw_url": "",
}


def fix_mojibake(text: str) -> str:
    """UTF-8 baytlarının Latin-1 / Windows-1252 / ISO-8859 olarak yanlış çözülmesiyle
    oluşan Türkçe karakter bozulmalarını (Ã¶ -> ö, Ã¼ -> ü, Ä± -> ı vb.) düzeltir."""
    if not text or not isinstance(text, str):
        return text
    if any(c in text for c in ("Ã", "Ä", "Å", "Â", "â")):
        try:
            return text.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            try:
                return text.encode("windows-1252").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
    return text


def normalize_extraction_result(data, source_url=""):
    """
    Cozucu ciktisini tek bir sozlesmeye oturtur: eksik anahtarlari varsayilanla
    doldurur, `qualities` listesi yoksa mevcut akistan tek girdilik bir liste turetir
    ve `total_segments` degerini segment listesiyle tutarli hale getirir.
    """
    if not isinstance(data, dict):
        return data

    out = dict(RESULT_DEFAULTS)
    out.update(data)

    if out.get("title"):
        out["title"] = fix_mojibake(out["title"])

    if not out.get("raw_url"):
        out["raw_url"] = source_url or out.get("video_url", "")

    segs = out.get("video_segments")
    if segs and not out.get("total_segments"):
        out["total_segments"] = len(segs)

    if not out.get("qualities") and out.get("video_url"):
        res_label = "🎬 Doğrudan Dosya" if out.get("direct_file") else "🌟 En Yüksek Kalite"
        out["qualities"] = [{
            "label": res_label,
            "resolution": "auto",
            "bandwidth": 0,
            "url": out["video_url"],
        }]

    # Ses kanali hic yoksa video akisini tek kanal olarak sun; arayuz her zaman
    # en az bir secenek gormeli.
    if not out.get("audio_tracks") and out.get("video_url") and not out.get("direct_file"):
        out["audio_tracks"] = [{
            "name": "🎬 Standart / Orijinal Akış",
            "lang": "und",
            "sample_segment_url": out["video_url"],
            "segments": segs,
            "durations": out.get("video_durations"),
            "video_durations": out.get("video_durations"),
            "count": out.get("total_segments", 0),
            "headers": out.get("video_headers", {}),
        }]

    return out


@dataclass
class ExtractorResult:
    """Standardized output model for all media extractors."""
    success: bool
    title: str
    video_url: str
    video_headers: Dict[str, str] = field(default_factory=dict)
    audio_tracks: List[Dict[str, Any]] = field(default_factory=list)
    subtitles: List[Dict[str, Any]] = field(default_factory=list)
    total_segments: int = 0
    direct_file: bool = False
    is_yt_dlp: bool = False
    raw_url: str = ""
    error_message: Optional[str] = None
    video_segments: Optional[List[str]] = None
    video_durations: Optional[List[Optional[float]]] = None
    qualities: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self):
        if self.title:
            self.title = fix_mojibake(self.title)

    def to_dict(self) -> Dict[str, Any]:
        """Converts to dictionary for GUI / Mobile / Core compatibility."""
        tracks = list(self.audio_tracks) if self.audio_tracks else []
        if not tracks and self.video_segments and not self.direct_file:
            tracks = [{
                "name": "🎬 Standart / Orijinal Akış",
                "lang": "und",
                "sample_segment_url": self.video_segments[0] if self.video_segments else self.video_url,
                "segments": self.video_segments,
                "durations": self.video_durations,
                "video_durations": self.video_durations,
                "count": len(self.video_segments),
                "headers": self.video_headers,
            }]
        return {
            "success": self.success,
            "title": self.title,
            "video_url": self.video_url,
            "video_headers": self.video_headers,
            "video_segments": self.video_segments,
            "video_durations": self.video_durations,
            "audio_tracks": tracks,
            "subtitles": self.subtitles,
            "total_segments": self.total_segments or (len(self.video_segments) if self.video_segments else 0),
            "direct_file": self.direct_file,
            "is_yt_dlp": self.is_yt_dlp,
            "raw_url": self.raw_url,
            "error_message": self.error_message,
            "qualities": list(self.qualities),
        }


class BaseExtractor(ABC):
    """Abstract base class for all platform extractors."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable extractor name."""
        pass

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Determines if this extractor supports the given URL."""
        pass

    @abstractmethod
    def extract(self, url: str, session=None, log_callback=None) -> Optional[ExtractorResult]:
        """Extracts media stream and metadata from the URL."""
        pass

    def log(self, msg: str, log_callback=None):
        """Thread-safe logging dispatch to GUI callback and module logger."""
        if log_callback:
            try:
                log_callback(msg)
            except Exception as e:
                logger.debug(f"log_callback error: {e}")
        logger.info(msg)

    def _resolve_m3u8_segments(self, sess, m3u8_url, headers):
        """M3U8 URL'sinden segment listesi döndürür (master → media playlist takibi dahil)."""
        try:
            r = sess.get(m3u8_url, headers=headers, timeout=12, allow_redirects=True)
            if r.status_code != 200 or not r.text.strip().startswith("#EXTM3U"):
                return []
            lines = [l.strip() for l in r.text.splitlines() if l.strip()]
            final_url = r.url
            if any(l.startswith("#EXT-X-STREAM-INF") for l in lines):
                best = select_best_variant_url(final_url, "\n".join(lines))
            else:
                best = None
            if best:
                r2 = sess.get(best, headers=headers, timeout=12, allow_redirects=True)
                if r2.status_code == 200:
                    lines = [l.strip() for l in r2.text.splitlines() if l.strip()]
                    final_url = r2.url
            init_m = re.search(r'#EXT-X-MAP:URI=["\']([^"\']+)["\']', "\n".join(lines))
            init_segs = [urljoin(final_url, init_m.group(1))] if init_m else []
            seg_lines = [l for l in lines if not l.startswith("#") and l]
            return init_segs + [urljoin(final_url, s) for s in seg_lines]
        except Exception as ex:
            logger.debug(f"m3u8 resolve error: {ex}")
            return []
