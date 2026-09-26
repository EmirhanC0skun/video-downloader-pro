# -*- coding: utf-8 -*-
"""
Series and Film Streaming Mirror Extractor.
Extracts JWPlayer, AES-256 decrypted streams, multi-audio tracks and subtitles
for platforms such as Diziyou, HDFilmcehennemi, DiziBox, and Diziwatch.
Dynamically parses segment counts directly from playlist streams.
"""

import re
import requests
from typing import Optional
from urllib.parse import urlparse, urljoin
from extractors.base import BaseExtractor, ExtractorResult
from extractors.subtitles import extract_subtitles_from_m3u8, extract_subtitles_from_tracks
from logger import get_logger
from exceptions import ISPBlockError

logger = get_logger("extractors.series_film")


class SeriesFilmExtractor(BaseExtractor):
    """Handles Turkish and international film/series/anime streaming mirrors and embed hosts."""

    SUPPORTED_DOMAINS = [
        "diziyou", "hdfilmcehennemi", "hdfilmizle", "dizibox", "diziwatch",
        "fullhdfilmizlesene", "fullhdfilmizle", "filmmodu", "sezonlukdizi",
        "unutulmazfilmler", "roketdizi", "asyadizi", "turkcealtyazi",
        "himovies", "bflix", "sflix", "vidsrc", "2embed", "flixhq",
        "turkanime", "aniwatch", "hianime", "animecix", "bicaps",
        "jetfilmizle", "yabancidizi", "dizilla", "lookmovie", "dizipal", "dplayer",
        "vidmoly", "closeload", "streamwish", "filelions", "voe", "sibnet"
    ]

    @property
    def name(self) -> str:
        return "Series, Film & Anime Multi-Mirror Extractor"

    def can_handle(self, url: str) -> bool:
        domain = urlparse(url).netloc.lower()
        return any(site in domain for site in self.SUPPORTED_DOMAINS)

    def extract(self, url: str, session=None, log_callback=None) -> Optional[ExtractorResult]:
        def log(msg):
            if log_callback:
                try:
                    log_callback(msg)
                except Exception:
                    logger.debug("Series/film log callback failed", exc_info=True)
            logger.info(msg)

        # NOT: Burada bilerek extractor.resolve_film_page() cagrilmaz.
        # resolve_film_page artik bu kayit defterini SON CARE olarak kullaniyor;
        # geri cagirmak sonsuz ozyineleme uretirdi (bkz. C2).
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": url
        }

        try:
            r = (session or requests).get(url, headers=headers, timeout=12)
            if r.status_code != 200:
                return None

            html = r.text
            if "erisime_engellenmis" in html or "mahkeme karari" in html.lower():
                raise ISPBlockError(f"Access to {url} is blocked by ISP.", details={"url": url})

            title_match = re.search(r'<title>([^<]+)</title>', html, re.IGNORECASE)
            title = title_match.group(1).strip() if title_match else "Dizi/Film Akışı"
            title = re.sub(r'[\r\n\t]+', ' ', title).strip()

            # BiCaps ayni sayfada dublajli (trd) ve altyazili/orijinal (tra)
            # oynaticilari JavaScript HTML'i olarak tutar. Genel iframe fallback'i
            # ilk kaynakta dondugu icin iki dil secenegini burada birlikte coz.
            if "bicaps" in urlparse(url).netloc.lower():
                source_matches = re.findall(
                    r'<!--\s*baslik:([^,>]*),(trd|tra)\s*-->\s*'
                    r'<iframe[^>]+src=["\']([^"\']+)',
                    html,
                    re.IGNORECASE | re.DOTALL,
                )
                source_groups = {"trd": [], "tra": []}
                for source_name, language_key, iframe_url in source_matches:
                    full_iframe_url = urljoin(url, iframe_url.strip())
                    candidate = (source_name.strip(), full_iframe_url)
                    if candidate not in source_groups[language_key.lower()]:
                        source_groups[language_key.lower()].append(candidate)

                if any(source_groups.values()):
                    from extractors.embeds.players import resolve_biplayer_embed

                    bicaps_tracks = []
                    bicaps_subtitles = []
                    for language_key in ("trd", "tra"):
                        for source_name, iframe_url in source_groups[language_key]:
                            bp_data = resolve_biplayer_embed(
                                iframe_url,
                                session=session,
                                headers=headers,
                                return_meta=True,
                            )
                            if not isinstance(bp_data, dict):
                                continue
                            stream_url = bp_data.get("url")
                            segments = bp_data.get("video_segments") or bp_data.get("segments") or []
                            if not stream_url or not segments:
                                continue
                            stream_headers = bp_data.get("headers") or {
                                "User-Agent": headers["User-Agent"],
                                "Referer": iframe_url,
                            }
                            is_dubbed = language_key == "trd"
                            bicaps_tracks.append({
                                "name": (
                                    "T\u00fcrk\u00e7e Dublaj"
                                    if is_dubbed
                                    else "Orijinal / T\u00fcrk\u00e7e Altyaz\u0131l\u0131"
                                ),
                                "lang": "tur" if is_dubbed else "eng",
                                "url": stream_url,
                                "sample_segment_url": segments[0],
                                "segments": segments,
                                "durations": bp_data.get("durations"),
                                "count": len(segments),
                                "headers": stream_headers,
                                "video_url": stream_url,
                                "video_segments": segments,
                                "video_headers": stream_headers,
                                "is_standalone_stream": True,
                                "source": source_name,
                            })
                            bicaps_subtitles.extend(bp_data.get("subtitles") or [])
                            break

                    if bicaps_tracks:
                        seen_subtitle_urls = set()
                        deduped_subtitles = []
                        for subtitle in bicaps_subtitles:
                            subtitle_url = subtitle.get("url") if isinstance(subtitle, dict) else subtitle
                            if subtitle_url and subtitle_url not in seen_subtitle_urls:
                                seen_subtitle_urls.add(subtitle_url)
                                deduped_subtitles.append(subtitle)
                        primary_track = bicaps_tracks[0]
                        return ExtractorResult(
                            success=True,
                            title=title,
                            video_url=primary_track["video_url"],
                            video_headers=primary_track["video_headers"],
                            audio_tracks=bicaps_tracks,
                            subtitles=deduped_subtitles,
                            total_segments=primary_track["count"],
                            direct_file=False,
                            video_segments=primary_track["video_segments"],
                            raw_url=url,
                        )

            m3u8_matches = re.findall(r'["\'](https?://[^"\']+\.m3u8[^"\']*)["\']', html)
            if m3u8_matches:
                m3u8_url = m3u8_matches[0]
                audio_tracks = []
                subtitles = extract_subtitles_from_tracks(html, url, headers=headers)
                try:
                    r_m = (session or requests).get(m3u8_url, headers=headers, timeout=8)
                    if r_m.status_code == 200:
                        for line in r_m.text.splitlines():
                            if line.startswith("#EXT-X-MEDIA:TYPE=AUDIO"):
                                name_m = re.search(r'NAME=["\']([^"\']+)["\']', line)
                                uri_m = re.search(r'URI=["\']([^"\']+)["\']', line)
                                a_name = name_m.group(1) if name_m else "Ses Akışı"
                                a_uri = urljoin(m3u8_url, uri_m.group(1)) if uri_m else m3u8_url
                                audio_tracks.append({"name": a_name, "url": a_uri})
                        m_subs = extract_subtitles_from_m3u8(r_m.text, m3u8_url, headers=headers)
                        if m_subs:
                            subtitles.extend(m_subs)
                except Exception:
                    logger.debug("[extractors/series_film.py:84] extract() sessiz istisna yutuldu", exc_info=True)

                seen_s = set()
                dedup_s = []
                for s in subtitles:
                    u_s = s.get("url") if isinstance(s, dict) else s
                    if u_s and u_s not in seen_s:
                        seen_s.add(u_s)
                        dedup_s.append(s)

                return ExtractorResult(
                    success=True,
                    title=title,
                    video_url=m3u8_url,
                    video_headers=headers,
                    audio_tracks=audio_tracks,
                    subtitles=dedup_s,
                    total_segments=0,
                    direct_file=False,
                    raw_url=url
                )

            # Fallback: Oynatıcı iFrame taraması (BiPlayer, PopcornVakti, VidMoly, vb.)
            iframes = re.findall(r'<iframe[^>]+src=["\']([^"\']+)["\']', html)
            for ifr in iframes:
                full_ifr = urljoin(url, ifr)
                if "biplayer" in full_ifr:
                    from extractors.embeds.players import resolve_biplayer_embed
                    bp_data = resolve_biplayer_embed(full_ifr, session=session, headers=headers, return_meta=True)
                    if bp_data:
                        v_u = bp_data.get("url") if isinstance(bp_data, dict) else bp_data
                        v_s = bp_data.get("subtitles", []) if isinstance(bp_data, dict) else []
                        v_segs = (bp_data.get("video_segments") or bp_data.get("segments")) if isinstance(bp_data, dict) else None
                        if v_u:
                            is_dir = False if (v_segs or ".m3u8" in v_u or ".png" in v_u) else True
                            v_hdrs = bp_data.get("headers", {"User-Agent": headers["User-Agent"], "Referer": full_ifr}) if isinstance(bp_data, dict) else {"User-Agent": headers["User-Agent"], "Referer": full_ifr}
                            return ExtractorResult(
                                success=True,
                                title=title,
                                video_url=v_u,
                                video_headers=v_hdrs,
                                audio_tracks=[],
                                subtitles=v_s,
                                total_segments=len(v_segs) if v_segs else 0,
                                direct_file=is_dir,
                                video_segments=v_segs,
                                raw_url=url
                            )
                elif "popcornvakti" in full_ifr:
                    from extractors.embeds.players import resolve_popcornvakti_embed
                    pv_data = resolve_popcornvakti_embed(full_ifr, session=session, headers=headers, return_meta=True)
                    if pv_data:
                        v_u = pv_data.get("url") if isinstance(pv_data, dict) else pv_data
                        v_s = pv_data.get("subtitles", []) if isinstance(pv_data, dict) else []
                        v_segs = (pv_data.get("video_segments") or pv_data.get("segments")) if isinstance(pv_data, dict) else None
                        if v_u:
                            is_dir = False if (v_segs or ".m3u8" in v_u or ".png" in v_u) else True
                            v_hdrs = pv_data.get("headers", {"User-Agent": headers["User-Agent"], "Referer": full_ifr}) if isinstance(pv_data, dict) else {"User-Agent": headers["User-Agent"], "Referer": full_ifr}
                            return ExtractorResult(
                                success=True,
                                title=title,
                                video_url=v_u,
                                video_headers=v_hdrs,
                                audio_tracks=[],
                                subtitles=v_s,
                                total_segments=len(v_segs) if v_segs else 0,
                                direct_file=is_dir,
                                video_segments=v_segs,
                                raw_url=url
                            )
        except ISPBlockError:
            raise
        except Exception as e:
            logger.debug(f"SeriesFilmExtractor scan notice: {e}")
            return None

        return None
