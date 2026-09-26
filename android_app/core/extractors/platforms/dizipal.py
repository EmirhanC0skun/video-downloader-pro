# -*- coding: utf-8 -*-
"""
Video Downloader Pro — Dizipal Platform Extractor.
Resolves encrypted media on Dizipal mirrors using PBKDF2/AES and DPlayer resolution.
"""

import os
import re
import json
import html
import base64
import hashlib
from urllib.parse import urljoin, urlsplit
import requests

try:
    from curl_cffi import requests as c_requests
except Exception:
    c_requests = None

try:
    from Crypto.Cipher import AES
except ImportError:
    try:
        from Cryptodome.Cipher import AES
    except ImportError:
        AES = None

from extractors.base import BaseExtractor, ExtractorResult
from extractors.embeds.dplayer import resolve_dplayer_embed
from extractors.subtitles import extract_subtitles_from_m3u8
from extractors.variants import extract_master_quality_variants, extract_media_playlist_timeline
from logger import get_logger

logger = get_logger("extractors.platforms.dizipal")


def _decrypt_modern_player_config(payload):
    """Decrypt the current Dizipal ajax-player-config response."""
    config = payload.get("config") or {}
    if config.get("v"):
        return str(config["v"])
    enc = payload.get("enc") or {}
    if not AES or not all(enc.get(key) for key in ("c", "iv", "k1", "k2")):
        return ""
    try:
        key_left = base64.b64decode(enc["k1"])
        key_right = base64.b64decode(enc["k2"])
        if len(key_left) != len(key_right) or len(key_left) not in (16, 24, 32):
            return ""
        key = bytes(left ^ right for left, right in zip(key_left, key_right))
        iv = base64.b64decode(enc["iv"])
        ciphertext = base64.b64decode(enc["c"])
        decrypted = AES.new(key, AES.MODE_CBC, iv).decrypt(ciphertext)
        pad_len = decrypted[-1]
        if not 1 <= pad_len <= AES.block_size or decrypted[-pad_len:] != bytes([pad_len]) * pad_len:
            return ""
        return decrypted[:-pad_len].decode("utf-8").strip()
    except (ValueError, TypeError, UnicodeDecodeError):
        logger.debug("Dizipal modern player config decrypt failed", exc_info=True)
        return ""


def _extract_jw_embed(embed_url, session, parent_url, user_agent):
    """Extract JWPlayer HLS and subtitle metadata from the current embed host."""
    embed_headers = {"User-Agent": user_agent, "Referer": parent_url}
    response = session.get(embed_url, headers=embed_headers, timeout=(10, 25))
    if response.status_code != 200:
        return None
    embed_html = response.text
    source_match = re.search(
        r'sources\s*:\s*\[\s*\{[^{}]*?file\s*:\s*["\']([^"\']+)["\']',
        embed_html,
        re.IGNORECASE | re.DOTALL,
    )
    if not source_match:
        source_match = re.search(r'["\'](https?://[^"\']+\.m3u8[^"\']*)["\']', embed_html)
    if not source_match:
        return None

    subtitles = []
    subtitle_headers = {"User-Agent": user_agent, "Referer": embed_url}
    for raw_track in re.findall(r'\{[^{}]*(?:captions|subtitles)[^{}]*\}', embed_html, re.IGNORECASE):
        file_match = re.search(r'file\s*:\s*["\']([^"\']+)["\']', raw_track, re.IGNORECASE)
        if not file_match:
            continue
        label_match = re.search(r'label\s*:\s*["\']([^"\']+)["\']', raw_track, re.IGNORECASE)
        label = label_match.group(1).strip() if label_match else "Altyazı"
        normalized = label.lower()
        is_turkish = any(token in normalized for token in ("turkish", "türk", "turk", "tr"))
        subtitles.append({
            "url": urljoin(embed_url, file_match.group(1)),
            "name": label,
            "label": label,
            "lang": "tur" if is_turkish else "eng",
            "kind": "subtitles",
            "headers": subtitle_headers,
        })

    return {
        "streams": [{"title": "Dizipal", "url": urljoin(embed_url, source_match.group(1))}],
        "subtitles": subtitles,
        "embed_url": embed_url,
    }


def _resolve_modern_player_config(film_url, html_text, session, req_headers):
    cfg_match = re.search(
        r'id=["\']videoContainer["\'][^>]*\bdata-cfg=["\']([^"\']+)["\']',
        html_text,
        re.IGNORECASE,
    ) or re.search(r'\bdata-cfg=["\']([^"\']+)["\']', html_text, re.IGNORECASE)
    if not cfg_match:
        return None

    parsed = urlsplit(film_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    config_url = urljoin(origin + "/", "ajax-player-config")
    post_headers = dict(req_headers)
    post_headers.update({
        "Referer": film_url,
        "Origin": origin,
        "Content-Type": "application/x-www-form-urlencoded",
    })
    response = session.post(
        config_url,
        headers=post_headers,
        data={"cfg": cfg_match.group(1)},
        timeout=(10, 25),
    )
    if response.status_code != 200:
        return None
    payload = response.json()
    if not payload.get("success"):
        return None
    player_value = _decrypt_modern_player_config(payload)
    if not player_value:
        return None

    player_type = str((payload.get("config") or {}).get("t") or "embed").lower()
    if player_type in ("m3u8", "hls") or ".m3u8" in player_value.lower():
        return {"streams": [{"title": "Dizipal", "url": player_value}], "subtitles": []}
    if "<iframe" in player_value.lower():
        iframe_match = re.search(r'\bsrc=["\']([^"\']+)["\']', player_value, re.IGNORECASE)
        if not iframe_match:
            return None
        player_value = urljoin(film_url, iframe_match.group(1))
    return _extract_jw_embed(
        player_value,
        session=session,
        parent_url=film_url,
        user_agent=req_headers["User-Agent"],
    )


def _classify_standalone_stream(title):
    """Classify a DPlayer source without confusing subtitle language with audio."""
    normalized = (title or "").strip().lower()
    if any(key in normalized for key in ("altyaz", "subtitle", "sub", "orij", "original", "eng")):
        return "\U0001f1ec\U0001f1e7 Orijinal / T\u00fcrk\u00e7e Altyaz\u0131l\u0131", "eng"
    if any(key in normalized for key in ("dublaj", "dubbed", "dub")):
        return "\U0001f1f9\U0001f1f7 T\u00fcrk\u00e7e Dublaj", "tur"
    return (title or "Kaynak"), "und"


def resolve_dizipal_page(film_url, session=None, headers=None, log_callback=None):
    """
    Dizipal (dizipal*.com/movies/... veya dizi bölümleri) platform çözücü.
    data-rm-k ile şifrelenmiş gömülü oynatıcıyı PBKDF2+AES ile çözer ve DPlayer üzerinden akışları getirir.
    """
    def log(msg):
        if log_callback:
            try:
                log_callback(msg)
            except Exception as _e_cb:
                logger.debug(f"log_callback exception: {_e_cb}")

    session = session or requests.Session()
    req_headers = dict(headers or {})
    req_headers.setdefault("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    req_headers.setdefault("Referer", film_url)
    req_headers.setdefault("Connection", "keep-alive")

    try:
        r = None
        try:
            r = session.get(film_url, headers=req_headers, timeout=(10, 25))
        except Exception:
            logger.debug("Dizipal primary page request failed", exc_info=True)
        if (r is None or r.status_code != 200) and c_requests:
            try:
                r = c_requests.get(film_url, headers=req_headers, impersonate="chrome124", timeout=(10, 25))
            except Exception:
                logger.debug("Dizipal Chrome fallback request failed", exc_info=True)
        elif r is None:
            session = requests.Session()
            r = session.get(film_url, headers=req_headers, timeout=(10, 25))

        if not r or r.status_code != 200:
            return None

        html_text = r.text
        title_m = re.search(r'<meta\s+property=[\'"]og:title[\'"]\s+content=[\'"]([^\'"]+)[\'"]', html_text) or re.search(r'<title>([^<]+)</title>', html_text)
        page_title = title_m.group(1) if title_m else "Dizipal Video"
        page_title = page_title.split(" - Dizipal")[0].split(" izle")[0].strip()

        rm_inner = [m.strip() for m in re.findall(r'<div[^>]*data-rm-k[^>]*>(.*?)</div>', html_text, re.DOTALL) if m.strip()]
        rm_attrs = [m[1] for m in re.findall(r'data-rm-k=([\'"])(.*?)\1', html_text, re.DOTALL) if m[1] and m[1].lower() != "true"]
        rm_matches = rm_inner if rm_inner else rm_attrs

        all_streams = []
        all_subtitles = []

        if not rm_matches:
            modern_result = _resolve_modern_player_config(
                film_url,
                html_text,
                session,
                req_headers,
            )
            if modern_result:
                for stream in modern_result.get("streams") or []:
                    stream["embed_url"] = modern_result.get("embed_url") or film_url
                    all_streams.append(stream)
                all_subtitles.extend(modern_result.get("subtitles") or [])

        passphrase = "3hPn4uCjTVtfYWcjIcoJQ4cL1WWk1qxXI39egLYOmNv6IblA7eKJz68uU3eLzux1biZLCms0quEjTYniGv5z1JcKbNIsDQFSeIZOBZJz4is6pD7UyWDggWWzTLBQbHcQFpBQdClnuQaMNUHtLHTpzCvZy33p6I7wFBvL4fnXBYH84aUIyWGTRvM2G5cfoNf4705tO2kv"

        for raw_rm in rm_matches:
            try:
                raw_json_str = html.unescape(raw_rm.strip())
                data = json.loads(raw_json_str)

                salt = bytes.fromhex(data["salt"])
                iv = bytes.fromhex(data["iv"])
                raw_cipher = str(data["ciphertext"]).strip()
                ciphertext = base64.b64decode(raw_cipher + "=" * (-len(raw_cipher) % 4))

                key = hashlib.pbkdf2_hmac("sha512", passphrase.encode("utf-8"), salt, 999, dklen=32)
                if not AES:
                    continue

                cipher = AES.new(key, AES.MODE_CBC, iv)
                decrypted_padded = cipher.decrypt(ciphertext)
                pad_len = decrypted_padded[-1]
                embed_path = decrypted_padded[:-pad_len].decode("utf-8").strip()

                if embed_path.startswith("//"):
                    embed_url = "https:" + embed_path
                elif embed_path.startswith("/"):
                    embed_url = urljoin(film_url, embed_path)
                else:
                    embed_url = embed_path

                log(f"[+] Dizipal Gömülü Oynatıcı Çözüldü: {embed_url}")

                dp_res = resolve_dplayer_embed(embed_url, session=session, headers={"User-Agent": req_headers["User-Agent"], "Referer": film_url})
                if dp_res and dp_res.get("streams"):
                    for st in dp_res["streams"]:
                        if not any(x.get("url") == st.get("url") for x in all_streams):
                            st["embed_url"] = embed_url
                            all_streams.append(st)
                    for sub in dp_res.get("subtitles", []):
                        if not any(x.get("url") == sub.get("url") for x in all_subtitles):
                            all_subtitles.append(sub)
            except Exception as e_rm:
                logger.debug(f"Dizipal rm_k decrypt error: {e_rm}")

        if not all_streams:
            return None

        log(f"[+] Dizipal HLS Akışı Çözüldü ({len(all_streams)} alternatif kaynak mevcut)...")

        audio_tracks = []
        primary_video_url = ""
        primary_headers = {}
        primary_segments = []
        primary_durations = []
        primary_variants = []

        def fetch_stream(stream_url, stream_headers, timeout):
            if c_requests:
                try:
                    return c_requests.get(
                        stream_url,
                        headers=stream_headers,
                        impersonate="chrome124",
                        timeout=timeout,
                    )
                except Exception:
                    logger.debug(
                        "Dizipal impersonated stream request failed; requests fallback is used",
                        exc_info=True,
                    )
            return session.get(stream_url, headers=stream_headers, timeout=timeout)

        # Sayfa içi <track> altyazılarını da ekle
        from extractors.subtitles import extract_subtitles_from_tracks
        page_subs = extract_subtitles_from_tracks(html_text, film_url, headers=req_headers)
        if page_subs:
            all_subtitles.extend(page_subs)

        for s_idx, st_info in enumerate(all_streams):
            st_title = st_info.get("title", f"Kaynak #{s_idx+1}").strip()
            st_url = st_info.get("url", "")
            emb_url = st_info.get("embed_url", film_url)
            if not st_url:
                continue

            stream_hdrs = {"User-Agent": req_headers["User-Agent"], "Referer": emb_url, "Connection": "keep-alive"}

            try:
                r_master = fetch_stream(st_url, stream_hdrs, (10, 25))

                if r_master.status_code != 200 or "#EXTM3U" not in r_master.text:
                    continue

                m_text = r_master.text
                m_subs = extract_subtitles_from_m3u8(m_text, st_url, headers=stream_hdrs)
                if m_subs:
                    all_subtitles.extend(m_subs)

                px_audio = []
                for line in m_text.splitlines():
                    if line.startswith("#EXT-X-MEDIA:TYPE=AUDIO"):
                        name_m = re.search(r'NAME=["\']([^"\']+)["\']', line)
                        uri_m = re.search(r'URI=["\']([^"\']+)["\']', line)
                        lang_m = re.search(r'LANGUAGE=["\']([^"\']+)["\']', line)
                        if name_m and uri_m:
                            a_u = urljoin(st_url, uri_m.group(1))
                            a_raw_name = name_m.group(1).strip()
                            a_is_tr = any(k in a_raw_name.lower() for k in ["türk", "tr", "dub"])
                            a_lang = lang_m.group(1).lower() if lang_m else ("tur" if a_is_tr else "eng")
                            a_segs = []
                            a_durations = []
                            try:
                                r_a = fetch_stream(a_u, stream_hdrs, (10, 20))
                                if r_a.status_code == 200:
                                    a_segs, a_durations = extract_media_playlist_timeline(a_u, r_a.text)
                            except Exception as ex_a:
                                logger.debug(f"Dizipal audio fetch error: {ex_a}")

                            disp_a_name = f"🎵 {a_raw_name}" if any(k in a_raw_name.lower() for k in ["dub", "orij"]) else (f"🎵 🇹🇷 {a_raw_name} (Dublaj)" if a_is_tr else f"🎵 🇬🇧 {a_raw_name} (Orijinal)")
                            px_audio.append({
                                "name": disp_a_name,
                                "lang": a_lang,
                                "url": a_u,
                                "sample_segment_url": a_segs[0] if a_segs else "",
                                "segments": a_segs,
                                "durations": a_durations,
                                "count": len(a_segs),
                                "headers": stream_hdrs
                            })

                variants = extract_master_quality_variants(st_url, m_text)
                best_m3u8 = variants[0]["url"] if variants else st_url

                r_sub = fetch_stream(best_m3u8, stream_hdrs, (10, 25))

                segs = []
                video_durations = []
                if r_sub.status_code == 200:
                    segs, video_durations = extract_media_playlist_timeline(
                        best_m3u8,
                        r_sub.text,
                    )

                if segs:
                    disp_title, track_lang = _classify_standalone_stream(st_title)

                    log(f"  [+] Dizipal {disp_title}: {len(segs)} segment çözüldü")

                    if px_audio:
                        for pa in px_audio:
                            pa["video_segments"] = segs
                            pa["video_durations"] = video_durations
                            pa["video_url"] = best_m3u8
                            pa["video_headers"] = stream_hdrs
                        audio_tracks.extend(px_audio)
                    else:
                        audio_tracks.append({
                            "name": f"🎬 {disp_title}",
                            "lang": track_lang,
                            "sample_segment_url": segs[0],
                            "count": len(segs),
                            "headers": stream_hdrs,
                            "segments": segs,
                            "durations": video_durations,
                            "video_durations": video_durations,
                            "video_segments": segs,
                            "video_url": best_m3u8,
                            "video_headers": stream_hdrs,
                            "is_standalone_stream": True
                        })

                    if not primary_video_url:
                        primary_video_url = best_m3u8
                        primary_headers = stream_hdrs
                        primary_segments = segs
                        primary_durations = video_durations
                        primary_variants = variants
            except Exception as st_err:
                logger.debug(f"Dizipal stream iteration error: {st_err}")

        # Altyazı tekilleştirme
        seen_s_urls = set()
        dedup_subs = []
        for s in all_subtitles:
            u_s = s.get("url") if isinstance(s, dict) else s
            if u_s and u_s not in seen_s_urls:
                seen_s_urls.add(u_s)
                dedup_subs.append(s)

        if primary_segments:
            log(f"[+] Dizipal Film/Dizi Başarıyla Çözümlendi! ({len(primary_segments)} segment, {len(audio_tracks)} ses seçeneği)")
            return {
                "success": True,
                "title": page_title,
                "video_url": primary_video_url,
                "video_headers": primary_headers,
                "video_segments": primary_segments,
                "video_durations": primary_durations,
                "audio_tracks": audio_tracks or [{
                    "name": "🎬 Standart / Orijinal Akış",
                    "lang": "und",
                    "sample_segment_url": primary_segments[0],
                    "segments": primary_segments,
                    "count": len(primary_segments),
                    "headers": primary_headers
                }],
                "subtitles": dedup_subs,
                "total_segments": len(primary_segments),
                "direct_file": False,
                "quality_variants": primary_variants
            }
    except Exception as e:
        log(f"[!] Dizipal çözme hatası: {e}")
    return None


class DizipalExtractor(BaseExtractor):
    """Strategy extractor for Dizipal platform pages."""

    @property
    def name(self) -> str:
        return "Dizipal Platform"

    def can_handle(self, url: str) -> bool:
        low = url.lower()
        return "dizipal" in low

    def extract(self, url: str, session=None, log_callback=None) -> ExtractorResult:
        data = resolve_dizipal_page(url, session=session, log_callback=log_callback)
        if not data or not data.get("video_url"):
            return None

        return ExtractorResult(
            success=True,
            title=data.get("title", "Dizipal Video"),
            video_url=data["video_url"],
            video_headers=data.get("video_headers", {}),
            audio_tracks=data.get("audio_tracks", []),
            subtitles=data.get("subtitles", []),
            total_segments=data.get("total_segments", 0),
            direct_file=False,
            video_segments=data.get("video_segments"),
            video_durations=data.get("video_durations"),
            raw_url=url
        )


__all__ = ["DizipalExtractor", "resolve_dizipal_page"]
