# -*- coding: utf-8 -*-
"""
Video Downloader Pro — SezonlukDizi Platform Extractor.
Resolves dataAlternatif22.asp and dataEmbed22.asp multi-language streams.
"""

import re
from urllib.parse import urlparse, urljoin
import requests

try:
    from curl_cffi import requests as c_requests
except Exception:
    c_requests = None

from extractors.base import BaseExtractor, ExtractorResult, DEFAULT_HEADERS
from extractors.embeds.vidmoly import resolve_vidmoly_embed
from extractors.embeds.streamwish import resolve_streamwish_embed
from extractors.embeds.sibnet import resolve_sibnet_embed
from extractors.subtitles import extract_subtitles_from_tracks, extract_subtitles_from_m3u8
from extractors.variants import extract_master_quality_variants, extract_media_playlist_timeline
from logger import get_logger

logger = get_logger("extractors.platforms.sezonlukdizi")


def _prioritize_alternatives(alternatives):
    """Prefer providers whose segment timelines contain real media consistently."""
    priorities = ("vidmoly", "streamruby", "streamwish", "sibnet")

    def rank(alternative):
        title = str(alternative.get("baslik", "")).strip().lower()
        for index, marker in enumerate(priorities):
            if marker in title:
                return index
        return len(priorities)

    return sorted(alternatives or [], key=rank)


class SezonlukdiziExtractor(BaseExtractor):
    """Strategy extractor for SezonlukDizi episode mirrors."""

    @property
    def name(self) -> str:
        return "SezonlukDizi Platform"

    def can_handle(self, url: str) -> bool:
        low = url.lower()
        return "sezonlukdizi" in low

    def extract(self, url: str, session=None, log_callback=None) -> ExtractorResult:
        self.log(f"[*] SezonlukDizi taranıyor: {url}", log_callback)
        sess = session or requests.Session()
        headers = dict(DEFAULT_HEADERS)
        headers["Referer"] = url

        try:
            r = sess.get(url, headers=headers, timeout=12)
            if r.status_code != 200:
                return None
            page_html = r.text
        except Exception as e:
            logger.debug(f"SezonlukDizi fetch error: {e}")
            return None

        title_m = re.search(r'<title>([^<]+)</title>', page_html)
        film_title = title_m.group(1).split("izle")[0].strip() if title_m else "SezonlukDizi Video"

        bid_m = re.search(r'data-id=["\'](\d+)["\']', page_html) or re.search(r'data-bid=["\'](\d+)["\']', page_html)
        bid = bid_m.group(1) if bid_m else None
        if not bid:
            return None

        s_ajax = c_requests.Session(impersonate='chrome124') if c_requests else sess
        ajax_headers = {
            'User-Agent': headers['User-Agent'],
            'Referer': url,
            'Origin': f"{urlparse(url).scheme}://{urlparse(url).netloc}",
            'X-Requested-With': 'XMLHttpRequest'
        }
        audio_tracks = []
        subtitles = extract_subtitles_from_tracks(page_html, url, headers=headers)
        primary_video_url = ""
        primary_headers = {}
        primary_segments = []

        for dil in [0, 1]:  # 0: Dublaj, 1: Altyazı
            dil_label = "🇹🇷 Türkçe Dublaj" if dil == 0 else "🇬🇧 Orijinal / Altyazılı"
            data = {'bid': bid, 'dil': dil}
            try:
                r_alt = s_ajax.post('https://sezonlukdizi.cc/ajax/dataAlternatif22.asp', data=data, headers=ajax_headers, timeout=10)
                alt_json = r_alt.json()
                if alt_json.get("status") == "success" and alt_json.get("data"):
                    for alt in _prioritize_alternatives(alt_json["data"]):
                        alt_id = alt.get("id")
                        r_emb = s_ajax.post('https://sezonlukdizi.cc/ajax/dataEmbed22.asp', data={'id': alt_id}, headers=ajax_headers, timeout=10)
                        emb_html = r_emb.text
                        iframe_m = re.search(r'<iframe[^>]+src=["\']([^"\']+)["\']', emb_html)
                        if not iframe_m:
                            continue
                        embed_src = iframe_m.group(1)
                        if embed_src.startswith("//"):
                            embed_src = "https:" + embed_src
                        elif embed_src.startswith("/"):
                            embed_src = urljoin(url, embed_src)
                        if "reCAPTCHA" in embed_src or "about:blank" in embed_src:
                            continue

                        # 1. VidMoly
                        if "vidmoly" in embed_src:
                            m3u8_url = resolve_vidmoly_embed(embed_src, session=sess, headers=headers)
                            if m3u8_url:
                                v_headers = {"User-Agent": headers["User-Agent"], "Referer": "https://vidmoly.net/"}
                                try:
                                    r_m = sess.get(m3u8_url, headers=v_headers, timeout=10)
                                    if r_m.status_code == 200:
                                        m_subs = extract_subtitles_from_m3u8(r_m.text, m3u8_url, headers=v_headers)
                                        if m_subs:
                                            subtitles.extend(m_subs)
                                        quality_variants = extract_master_quality_variants(m3u8_url, r_m.text)
                                        sub_lines = [l.strip() for l in r_m.text.splitlines() if l.strip() and not l.startswith("#")]
                                        if quality_variants or sub_lines:
                                            sub_m3u8 = quality_variants[0]["url"] if quality_variants else urljoin(m3u8_url, sub_lines[-1])
                                            r_sub = sess.get(sub_m3u8, headers=v_headers, timeout=10)
                                            segs, segment_durations = extract_media_playlist_timeline(
                                                sub_m3u8,
                                                r_sub.text,
                                            )
                                            if segs:
                                                v_subs = extract_subtitles_from_tracks(emb_html, embed_src)
                                                if v_subs:
                                                    subtitles.extend(v_subs)
                                                audio_tracks.append({
                                                    "name": dil_label,
                                                    "lang": "tur" if dil == 0 else "eng",
                                                    "sample_segment_url": segs[0],
                                                    "count": len(segs),
                                                    "headers": v_headers,
                                                    "segments": segs,
                                                    "durations": segment_durations,
                                                    "video_segments": segs,
                                                    "video_url": sub_m3u8,
                                                    "video_headers": v_headers,
                                                    "is_standalone_stream": True
                                                })
                                                if not primary_video_url:
                                                    primary_video_url = segs[0]
                                                    primary_headers = v_headers
                                                    primary_segments = segs
                                                break
                                except Exception as ex_vm:
                                    logger.debug(f"VidMoly stream fetch error: {ex_vm}")

                        # 2. StreamWish
                        elif any(h in embed_src for h in ["streamwish", "rubyvidhub", "streamruby", "wishembed", "mwish"]):
                            m3u8_url = resolve_streamwish_embed(embed_src, session=sess, headers=headers)
                            if m3u8_url:
                                v_headers = {"User-Agent": headers["User-Agent"], "Referer": embed_src}
                                try:
                                    r_m = sess.get(m3u8_url, headers=v_headers, timeout=10)
                                    if r_m.status_code == 200:
                                        m_subs = extract_subtitles_from_m3u8(r_m.text, m3u8_url, headers=v_headers)
                                        if m_subs:
                                            subtitles.extend(m_subs)
                                        quality_variants = extract_master_quality_variants(m3u8_url, r_m.text)
                                        sub_lines = [l.strip() for l in r_m.text.splitlines() if l.strip() and not l.startswith("#")]
                                        if quality_variants or sub_lines:
                                            sub_m3u8 = quality_variants[0]["url"] if quality_variants else urljoin(m3u8_url, sub_lines[-1])
                                            r_sub = sess.get(sub_m3u8, headers=v_headers, timeout=10)
                                            segs, segment_durations = extract_media_playlist_timeline(
                                                sub_m3u8,
                                                r_sub.text,
                                            )
                                            if segs:
                                                v_subs = extract_subtitles_from_tracks(emb_html, embed_src)
                                                if v_subs:
                                                    subtitles.extend(v_subs)
                                                audio_tracks.append({
                                                    "name": dil_label,
                                                    "lang": "tur" if dil == 0 else "eng",
                                                    "sample_segment_url": segs[0],
                                                    "count": len(segs),
                                                    "headers": v_headers,
                                                    "segments": segs,
                                                    "durations": segment_durations,
                                                    "video_segments": segs,
                                                    "video_url": sub_m3u8,
                                                    "video_headers": v_headers,
                                                    "is_standalone_stream": True
                                                })
                                                if not primary_video_url:
                                                    primary_video_url = segs[0]
                                                    primary_headers = v_headers
                                                    primary_segments = segs
                                                break
                                except Exception as ex_sw:
                                    logger.debug(f"Streamwish fetch error: {ex_sw}")

                        # 3. Sibnet
                        elif "sibnet" in embed_src:
                            mp4_url = resolve_sibnet_embed(embed_src, session=sess, headers=headers)
                            if mp4_url:
                                v_headers = {"User-Agent": headers["User-Agent"], "Referer": "https://video.sibnet.ru/"}
                                audio_tracks.append({
                                    "name": dil_label,
                                    "lang": "tur" if dil == 0 else "eng",
                                    "video_url": mp4_url,
                                    "sample_segment_url": mp4_url,
                                    "count": 1,
                                    "direct_file": True,
                                    "headers": v_headers,
                                    "is_standalone_stream": True
                                })
                                if not primary_video_url:
                                    primary_video_url = mp4_url
                                    primary_headers = v_headers
                                break
            except Exception as ex_d:
                logger.debug(f"SezonlukDizi dil error: {ex_d}")

        if primary_video_url:
            # Deduplicate subtitles by url
            seen_sub_urls = set()
            dedup_subs = []
            for s in subtitles:
                u_s = s.get("url") if isinstance(s, dict) else s
                if u_s and u_s not in seen_sub_urls:
                    seen_sub_urls.add(u_s)
                    dedup_subs.append(s)

            is_direct = False if (primary_segments or ".m3u8" in primary_video_url) else True
            return ExtractorResult(
                success=True,
                title=film_title,
                video_url=primary_video_url,
                video_headers=primary_headers,
                audio_tracks=audio_tracks,
                subtitles=dedup_subs,
                total_segments=len(primary_segments) if primary_segments else 1,
                direct_file=is_direct,
                video_segments=primary_segments if primary_segments else None,
                raw_url=url
            )

        return None


__all__ = ["SezonlukdiziExtractor"]
