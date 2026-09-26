# -*- coding: utf-8 -*-
"""Generic final fallback for yt-dlp and inline direct-media pages."""

from __future__ import annotations

import html as html_module
import os
import re
import sys
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse

from extractors.base import DEFAULT_HEADERS, BaseExtractor, ExtractorResult
from logger import get_logger

logger = get_logger("extractors.universal")

try:
    import yt_dlp
except ImportError:
    yt_dlp = None


_DIRECT_MEDIA_EXTENSIONS = (".mp4", ".m4v", ".webm", ".mov")
_KVS_VIDEO_FIELD_RE = re.compile(
    r"(?P<key>video_(?:alt_)?url\d*)\s*[:=]\s*"
    r"(?P<quote>['\"])(?P<value>(?:\\.|(?!\2).)*?)(?P=quote)",
    re.IGNORECASE | re.DOTALL,
)
_KVS_TEXT_FIELD_RE = re.compile(
    r"(?P<key>video_(?:alt_)?url\d*_text)\s*[:=]\s*"
    r"(?P<quote>['\"])(?P<value>(?:\\.|(?!\2).)*?)(?P=quote)",
    re.IGNORECASE | re.DOTALL,
)
_HEIGHT_RE = re.compile(r"(?<!\d)(\d{3,4})\s*p(?![a-z0-9])", re.IGNORECASE)
_DIMENSION_HEIGHT_RE = re.compile(r"(?<!\d)\d{3,4}\s*x\s*(\d{3,4})(?!\d)", re.IGNORECASE)
_JS_UNICODE_ESCAPE_RE = re.compile(r"\\u([0-9a-fA-F]{4})|\\x([0-9a-fA-F]{2})")


@dataclass(frozen=True)
class _InlineCandidate:
    url: str
    height: int
    confidence: int


class _InlineMediaHTMLParser(HTMLParser):
    """Collect explicit page-level media declarations, not arbitrary MP4 text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: List[str] = []
        self.media_values: List[tuple[str, str]] = []
        self._inside_title = False
        self._video_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        attr_map = {str(key).lower(): value for key, value in attrs if value is not None}
        tag = tag.lower()
        if tag == "title":
            self._inside_title = True
        if tag == "video":
            self._video_depth += 1
            if attr_map.get("src"):
                self.media_values.append((attr_map["src"], attr_map.get("data-res", "")))
        elif tag == "source" and self._video_depth and attr_map.get("src"):
            label = attr_map.get("label") or attr_map.get("res") or attr_map.get("data-res") or ""
            self.media_values.append((attr_map["src"], label))
        elif tag == "meta":
            property_name = (attr_map.get("property") or attr_map.get("name") or "").lower()
            if property_name in {"og:video", "og:video:url", "og:video:secure_url"}:
                content = attr_map.get("content")
                if content:
                    self.media_values.append((content, attr_map.get("data-res", "")))

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self._inside_title = False
        elif tag == "video" and self._video_depth:
            self._video_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._inside_title:
            self.title_parts.append(data)


class _YtDlpLogger:
    """Keep an expected generic-extractor miss out of stderr before inline fallback."""

    def debug(self, message: str) -> None:
        logger.debug("yt-dlp: %s", message)

    def info(self, message: str) -> None:
        logger.debug("yt-dlp: %s", message)

    def warning(self, message: str) -> None:
        logger.debug("yt-dlp warning: %s", message)

    def error(self, message: str) -> None:
        logger.debug("yt-dlp error: %s", message)


def _decode_javascript_string(value: str) -> str:
    def replace_escape(match: re.Match) -> str:
        code = match.group(1) or match.group(2)
        return chr(int(code, 16))

    value = html_module.unescape(value.strip())
    value = _JS_UNICODE_ESCAPE_RE.sub(replace_escape, value)
    return value.replace(r"\/", "/").replace(r"\\", "\\")


def _media_height(*values: str) -> int:
    heights: List[int] = []
    for value in values:
        matches = list(_HEIGHT_RE.finditer(value or ""))
        matches.extend(_DIMENSION_HEIGHT_RE.finditer(value or ""))
        for match in matches:
            height = int(match.group(1))
            if 144 <= height <= 4320:
                heights.append(height)
    return max(heights, default=0)


def _looks_like_direct_media(url: str) -> bool:
    path = urlparse(url).path.lower().rstrip("/")
    return path.endswith(_DIRECT_MEDIA_EXTENSIONS)


def _extract_inline_candidates(page_html: str, base_url: str) -> tuple[str, List[_InlineCandidate]]:
    parser = _InlineMediaHTMLParser()
    try:
        parser.feed(page_html)
    except Exception:
        logger.debug("Inline media HTML parser could not consume the complete page", exc_info=True)

    text_labels: Dict[str, str] = {}
    for match in _KVS_TEXT_FIELD_RE.finditer(page_html):
        text_labels[match.group("key").lower().removesuffix("_text")] = _decode_javascript_string(
            match.group("value")
        )

    candidates: Dict[str, _InlineCandidate] = {}

    def add_candidate(raw_url: str, label: str, confidence: int) -> None:
        decoded_url = _decode_javascript_string(raw_url)
        absolute_url = urljoin(base_url, decoded_url)
        if not absolute_url.lower().startswith(("http://", "https://")):
            return
        if not _looks_like_direct_media(absolute_url):
            return
        candidate = _InlineCandidate(
            url=absolute_url,
            height=_media_height(label, absolute_url),
            confidence=confidence,
        )
        previous = candidates.get(absolute_url)
        if previous is None or (candidate.confidence, candidate.height) > (
            previous.confidence,
            previous.height,
        ):
            candidates[absolute_url] = candidate

    for match in _KVS_VIDEO_FIELD_RE.finditer(page_html):
        key = match.group("key").lower()
        add_candidate(match.group("value"), text_labels.get(key, ""), confidence=3)

    for media_value, label in parser.media_values:
        add_candidate(media_value, label, confidence=2)

    ordered = sorted(
        candidates.values(),
        key=lambda candidate: (candidate.height, candidate.confidence),
        reverse=True,
    )
    title = " ".join(" ".join(parser.title_parts).split()) or "Evrensel Medya"
    return title, ordered


def _cookie_header(session) -> str:
    cookies = getattr(session, "cookies", None)
    if cookies is None:
        return ""
    try:
        values = cookies.get_dict()
    except Exception:
        logger.debug("Inline media session cookies could not be exported", exc_info=True)
        return ""
    return "; ".join(f"{key}={value}" for key, value in values.items())


def _stream_headers(page_url: str, session) -> Dict[str, str]:
    headers = {
        "User-Agent": DEFAULT_HEADERS["User-Agent"],
        "Accept": "video/webm,video/mp4,video/*;q=0.9,*/*;q=0.8",
        "Referer": page_url,
    }
    parsed = urlparse(page_url)
    if parsed.scheme and parsed.netloc:
        headers["Origin"] = f"{parsed.scheme}://{parsed.netloc}"
    session_headers = getattr(session, "headers", None)
    if session_headers:
        for key in ("User-Agent", "Accept-Language"):
            if session_headers.get(key):
                headers[key] = session_headers[key]
    cookie = _cookie_header(session)
    if cookie:
        headers["Cookie"] = cookie
    return headers


def _probe_direct_media(session, media_url: str, headers: Dict[str, str]) -> bool:
    response = None
    probe_headers = dict(headers)
    probe_headers["Range"] = "bytes=0-1023"
    try:
        response = session.get(
            media_url,
            headers=probe_headers,
            timeout=(5, 12),
            allow_redirects=True,
            stream=True,
        )
        if response.status_code not in (200, 206):
            return False
        response_headers = getattr(response, "headers", {}) or {}
        content_type = response_headers.get("Content-Type", "").lower()
        content_range = response_headers.get("Content-Range", "")
        if content_type.startswith("video/") or content_range.lower().startswith("bytes "):
            return True
        iterator = response.iter_content(chunk_size=1024)
        first_chunk = next(iterator, b"")
        return b"ftyp" in first_chunk[:64] or first_chunk.startswith(b"\x1aE\xdf\xa3")
    except Exception:
        logger.debug("Inline direct media probe failed for %s", media_url, exc_info=True)
        return False
    finally:
        if response is not None:
            try:
                response.close()
            except Exception:
                logger.debug("Inline direct media probe response could not close", exc_info=True)


def _resolve_inline_media(url: str, session=None) -> Optional[ExtractorResult]:
    owns_session = session is None
    if session is None:
        import requests

        session = requests.Session()

    page_response = None
    page_headers = dict(DEFAULT_HEADERS)
    page_headers["Referer"] = url
    try:
        page_response = session.get(url, headers=page_headers, timeout=(5, 15), allow_redirects=True)
        if page_response.status_code != 200:
            return None
        final_page_url = getattr(page_response, "url", "") or url
        title, candidates = _extract_inline_candidates(page_response.text, final_page_url)
        if not candidates:
            return None
        media_headers = _stream_headers(final_page_url, session)
        available_candidates = [
            candidate
            for candidate in candidates
            if _probe_direct_media(session, candidate.url, media_headers)
        ]
        if not available_candidates:
            return None

        selected = available_candidates[0]
        qualities = []
        for index, candidate in enumerate(available_candidates, start=1):
            resolution = f"{candidate.height}p" if candidate.height else "auto"
            label = f"🎬 {resolution}" if candidate.height else f"🎬 Doğrudan Dosya {index}"
            qualities.append({
                "label": label,
                "resolution": resolution,
                "bandwidth": 0,
                "url": candidate.url,
                "direct_file": True,
            })

        return ExtractorResult(
            success=True,
            title=title,
            video_url=selected.url,
            video_headers=media_headers,
            audio_tracks=[{
                "name": "Doğrudan MP4 Akışı",
                "lang": "und",
                "sample_segment_url": selected.url,
                "count": 1,
                "headers": media_headers,
            }],
            subtitles=[],
            total_segments=1,
            direct_file=True,
            is_yt_dlp=False,
            raw_url=url,
            qualities=qualities,
        )
    except Exception:
        logger.debug("Inline direct media page resolution failed for %s", url, exc_info=True)
        return None
    finally:
        if page_response is not None:
            try:
                page_response.close()
            except Exception:
                logger.debug("Inline media page response could not close", exc_info=True)
        if owns_session:
            try:
                session.close()
            except Exception:
                logger.debug("Inline media session could not close", exc_info=True)


class UniversalYtDlpExtractor(BaseExtractor):
    @property
    def name(self) -> str:
        return "Universal yt-dlp Engine"

    def can_handle(self, url: str) -> bool:
        parsed = urlparse(url)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    def extract(self, url: str, session=None, log_callback=None) -> Optional[ExtractorResult]:
        def log(msg):
            if log_callback:
                try:
                    log_callback(msg)
                except Exception:
                    logger.debug("Universal extractor log callback failed", exc_info=True)
            logger.info(msg)

        if yt_dlp is not None:
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
                "skip_download": True,
                "extract_flat": False,
                "socket_timeout": 15,
                "extractor_args": {
                    "youtube": {
                        "player_client": ["android_creator", "android", "web", "mweb"]
                    }
                },
                "http_headers": {"User-Agent": DEFAULT_HEADERS["User-Agent"]},
                "logger": _YtDlpLogger(),
            }

            os.environ.setdefault("YTDLP_NO_PLUGINS", "1")
            saved_extractor_mod = sys.modules.get("extractor")
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    if info and info.get("url"):
                        title = info.get("title") or "Evrensel Medya"
                        video_url = info.get("url")
                        direct = not any(ext in video_url.lower() for ext in [".m3u8", ".mpd"])
                        known_segment_count = 1 if direct else 0
                        extractor_name = info.get("extractor_key") or info.get("extractor") or "Universal"
                        source_host = urlparse(url).netloc.lower()
                        is_youtube_result = "youtube" in str(extractor_name).lower()
                        is_youtube_input = "youtube.com" in source_host or source_host == "youtu.be"
                        if is_youtube_result and not is_youtube_input:
                            logger.debug(
                                "Universal fallback embedded YouTube result rejected for %s",
                                source_host,
                            )
                        else:
                            log(f"[+] Evrensel Motor ile medya akışı çözüldü: '{title}' [{extractor_name}]")
                            media_headers = info.get("http_headers", {})
                            return ExtractorResult(
                                success=True,
                                title=title,
                                video_url=video_url,
                                video_headers=media_headers,
                                audio_tracks=[{
                                    "name": f"{extractor_name} Akışı",
                                    "lang": "und",
                                    "sample_segment_url": video_url,
                                    "count": known_segment_count,
                                    "headers": media_headers,
                                }],
                                subtitles=[],
                                total_segments=known_segment_count,
                                direct_file=direct,
                                is_yt_dlp=True,
                                raw_url=url,
                            )
            except Exception as ex:
                logger.debug("Universal yt-dlp resolution note: %s", ex)
            finally:
                if saved_extractor_mod is not None:
                    sys.modules["extractor"] = saved_extractor_mod

        inline_result = _resolve_inline_media(url, session=session)
        if inline_result is not None:
            log(f"[+] Sayfadaki doğrudan medya akışı çözüldü: '{inline_result.title}'")
        return inline_result
