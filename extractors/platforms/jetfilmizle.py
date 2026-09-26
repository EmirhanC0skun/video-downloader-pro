# -*- coding: utf-8 -*-
"""
Video Downloader Pro — JetFilmizle Platform Extractor.
Resolves film_id post requests, /jetplayer API, Videopark and Streamwish streams.
"""

import json
import re
import unicodedata
from urllib.parse import urlparse, urljoin, parse_qs
import requests

try:
    from curl_cffi import requests as c_requests
except Exception:
    c_requests = None

from extractors.base import BaseExtractor, ExtractorResult, DEFAULT_HEADERS
from extractors.embeds.players import resolve_videopark_embed
from extractors.embeds.streamwish import resolve_streamwish_embed
from extractors.embeds.vidmoly import resolve_vidmoly_embed
from extractors.subtitles import extract_subtitles_from_tracks, extract_subtitles_from_m3u8
from extractors.variants import extract_master_quality_variants, extract_media_playlist_timeline
from logger import get_logger

logger = get_logger("extractors.platforms.jetfilmizle")


_ORIGINAL_AUDIO_LANGUAGES = {
    "ingilizce": ("eng", "İngilizce"),
    "english": ("eng", "İngilizce"),
    "japonca": ("jpn", "Japonca"),
    "japanese": ("jpn", "Japonca"),
    "fransizca": ("fra", "Fransızca"),
    "french": ("fra", "Fransızca"),
    "rusca": ("rus", "Rusça"),
    "russian": ("rus", "Rusça"),
    "almanca": ("deu", "Almanca"),
    "german": ("deu", "Almanca"),
    "ispanyolca": ("spa", "İspanyolca"),
    "spanish": ("spa", "İspanyolca"),
    "italyanca": ("ita", "İtalyanca"),
    "italian": ("ita", "İtalyanca"),
    "korece": ("kor", "Korece"),
    "korean": ("kor", "Korece"),
    "cince": ("zho", "Çince"),
    "chinese": ("zho", "Çince"),
    "hintce": ("hin", "Hintçe"),
    "hindi": ("hin", "Hintçe"),
    "portekizce": ("por", "Portekizce"),
    "portuguese": ("por", "Portekizce"),
    "arapca": ("ara", "Arapça"),
    "arabic": ("ara", "Arapça"),
}


def _normalize_language_name(value):
    value = str(value or "").casefold().translate(str.maketrans({"ı": "i"}))
    return "".join(
        character
        for character in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(character)
    ).strip()


def _extract_original_audio_language(page_html):
    """Read the original audio language from the page's Movie JSON-LD genres."""
    script_pattern = re.compile(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        re.IGNORECASE | re.DOTALL,
    )
    for script_body in script_pattern.findall(page_html or ""):
        try:
            payload = json.loads(script_body.strip())
        except (TypeError, ValueError):
            continue
        candidates = payload if isinstance(payload, list) else [payload]
        for candidate in candidates:
            if not isinstance(candidate, dict) or candidate.get("@type") != "Movie":
                continue
            genres = candidate.get("genre") or []
            if isinstance(genres, str):
                genres = [genres]
            for genre in genres:
                language = _ORIGINAL_AUDIO_LANGUAGES.get(_normalize_language_name(genre))
                if language:
                    return language
    return "und", "Orijinal Dil"


def _fetch_page(session, url, headers):
    """Fetch the page with the normal session, then Chrome TLS impersonation."""
    response = None
    try:
        response = session.get(url, headers=headers, timeout=12)
    except Exception:
        logger.debug("JetFilmizle standard page fetch failed", exc_info=True)
    if response is not None and response.status_code == 200:
        return response
    if c_requests:
        try:
            return c_requests.get(
                url,
                headers=headers,
                impersonate="chrome124",
                timeout=12,
            )
        except Exception:
            logger.debug("JetFilmizle Chrome page fetch failed", exc_info=True)
    return response


def _select_preferred_film_sources(buttons):
    """Select one bounded player candidate for each language group."""
    priorities = ("moly", "streamhls", "vip", "oplay", "gold", "stape")

    def rank(button):
        clean_name = re.sub(r"<[^>]+>", " ", button[2]).strip().lower()
        for index, marker in enumerate(priorities):
            if marker in clean_name:
                return index
        return len(priorities)

    selected = []
    for player_type in ("dublaj", "altyazili"):
        candidates = [button for button in buttons if button[1] == player_type]
        if candidates:
            selected.append(min(candidates, key=rank))
    if not selected:
        general = [button for button in buttons if button[1] == "genel"]
        if general:
            selected.append(min(general, key=rank))
    return selected


class JetfilmizleExtractor(BaseExtractor):
    """Strategy extractor for JetFilmizle and JetPlayer endpoints."""

    @property
    def name(self) -> str:
        return "JetFilmizle & JetPlayer"

    def can_handle(self, url: str) -> bool:
        low = url.lower()
        return "jetfilmizle" in low

    def extract(self, url: str, session=None, log_callback=None) -> ExtractorResult:
        self.log(f"[*] JetFilmizle taranıyor: {url}", log_callback)
        sess = session or requests.Session()
        headers = dict(DEFAULT_HEADERS)
        headers["Referer"] = url

        r = _fetch_page(sess, url, headers)
        if r is None or r.status_code != 200:
            return None
        page_html = r.text
        original_lang, original_lang_label = _extract_original_audio_language(page_html)

        title_m = re.search(r'<title>([^<]+)</title>', page_html)
        film_title = title_m.group(1).split("izle")[0].strip() if title_m else "JetFilmizle Video"

        try:
            film_id_m = (
                re.search(r'name=["\']film_id["\'][^>]*value=["\']([^"\']+)["\']', page_html)
                or re.search(r'value=["\']([^"\']+)["\'][^>]*name=["\']film_id["\']', page_html)
                or re.search(r'<input[^>]+name=["\']film_id["\'][^>]+value=["\']([^"\']+)["\']', page_html)
                or re.search(r'data-film-id=["\']([^"\']+)["\']', page_html)
                or re.search(r'film_id["\']?\s*[:=]\s*["\']?(\d+)', page_html)
            )

            if not film_id_m:
                return None

            film_id = film_id_m.group(1)
            csrf_m = (
                re.search(r'name=["\']csrf_token["\'][^>]*value=["\']([^"\']+)["\']', page_html)
                or re.search(r'value=["\']([^"\']+)["\'][^>]*name=["\']csrf_token["\']', page_html)
            )
            csrf_token = csrf_m.group(1) if csrf_m else None

            post_url = urljoin(url, "/jetplayer")
            parsed_u = urlparse(url)
            origin = f"{parsed_u.scheme}://{parsed_u.netloc}"
            post_headers = {
                'User-Agent': headers['User-Agent'],
                'Referer': url,
                'Origin': origin,
                'X-Requested-With': 'XMLHttpRequest',
                'Content-Type': 'application/x-www-form-urlencoded'
            }

            btns = re.findall(r'<button[^>]+class="[^"]*player-source-btn[^"]*"[^>]*data-source-index=["\']([^"\']+)["\'][^>]*data-player-type=["\']([^"\']+)["\'][^>]*>(.*?)</button>', page_html, re.DOTALL)
            if not btns:
                btns = re.findall(r'<button[^>]+data-source-index=["\']([^"\']+)["\'][^>]+data-player-type=["\']([^"\']+)["\'][^>]*>(.*?)</button>', page_html, re.DOTALL)

            parsed_q = parse_qs(parsed_u.query)
            req_source_index = parsed_q.get("source_index", [None])[0]
            req_season = parsed_q.get("season", [None])[0]
            req_episode = parsed_q.get("episode", [None])[0]

            is_series = "data-episode=" in page_html or "/dizi/" in url or any(b[2].strip().startswith("E") and len(b[2].strip()) <= 4 for b in btns)
            if is_series:
                if req_source_index is not None:
                    btns = [b for b in btns if str(b[0]) == str(req_source_index)] or btns[:1]
                else:
                    btns = btns[:1]
                if req_season and req_episode:
                    film_title = f"{film_title} - {req_season}. Sezon {req_episode}. Bölüm"

            if not is_series:
                btns = _select_preferred_film_sources(btns)

            audio_tracks = []
            subtitles = extract_subtitles_from_tracks(page_html, url, headers=headers)
            primary_video_url = ""
            primary_headers = {}
            primary_segments = []

            for s_idx, p_type, s_name in btns:
                try:
                    s_name_clean = s_name.strip()
                    dil_label = (
                        "Türkçe Dublaj"
                        if p_type == "dublaj"
                        else f"{original_lang_label} / Türkçe Altyazı"
                    )
                    data_body = f"film_id={film_id}&source_index={s_idx}&player_type={p_type}"
                    if csrf_token:
                        data_body += f"&csrf_token={csrf_token}"
                    if c_requests:
                        r_post = c_requests.post(post_url, headers=post_headers, data=data_body, impersonate="chrome124", timeout=10)
                    else:
                        r_post = sess.post(post_url, headers=post_headers, data=data_body, timeout=10)

                    if r_post.status_code == 200:
                        post_subs = extract_subtitles_from_tracks(r_post.text, post_url, headers=post_headers)
                        if post_subs:
                            subtitles.extend(post_subs)

                        ifrs = re.findall(r'<iframe[^>]+src=[\'"]([^\'"]+)[\'"]', r_post.text)
                        for ifr in ifrs:
                            if ifr.startswith("//"):
                                ifr = "https:" + ifr
                            hls_stream = None
                            if "videopark" in ifr:
                                hls_stream = resolve_videopark_embed(ifr, session=sess, headers=headers)
                            elif "streamwish" in ifr or "swish" in ifr:
                                hls_stream = resolve_streamwish_embed(ifr, session=sess, headers=headers)
                            elif "vidmoly" in ifr:
                                hls_stream = resolve_vidmoly_embed(ifr, session=sess, headers=headers)

                            try:
                                r_ifr = c_requests.get(ifr, headers={'User-Agent': headers['User-Agent'], 'Referer': url}, impersonate='chrome124', timeout=8) if c_requests else sess.get(ifr, headers={'User-Agent': headers['User-Agent'], 'Referer': url}, timeout=8)
                                if r_ifr and r_ifr.status_code == 200:
                                    ifr_subs = extract_subtitles_from_tracks(r_ifr.text, ifr, headers={'User-Agent': headers['User-Agent'], 'Referer': ifr})
                                    if ifr_subs:
                                        subtitles.extend(ifr_subs)
                            except Exception:
                                logger.debug("Jetfilmizle iframe subtitle parse failed", exc_info=True)

                            if hls_stream:
                                mst_hdrs = {'User-Agent': headers['User-Agent'], 'Referer': ifr, 'Origin': urlparse(ifr).scheme + "://" + urlparse(ifr).netloc}
                                r_mst = sess.get(hls_stream, headers=mst_hdrs, timeout=12)
                                if r_mst.status_code == 200:
                                    m_subs = extract_subtitles_from_m3u8(r_mst.text, hls_stream, headers=mst_hdrs)
                                    if m_subs:
                                        subtitles.extend(m_subs)

                                    qual_list = extract_master_quality_variants(hls_stream, r_mst.text)
                                    sub_u = qual_list[0]["url"] if qual_list else hls_stream
                                    r_sub = sess.get(sub_u, headers=mst_hdrs, timeout=12)
                                    if r_sub.status_code == 200:
                                        sub_subs = extract_subtitles_from_m3u8(r_sub.text, sub_u, headers=mst_hdrs)
                                        if sub_subs:
                                            subtitles.extend(sub_subs)
                                        segs, segment_durations = extract_media_playlist_timeline(
                                            sub_u,
                                            r_sub.text,
                                        )
                                        if segs:
                                            audio_tracks.append({
                                                "name": f"🎬 {s_name_clean} ({dil_label})",
                                                "lang": "tur" if p_type == "dublaj" else original_lang,
                                                "sample_segment_url": segs[0],
                                                "count": len(segs),
                                                "headers": mst_hdrs,
                                                "segments": segs,
                                                "durations": segment_durations,
                                                "video_segments": segs,
                                                "video_url": sub_u,
                                                "video_headers": mst_hdrs,
                                                "is_standalone_stream": True
                                            })
                                            if not primary_video_url:
                                                primary_video_url = segs[0]
                                                primary_headers = mst_hdrs
                                                primary_segments = segs
                except Exception as loop_ex:
                    logger.debug(f"JetFilmizle source scan note: {loop_ex}")

            if primary_video_url:
                # Deduplicate subtitles by url
                seen_sub_urls = set()
                dedup_subs = []
                for s in subtitles:
                    u_s = s.get("url") if isinstance(s, dict) else s
                    if u_s and u_s not in seen_sub_urls:
                        seen_sub_urls.add(u_s)
                        dedup_subs.append(s)

                return ExtractorResult(
                    success=True,
                    title=film_title,
                    video_url=primary_video_url,
                    video_headers=primary_headers,
                    audio_tracks=audio_tracks,
                    subtitles=dedup_subs,
                    total_segments=len(primary_segments),
                    direct_file=False,
                    video_segments=primary_segments if primary_segments else None,
                    raw_url=url
                )
        except Exception as jet_err:
            logger.debug(f"JetFilmizle resolution error: {jet_err}")

        return None


__all__ = ["JetfilmizleExtractor"]
