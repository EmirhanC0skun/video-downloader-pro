# -*- coding: utf-8 -*-
"""
Video Downloader Pro — FilmModu & Pilavyer Platform Extractor.
Resolves data-pv mounts, pilavyerplay streams, multi-audio tracks and subtitles.
"""

import re
import json
from urllib.parse import urljoin, quote
import requests

try:
    from curl_cffi import requests as c_requests
except Exception:
    c_requests = None

from extractors.base import BaseExtractor, ExtractorResult, DEFAULT_HEADERS
from extractors.variants import extract_master_quality_variants, extract_media_playlist_timeline
from logger import get_logger

logger = get_logger("extractors.platforms.filmmodu")

COPYRIGHT_KEYWORDS = [
    "telif nedeniyle bu içerik kaldırılmıştır",
    "telif nedeniyle bu icerik kaldirilmistir",
    "telif hakkı nedeniyle kaldırılmıştır",
    "telif hakları nedeniyle kaldırılmıştır",
    "bu içerik siteden kaldırılmıştır"
]


class FilmmoduExtractor(BaseExtractor):
    """Strategy extractor for FilmModu and Pilavyer stream mounts."""

    @property
    def name(self) -> str:
        return "FilmModu & Pilavyer"

    def can_handle(self, url: str) -> bool:
        low = url.lower()
        return "filmmodu" in low or "pilavyer" in low

    def extract(self, url: str, session=None, log_callback=None) -> ExtractorResult:
        self.log(f"[*] FilmModu taranıyor: {url}", log_callback)
        sess = session or requests.Session()
        headers = dict(DEFAULT_HEADERS)
        headers["Referer"] = url

        try:
            r_page = sess.get(url, headers=headers, timeout=12)
            page_html = r_page.text if r_page.status_code == 200 else ""
        except Exception as e:
            logger.debug(f"FilmModu page fetch error: {e}")
            return None

        if not page_html:
            return None

        # Telif Hakkı Kontrolü (Test_C8 güvencesi)
        if any(kw in page_html.lower() for kw in COPYRIGHT_KEYWORDS):
            raise RuntimeError("Bu içerik telif hakkı nedeniyle yayıncı site tarafından yayından kaldırılmıştır.")

        title_m = re.search(r'<title>([^<]+)</title>', page_html)
        film_title = title_m.group(1).split("izle")[0].strip() if title_m else "FilmModu Video"

        try:
            pv_match = re.search(r'data-pv=["\']([^"\']+)["\']', page_html) or re.search(r'PV\.mount\s*\(\s*["\']([^"\']+)["\']', page_html)
            script_match = re.search(r'<script[^>]+src=["\']([^"\']*(?:assets/js/core\.js|/e/c\.js)[^"\']*)["\']', page_html)

            if pv_match:
                slug = pv_match.group(1)
                base_pilavyer = "https://play2.pilavyerplay.top"
                if script_match:
                    src_val = script_match.group(1)
                    derived = re.sub(r'/(?:e/c|assets/js/core)\.js.*$', '', src_val)
                    if derived.startswith("http"):
                        base_pilavyer = derived
                    elif derived.startswith("//"):
                        base_pilavyer = "https:" + derived

                iframe_s_url = f"{base_pilavyer}/assets/js/s.php?s={quote(slug)}"
                s_hdrs = {'User-Agent': headers['User-Agent'], 'Referer': url}

                if c_requests:
                    r_s = c_requests.get(iframe_s_url, headers=s_hdrs, impersonate="chrome124", timeout=12)
                else:
                    r_s = sess.get(iframe_s_url, headers=s_hdrs, timeout=12)

                if r_s.status_code == 200:
                    player_json_m = re.search(r'window\.__PLAYER__\s*=\s*(\{.*?\});', r_s.text, re.DOTALL)
                    if player_json_m:
                        p_data = json.loads(player_json_m.group(1))
                        master_stream = p_data.get("stream")
                        p_title = p_data.get("title") or film_title

                        if master_stream:
                            stream_hdrs = {
                                'User-Agent': headers['User-Agent'],
                                'Referer': iframe_s_url,
                                'Origin': base_pilavyer
                            }
                            r_mst = sess.get(master_stream, headers=stream_hdrs, timeout=12)
                            if r_mst.status_code == 200:
                                audio_tracks = []
                                subtitles = []
                                primary_video_url = ""
                                primary_headers = {}
                                primary_segments = []
                                primary_durations = []

                                for sub_item in p_data.get("subs", []):
                                    s_src = sub_item.get("src")
                                    if s_src:
                                        s_lbl = sub_item.get("label") or "Türkçe Altyazı"
                                        s_lang = sub_item.get("lang") or ("tur" if any(k in s_lbl.lower() for k in ["türk", "tr"]) else "eng")
                                        subtitles.append({
                                            "name": s_lbl,
                                            "lang": s_lang,
                                            "url": s_src,
                                            "headers": stream_hdrs
                                        })

                                p_audios = [a for a in p_data.get("audios", []) if isinstance(a, dict)]
                                audio_lines = [l.strip() for l in r_mst.text.splitlines() if l.strip().startswith("#EXT-X-MEDIA:TYPE=AUDIO")]
                                for a_idx, a_line in enumerate(audio_lines):
                                    n_m = re.search(r'NAME=["\']([^"\']+)["\']', a_line)
                                    l_m = re.search(r'LANGUAGE=["\']([^"\']+)["\']', a_line)
                                    u_m = re.search(r'URI=["\']([^"\']+)["\']', a_line)
                                    if not u_m:
                                        continue
                                    a_name = n_m.group(1) if n_m else f"audio_{a_idx+1}"
                                    a_lang_hdr = l_m.group(1) if l_m else ""
                                    a_uri = u_m.group(1)
                                    aud_sub_url = urljoin(master_stream, a_uri)
                                    try:
                                        r_aud = sess.get(aud_sub_url, headers=stream_hdrs, timeout=12)
                                        if r_aud.status_code == 200:
                                            all_aud_segs, aud_durations = extract_media_playlist_timeline(
                                                aud_sub_url,
                                                r_aud.text,
                                            )
                                            if all_aud_segs:
                                                aud_aes_key = None
                                                aud_aes_iv = None
                                                if 'METHOD=AES-128' in r_aud.text:
                                                    try:
                                                        k_uri = r_aud.text.split('URI="')[1].split('"')[0]
                                                        k_full = urljoin(aud_sub_url, k_uri)
                                                        if 'IV=0x' in r_aud.text:
                                                            iv_h = r_aud.text.split('IV=0x')[1].split('\n')[0].split(',')[0].strip()
                                                            aud_aes_iv = bytes.fromhex(iv_h)
                                                        r_k = sess.get(k_full, headers=stream_hdrs, timeout=10)
                                                        if r_k.status_code == 200:
                                                            aud_aes_key = r_k.content
                                                    except Exception as ex_k:
                                                        logger.debug(f"FilmModu key fetch error: {ex_k}")
                                                aud_hdrs = dict(stream_hdrs)
                                                if aud_aes_key and aud_aes_iv:
                                                    aud_hdrs["aes_key"] = aud_aes_key
                                                    aud_hdrs["aes_iv"] = aud_aes_iv

                                                fixed_aud_segs = [aseg.replace("https://pilavyer2.top", base_pilavyer).replace("http://pilavyer2.top", base_pilavyer) for aseg in all_aud_segs]

                                                matched_meta = {}
                                                for pa in p_audios:
                                                    pa_name = pa.get("name", "")
                                                    if pa_name and (f"stream_{pa_name}" in a_uri or pa_name == a_name):
                                                        matched_meta = pa
                                                        break
                                                if not matched_meta and a_idx < len(p_audios):
                                                    matched_meta = p_audios[a_idx]

                                                p_lbl = matched_meta.get("label") or ""
                                                p_lang = matched_meta.get("lang") or a_lang_hdr or ""
                                                is_tr = any(k in f"{a_name} {p_lbl} {p_lang} {a_lang_hdr}".lower() for k in ["turk", "türk", "tr", "dublaj"])
                                                if is_tr:
                                                    track_name = "🇹🇷 Türkçe Dublaj"
                                                    track_lang = "tur"
                                                else:
                                                    track_name = "🇬🇧 Orijinal / İngilizce"
                                                    track_lang = "eng"

                                                audio_tracks.append({
                                                    "name": track_name,
                                                    "lang": track_lang,
                                                    "sample_segment_url": fixed_aud_segs[0],
                                                    "count": len(fixed_aud_segs),
                                                    "headers": aud_hdrs,
                                                    "segments": fixed_aud_segs,
                                                    "durations": aud_durations,
                                                })
                                    except Exception as aud_err:
                                        logger.debug(f"FilmModu audio track error: {aud_err}")

                                qual_variants = extract_master_quality_variants(master_stream, r_mst.text)
                                v_sub_urls = [qv["url"] for qv in qual_variants] if qual_variants else [urljoin(master_stream, l.strip()) for l in r_mst.text.splitlines() if l.strip() and not l.startswith("#")]

                                for sub_m3u8_url in v_sub_urls:
                                    r_sub = sess.get(sub_m3u8_url, headers=stream_hdrs, timeout=12)
                                    if r_sub.status_code == 200:
                                        aes_key_bytes = None
                                        aes_iv_bytes = None
                                        if 'METHOD=AES-128' in r_sub.text:
                                            try:
                                                k_uri = r_sub.text.split('URI="')[1].split('"')[0]
                                                k_full = urljoin(sub_m3u8_url, k_uri)
                                                if 'IV=0x' in r_sub.text:
                                                    iv_h = r_sub.text.split('IV=0x')[1].split('\n')[0].split(',')[0].strip()
                                                    aes_iv_bytes = bytes.fromhex(iv_h)
                                                r_k = sess.get(k_full, headers=stream_hdrs, timeout=10)
                                                if r_k.status_code == 200:
                                                    aes_key_bytes = r_k.content
                                            except Exception as ex_k2:
                                                logger.debug(f"FilmModu video key error: {ex_k2}")

                                        raw_segs, raw_durations = extract_media_playlist_timeline(
                                            sub_m3u8_url,
                                            r_sub.text,
                                        )
                                        if raw_segs:
                                            fixed_segs = [s.replace("https://pilavyer2.top", base_pilavyer).replace("http://pilavyer2.top", base_pilavyer) for s in raw_segs]
                                            final_hdrs = dict(stream_hdrs)
                                            if aes_key_bytes and aes_iv_bytes:
                                                final_hdrs["aes_key"] = aes_key_bytes
                                                final_hdrs["aes_iv"] = aes_iv_bytes

                                            primary_video_url = fixed_segs[0]
                                            primary_headers = final_hdrs
                                            primary_segments = fixed_segs
                                            primary_durations = raw_durations
                                            break

                                if primary_video_url:
                                    return ExtractorResult(
                                        success=True,
                                        title=p_title,
                                        video_url=primary_video_url,
                                        video_headers=primary_headers,
                                        video_segments=primary_segments,
                                        video_durations=primary_durations,
                                        audio_tracks=audio_tracks,
                                        subtitles=subtitles,
                                        total_segments=len(primary_segments),
                                        direct_file=False,
                                        raw_url=url
                                    )
        except Exception as e:
            logger.debug(f"FilmModu extractor error: {e}")

        return None


__all__ = ["FilmmoduExtractor"]
