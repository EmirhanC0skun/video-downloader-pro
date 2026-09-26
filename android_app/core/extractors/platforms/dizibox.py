# -*- coding: utf-8 -*-
"""
Video Downloader Pro — DiziBox Platform Extractor.
Resolves Dizibox King/Molystream player bridges, CryptoJS decrypted playlists, and image segments.
"""

import re
import tempfile
from urllib.parse import urljoin, urlparse, urlunparse
import requests

try:
    from curl_cffi import requests as c_requests
except Exception:
    c_requests = None

from extractors.base import BaseExtractor, ExtractorResult, DEFAULT_HEADERS
from extractors.generic_hls import decrypt_cryptojs_aes, unpack_js
from extractors.subtitles import extract_subtitles_from_m3u8
from extractors.variants import extract_master_quality_variants, extract_media_playlist_timeline
from logger import get_logger

logger = get_logger("extractors.platforms.dizibox")


def _page_candidates(url):
    parsed = urlparse(url)
    current_path = re.sub(r'-hd-izle/?$', '/', parsed.path, flags=re.IGNORECASE)
    hosts = [parsed.netloc]
    if parsed.netloc.lower() != "www.dizibox.lol":
        hosts.append("www.dizibox.lol")
    paths = [parsed.path]
    if current_path != parsed.path:
        paths.append(current_path)

    candidates = []
    for host in hosts:
        for path in paths:
            candidate = urlunparse((parsed.scheme or "https", host, path, "", parsed.query, ""))
            if candidate not in candidates:
                candidates.append(candidate)
    return candidates


def _fetch_dizibox_browser_page(url):
    """Read a managed Cloudflare page with the project's installed Chrome."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.debug("Playwright is unavailable for the Dizibox browser fallback")
        return None

    try:
        with tempfile.TemporaryDirectory(prefix="vdp_dizibox_") as profile_dir:
            with sync_playwright() as playwright:
                context = None
                launch_args = [
                    "--window-position=-32000,-32000",
                    "--disable-blink-features=AutomationControlled",
                    "--no-first-run",
                    "--no-default-browser-check",
                ]
                for channel in ("chrome", "msedge"):
                    try:
                        context = playwright.chromium.launch_persistent_context(
                            profile_dir,
                            headless=False,
                            channel=channel,
                            args=launch_args,
                            viewport={"width": 1280, "height": 720},
                        )
                        break
                    except Exception as launch_exc:
                        logger.debug("Dizibox %s browser launch failed: %s", channel, launch_exc)
                if context is None:
                    return None
                try:
                    page = context.pages[0] if context.pages else context.new_page()
                    media_embeds = []

                    def capture_embed(request):
                        request_url = request.url
                        if any(
                            marker in request_url.lower()
                            for marker in ("molystream", "vidmoly", "sheila")
                        ) and request_url not in media_embeds:
                            media_embeds.append(request_url)

                    page.on("request", capture_embed)
                    page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                    page.wait_for_timeout(5_000)
                    title = (page.title() or "").lower()
                    if any(marker in title for marker in ("just a moment", "bir dakika", "attention required")):
                        return None
                    page_html = page.content()
                    if media_embeds:
                        injected = "".join(
                            f'<iframe src="{embed_url}"></iframe>'
                            for embed_url in media_embeds
                        )
                        page_html += injected
                    return page_html if "<iframe" in page_html.lower() else None
                finally:
                    context.close()
    except Exception as browser_exc:
        logger.debug("Dizibox browser page fallback failed: %s", browser_exc, exc_info=True)
        return None


def _resolve_plain_hls(session, master_url, player_html, stream_headers, title, raw_url):
    response = session.get(master_url, headers=stream_headers, timeout=12)
    if response.status_code != 200 or "#EXTM3U" not in response.text:
        return None

    master_text = response.text
    variants = extract_master_quality_variants(master_url, master_text)
    media_url = variants[0]["url"] if variants else master_url
    media_text = master_text
    if variants:
        media_response = session.get(media_url, headers=stream_headers, timeout=12)
        if media_response.status_code != 200:
            return None
        media_text = media_response.text

    video_segments, video_durations = extract_media_playlist_timeline(media_url, media_text)
    if not video_segments:
        return None

    audio_tracks = []
    for line in master_text.splitlines():
        if not line.upper().startswith("#EXT-X-MEDIA:TYPE=AUDIO"):
            continue
        uri_match = re.search(r'URI=["\']([^"\']+)["\']', line, re.IGNORECASE)
        if not uri_match:
            continue
        name_match = re.search(r'NAME=["\']([^"\']+)["\']', line, re.IGNORECASE)
        language_match = re.search(r'LANGUAGE=["\']([^"\']+)["\']', line, re.IGNORECASE)
        audio_name = name_match.group(1) if name_match else "Ses"
        language = (language_match.group(1) if language_match else audio_name).lower()
        audio_url = urljoin(master_url, uri_match.group(1))
        audio_response = session.get(audio_url, headers=stream_headers, timeout=12)
        if audio_response.status_code != 200:
            continue
        audio_segments, audio_durations = extract_media_playlist_timeline(
            audio_url,
            audio_response.text,
        )
        if not audio_segments:
            continue
        is_turkish = any(token in language for token in ("tur", "tr", "türk", "turk", "dub"))
        audio_tracks.append({
            "name": audio_name,
            "lang": "tur" if is_turkish else "eng",
            "sample_segment_url": audio_segments[0],
            "segments": audio_segments,
            "durations": audio_durations,
            "count": len(audio_segments),
            "headers": stream_headers,
        })

    subtitles = extract_subtitles_from_m3u8(master_text, master_url, headers=stream_headers)
    return ExtractorResult(
        success=True,
        title=title,
        video_url=media_url,
        video_headers=stream_headers,
        audio_tracks=audio_tracks,
        subtitles=subtitles,
        total_segments=len(video_segments),
        direct_file=False,
        raw_url=raw_url,
        video_segments=video_segments,
        video_durations=video_durations,
        qualities=variants,
    )


class DiziboxExtractor(BaseExtractor):
    """Strategy extractor for DiziBox episode streams and player iframes."""

    @property
    def name(self) -> str:
        return "DiziBox Platform"

    def can_handle(self, url: str) -> bool:
        low = url.lower()
        return "dizibox" in low

    def extract(self, url: str, session=None, log_callback=None) -> ExtractorResult:
        self.log(f"[*] DiziBox taranıyor: {url}", log_callback)
        sess = session or requests.Session()
        headers = dict(DEFAULT_HEADERS)
        headers["Referer"] = url

        page_html = ""
        page_url = url
        for candidate_url in _page_candidates(url):
            try:
                r = sess.get(candidate_url, headers=headers, timeout=12)
                if r.status_code != 200 and c_requests:
                    try:
                        r = c_requests.get(
                            candidate_url,
                            headers=headers,
                            impersonate="chrome124",
                            timeout=12,
                        )
                    except Exception as ex_c:
                        logger.debug("DiziBox impersonated page fetch error: %s", ex_c)
                if candidate_url == url and r.status_code in (403, 429, 503):
                    browser_html = _fetch_dizibox_browser_page(candidate_url)
                    if browser_html:
                        page_html = browser_html
                        page_url = candidate_url
                        break
                if r.status_code != 200:
                    continue
                page_html = r.text
                page_url = getattr(r, "url", "") or candidate_url
                break
            except Exception as exc:
                logger.debug("DiziBox page candidate %s failed: %s", candidate_url, exc)
        if not page_html:
            return None

        headers["Referer"] = page_url

        title_m = re.search(r'<title>([^<]+)</title>', page_html)
        film_title = title_m.group(1).split("izle")[0].strip() if title_m else "DiziBox Video"

        dizibox_player_matches = []
        iframes_in_page = re.findall(r'<iframe[^>]+src=["\']([^"\']+)["\']', page_html, re.IGNORECASE)
        for ifr in iframes_in_page:
            ifr_full = urljoin(page_url, ifr.strip())
            if any(k in ifr_full.lower() for k in ["king.php", "molystream", "vidmoly", "moly", "sheila", "player/", "spidypro"]):
                dizibox_player_matches.append(ifr_full)

        dizibox_player_matches.sort(
            key=lambda candidate: 0 if "molystream" in candidate.lower() else 1
        )

        if not dizibox_player_matches:
            dizibox_player_matches = re.findall(r'(https?://[^\s"\'<>]+(?:king\.php|molystream|vidmoly|sheila)[^\s"\'<>]*)', page_html)

        if dizibox_player_matches:
            player_page_url = dizibox_player_matches[0]
            dbx_headers = {"User-Agent": headers["User-Agent"], "Referer": page_url}
            player_html = ""
            try:
                r_player = sess.get(player_page_url, headers=dbx_headers, timeout=12)
                player_html = r_player.text
            except Exception:
                if c_requests:
                    try:
                        c_p = c_requests.get(player_page_url, headers=dbx_headers, impersonate="chrome124", timeout=12)
                        player_html = c_p.text
                    except Exception as ex_c:
                        logger.debug(f"DiziBox player page error: {ex_c}")

            embed_src = None
            iframe_match = re.search(r'<iframe[^>]+src=["\']([^"\']+)["\']', player_html)
            if iframe_match:
                embed_src = urljoin(player_page_url, iframe_match.group(1))
            elif any(host in player_page_url for host in ("molystream", "vidmoly", "spidypro")):
                embed_src = player_page_url

            if embed_src:
                moly_headers = {"User-Agent": headers["User-Agent"], "Referer": player_page_url}
                try:
                    r_moly = sess.get(embed_src, headers=moly_headers, timeout=12)
                    player_sources = [r_moly.text]
                    unpacked_player = unpack_js(r_moly.text)
                    if unpacked_player != r_moly.text:
                        player_sources.append(unpacked_player)

                    for source_text in player_sources:
                        hls_matches = re.findall(
                            r'https?:(?:\\/\\/|//)[^"\'<>\s]+?\.m3u8[^"\'<>\s]*',
                            source_text,
                            re.IGNORECASE,
                        )
                        for hls_match in hls_matches:
                            master_url = hls_match.replace(r"\/", "/")
                            result = _resolve_plain_hls(
                                sess,
                                master_url,
                                source_text,
                                moly_headers,
                                film_title,
                                url,
                            )
                            if result:
                                return result

                    aes_match = re.search(r'CryptoJS\.AES\.decrypt\(["\'](.*?)["\']\s*,\s*["\'](.*?)["\']\)', r_moly.text, re.DOTALL)
                    if aes_match:
                        ciphertext, key = aes_match.groups()
                        decrypted_html = decrypt_cryptojs_aes(ciphertext, key)
                        file_match = re.search(r'file:\s*["\'](https?://[^\s"\'<>]+)["\']', decrypted_html)
                        if file_match:
                            master_m3u8_url = file_match.group(1)
                            r_master = sess.get(master_m3u8_url, headers=moly_headers, timeout=12)
                            if r_master.status_code == 200:
                                q_lines = [l.strip() for l in r_master.text.splitlines() if l.strip() and not l.startswith("#")]
                                if q_lines:
                                    quality_url = urljoin(master_m3u8_url, q_lines[0])
                                    r_q = sess.get(quality_url, headers=moly_headers, timeout=12)
                                    if r_q.status_code == 200:
                                        segs = re.findall(r'https?://[^\s\'"<>]+\.(?:png|jpg|ts|jpeg|webp)', r_q.text)
                                        if segs:
                                            sub_files = re.findall(r'["\']file["\']\s*:\s*["\']([^"\']+\.(?:srt|vtt))["\']', decrypted_html)
                                            subtitles = [{"url": urljoin(embed_src, sf), "name": "Altyazı"} for sf in sub_files]
                                            track_headers = {"User-Agent": headers["User-Agent"], "Referer": embed_src}
                                            return ExtractorResult(
                                                success=True,
                                                title=film_title,
                                                video_url=segs[0],
                                                video_headers=track_headers,
                                                audio_tracks=[{
                                                    "name": "🎬 Full HD (1080p)",
                                                    "lang": "tur",
                                                    "sample_segment_url": segs[0],
                                                    "segments": segs,
                                                    "count": len(segs),
                                                    "headers": track_headers,
                                                    "video_segments": segs,
                                                    "video_url": quality_url,
                                                    "video_headers": track_headers,
                                                    "is_standalone_stream": True,
                                                }],
                                                subtitles=subtitles,
                                                total_segments=len(segs),
                                                direct_file=False,
                                                raw_url=url,
                                                video_segments=segs,
                                            )
                except Exception as ex_moly:
                    logger.debug(f"DiziBox molystream error: {ex_moly}")

        return None


__all__ = ["DiziboxExtractor"]
