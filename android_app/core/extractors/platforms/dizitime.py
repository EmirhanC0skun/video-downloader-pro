# -*- coding: utf-8 -*-
"""
Video Downloader Pro — DiziTime Platform Extractor.
Resolves dizitime.news and dizitime mirrors by querying /getvideo/{id}_t API endpoints.
"""

import re
import json
import base64
from urllib.parse import urljoin, urlparse
import requests

try:
    from curl_cffi import requests as c_requests
except Exception:
    c_requests = None

from extractors.base import BaseExtractor, ExtractorResult
from extractors.generic_hls import decrypt_cryptojs_aes
from logger import get_logger

logger = get_logger("extractors.platforms.dizitime")


def _resolve_dtime_embed(embed_url, session, headers, curl_session=None):
    """Resolve DiziTime's AES-wrapped MolySTREAM player to its HLS manifest."""
    response = None
    if curl_session:
        try:
            response = curl_session.get(embed_url, headers=headers, timeout=10)
        except Exception as exc:
            logger.debug(f"DiziTime DTime curl request error: {exc}")
    if response is None or response.status_code != 200:
        try:
            response = session.get(embed_url, headers=headers, timeout=10)
        except Exception as exc:
            logger.debug(f"DiziTime DTime request error: {exc}")
            return None
    if response.status_code != 200 or not response.text:
        return None

    text = response.text
    aes_match = re.search(
        r'CryptoJS\.AES\.decrypt\(["\'](.*?)["\']\s*,\s*["\'](.*?)["\']\)',
        text,
        re.DOTALL,
    )
    if aes_match:
        decrypted = decrypt_cryptojs_aes(aes_match.group(1), aes_match.group(2))
        if decrypted:
            text += "\n" + decrypted

    manifest_match = re.search(
        r'file\s*:\s*["\'](https?://[^"\']+)["\']',
        text,
        re.I,
    )
    if not manifest_match:
        manifest_match = re.search(
            r'["\'](https?://[^"\']+\.m3u8(?:\?[^"\']*)?)["\']',
            text,
            re.I,
        )
    if not manifest_match:
        return None

    stream_headers = dict(headers)
    stream_headers["Referer"] = embed_url
    return {
        "success": True,
        "title": "DTime stream",
        "video_url": manifest_match.group(1),
        "video_headers": stream_headers,
        "video_segments": [],
        "audio_tracks": [],
        "subtitles": [],
        "total_segments": 0,
        "direct_file": False,
    }


def resolve_dizitime_page(
    film_url,
    session=None,
    headers=None,
    log_callback=None,
    _include_watch_variants=True,
):
    """
    DiziTime (dizitime.news, dizitime.org vb.) platform çözücü.
    Sayfadaki kaynakları (DTime, Moly, Vidmoly, Odnok vb.) dinamik tarar,
    /getvideo/{id}_t API uç noktası üzerinden çalışan embed oynatıcıyı (Vidmoly vb.)
    otomatik tespit edip çözümler.
    """
    def log(msg):
        if log_callback:
            try:
                log_callback(msg)
            except Exception as _e_cb:
                logger.debug(f"log_callback error: {_e_cb}")

    log(f"[*] 🎬 DiziTime sayfası taranıyor: {film_url}")
    parsed = urlparse(film_url)
    netloc = parsed.netloc or "dizitime.news"
    base_origin = f"{parsed.scheme or 'https'}://{netloc}"

    req_headers = dict(headers or {})
    req_headers.setdefault("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    req_headers["Referer"] = base_origin + "/"

    c_sess = None
    active_c_requests = c_requests
    try:
        import extractor
        if hasattr(extractor, "c_requests") and extractor.c_requests is not None:
            active_c_requests = extractor.c_requests
    except Exception:
        logger.debug("Dizitime curl facade lookup failed", exc_info=True)

    if active_c_requests:
        try:
            c_sess = active_c_requests.Session(impersonate="chrome124")
        except Exception as _e_c:
            logger.debug(f"c_requests session error: {_e_c}")

    sess = session or requests.Session()
    html = ""
    try:
        r = None
        if c_sess:
            try:
                r = c_sess.get(film_url, headers=req_headers, timeout=12)
            except Exception as e_c_page:
                logger.debug(f"DiziTime curl_cffi page request error: {e_c_page}")
                c_sess = None
        if r is None or r.status_code != 200:
            r = sess.get(film_url, headers=req_headers, timeout=12)
        if r.status_code == 200:
            html = r.text
    except Exception as e_req:
        log(f"[!] DiziTime sayfası yüklenemedi: {e_req}")
        return None

    if not html:
        return None

    m_title = re.search(r'<title>(.*?)</title>', html, re.I | re.S)
    page_title = m_title.group(1).split("-")[0].strip() if m_title else "DiziTime Video"

    page_language = "tur" if "turkce-dublaj" in parsed.path.lower() else "eng"
    watch_type_urls = {}
    for anchor_html in re.findall(r'<a\b.*?</a\s*>', html, re.I | re.S):
        if "btn-watchtype" not in anchor_html.lower():
            continue
        href_match = re.search(r'\bhref=["\']([^"\']+)["\']', anchor_html, re.I)
        if not href_match:
            continue
        label = re.sub(r'<[^>]+>', ' ', anchor_html)
        label = re.sub(r'\s+', ' ', label).strip().lower()
        target_url = urljoin(film_url, href_match.group(1))
        if "dublaj" in label:
            watch_type_urls["tur"] = target_url
        elif "altyaz" in label:
            watch_type_urls["eng"] = target_url

    raw_vids = []
    for option_html in re.findall(r'<option\b.*?</option\s*>', html, re.I | re.S):
        vid_match = re.search(r'\bvalue=["\'](\d+)["\']', option_html, re.I)
        name_match = re.search(r'\bdata-name=["\']([^"\']+)["\']', option_html, re.I)
        if not vid_match or not name_match:
            continue
        raw_vids.append((vid_match.group(1), name_match.group(1), page_language))
    if not raw_vids:
        raw_vids = [
            (vid, "Kaynak", page_language)
            for vid in re.findall(r'value=["\'](\d{5,})["\']', html)
        ]
        iframe_vid = re.search(r'//' + re.escape(netloc) + r'/vid/(\d+)', html)
        if iframe_vid and not any(vid == iframe_vid.group(1) for vid, _, _ in raw_vids):
            raw_vids.insert(0, (iframe_vid.group(1), "Varsayılan", page_language))

    if not raw_vids:
        log("[!] DiziTime sayfasında kaynak ID'si bulunamadı.")
        return None

    log(f"[+] DiziTime: {len(raw_vids)} alternatif video kaynağı tespit edildi.")
    def source_priority(source):
        _vid, source_name, source_lang = source
        language_rank = {"tur": 0, "eng": 1}.get(source_lang, 2)
        provider_name = source_name.lower()
        provider_rank = 0 if "dtime" in provider_name else 1 if "moly" in provider_name else 2
        return language_rank, provider_rank

    sorted_vids = sorted(raw_vids, key=source_priority)

    # Lazy-load resolve_film_page from extractor to support monkey-patching in tests
    try:
        import extractor
        resolve_fn = extractor.resolve_film_page
    except Exception:
        resolve_fn = None

    best_res = None
    standalone_tracks = []
    for vid_id, name, source_lang in sorted_vids:
        log(f"[+] DiziTime kaynağı sorgulanıyor: #{vid_id} ({name})...")
        gv_url = f"{base_origin}/getvideo/{vid_id}_t"
        gv_headers = dict(req_headers)
        gv_headers["Referer"] = film_url

        target_embed = None
        try:
            gv = None
            if c_sess:
                try:
                    gv = c_sess.get(gv_url, headers=gv_headers, allow_redirects=False, timeout=8)
                except Exception as e_c_gv:
                    logger.debug(f"DiziTime curl_cffi getvideo error: {e_c_gv}")
            if gv is None:
                gv = sess.get(gv_url, headers=gv_headers, allow_redirects=False, timeout=8)

            if gv.status_code in (301, 302, 307) and gv.headers.get("Location"):
                target_embed = gv.headers["Location"]
            elif gv.status_code == 200 and gv.text:
                try:
                    dec = base64.b64decode(gv.text.strip()).decode("utf-8", errors="ignore")
                    data = json.loads(dec)
                    if data.get("status") == "success" and data.get("url"):
                        target_embed = data["url"]
                except Exception as ex_dec:
                    logger.debug(f"DiziTime base64 decode error: {ex_dec}")
        except Exception as e_gv:
            logger.debug(f"DiziTime getvideo/{vid_id}_t error: {e_gv}")
            continue

        if not target_embed or "notfound" in target_embed.lower():
            continue

        seen_bridges = set()
        while target_embed and "/getvideo/" in urlparse(target_embed).path.lower():
            if target_embed in seen_bridges:
                target_embed = None
                break
            seen_bridges.add(target_embed)
            try:
                bridge = None
                if c_sess:
                    try:
                        bridge = c_sess.get(
                            target_embed,
                            headers=gv_headers,
                            allow_redirects=False,
                            timeout=8,
                        )
                    except Exception as curl_bridge_error:
                        logger.debug(f"DiziTime curl redirected bridge error: {curl_bridge_error}")
                if bridge is None or bridge.status_code not in (200, 301, 302, 307, 308):
                    bridge = sess.get(
                        target_embed,
                        headers=gv_headers,
                        allow_redirects=False,
                        timeout=8,
                    )
                next_target = None
                if bridge.status_code in (301, 302, 307, 308) and bridge.headers.get("Location"):
                    next_target = urljoin(target_embed, bridge.headers["Location"])
                elif bridge.status_code == 200 and bridge.text:
                    decoded = base64.b64decode(bridge.text.strip()).decode("utf-8", errors="ignore")
                    bridge_data = json.loads(decoded)
                    if bridge_data.get("status") == "success" and bridge_data.get("url"):
                        next_target = bridge_data["url"]
                if not next_target:
                    target_embed = None
                    break
                target_embed = next_target
            except Exception as bridge_error:
                logger.debug(f"DiziTime redirected getvideo bridge error: {bridge_error}")
                break

        if not target_embed or "notfound" in target_embed.lower():
            continue

        log(f"[+] 🎯 DiziTime oynatıcı yönlendirmesi bulundu: {target_embed[:60]}...")
        try:
            resolved = None
            if any(
                host in target_embed.lower()
                for host in ("dtm.molystream.org", "ydt.sheila.stream")
            ):
                embed_headers = dict(req_headers)
                embed_headers["Referer"] = film_url
                resolved = _resolve_dtime_embed(
                    target_embed,
                    sess,
                    embed_headers,
                    curl_session=c_sess,
                )
            if not resolved and resolve_fn:
                resolved = resolve_fn(target_embed, log_callback=log_callback)

            if resolved and resolved.get("success") and (resolved.get("video_url") or resolved.get("video_segments")):
                resolved_title = resolved.get("title") or name or ""
                resolved["title"] = page_title
                segs = len(resolved.get("video_segments") or [])
                if segs > 0:
                    log(f"[+] 🚀 DiziTime: '{page_title}' başarıyla çözümlendi ({segs} parça)!")
                    return resolved
                else:
                    stream_url = resolved.get("video_url", "")
                    stream_parts = urlparse(stream_url)
                    stream_key = (stream_parts.scheme, stream_parts.netloc, stream_parts.path)
                    known_keys = {
                        (
                            urlparse(track["url"]).scheme,
                            urlparse(track["url"]).netloc,
                            urlparse(track["url"]).path,
                        )
                        for track in standalone_tracks
                    }
                    if stream_url and stream_key not in known_keys:
                        stream_title = str(resolved_title).lower()
                        if source_lang in ("tur", "eng"):
                            track_lang = source_lang
                        else:
                            is_original = bool(re.search(
                                r'(?:^|[\s_-])(?:ing|eng|en)(?:$|[\s_-])',
                                stream_title,
                            ))
                            track_lang = "eng" if is_original else "tur"
                        if source_lang in ("tur", "eng") and any(
                            track.get("lang") == track_lang for track in standalone_tracks
                        ):
                            if not best_res:
                                best_res = resolved
                            continue
                        track_name = (
                            "Orijinal / T\u00fcrk\u00e7e Altyaz\u0131l\u0131"
                            if track_lang == "eng"
                            else "T\u00fcrk\u00e7e Dublaj"
                        )
                        stream_headers = resolved.get("video_headers", {})
                        standalone_tracks.append({
                            "name": track_name,
                            "lang": track_lang,
                            "url": stream_url,
                            "sample_segment_url": stream_url,
                            "segments": [],
                            "count": 0,
                            "headers": stream_headers,
                            "video_url": stream_url,
                            "video_headers": stream_headers,
                            "video_segments": [],
                            "is_standalone_stream": True,
                        })
                    if not best_res:
                        best_res = resolved
        except Exception as e_res:
            logger.debug(f"DiziTime embed resolution error: {e_res}")

    counterpart_language = "eng" if page_language == "tur" else "tur"
    counterpart_url = watch_type_urls.get(counterpart_language)
    counterpart = None
    if (
        _include_watch_variants
        and counterpart_url
        and counterpart_url.rstrip("/") != film_url.rstrip("/")
    ):
        counterpart = resolve_dizitime_page(
            counterpart_url,
            session=sess,
            headers=headers,
            log_callback=log_callback,
            _include_watch_variants=False,
        )

    if not best_res and counterpart:
        log(
            f"[+] DiziTime: istenen sekmenin kaynağı kullanılamadı; "
            f"çalışan {counterpart_language} sekmesine geçildi."
        )
        return counterpart

    if best_res:
        if standalone_tracks:
            best_res = dict(best_res)
            primary_track = standalone_tracks[0]
            best_res.update({
                "video_url": primary_track["video_url"],
                "video_headers": primary_track["video_headers"],
                "video_segments": None,
                "audio_tracks": standalone_tracks,
                "total_segments": 0,
                "direct_file": False,
            })

        if counterpart:
            tracks_by_language = {}
            for variant in (best_res, counterpart):
                for track in variant.get("audio_tracks") or []:
                    track_lang = track.get("lang")
                    if track_lang not in ("tur", "eng") or track_lang in tracks_by_language:
                        continue
                    normalized_track = dict(track)
                    normalized_track["name"] = (
                        "Türkçe Dublaj"
                        if track_lang == "tur"
                        else "Orijinal / Türkçe Altyazılı"
                    )
                    tracks_by_language[track_lang] = normalized_track

            combined_tracks = [
                tracks_by_language[lang]
                for lang in ("tur", "eng")
                if lang in tracks_by_language
            ]
            if len(combined_tracks) >= 2:
                best_res = dict(best_res)
                primary_track = combined_tracks[0]
                best_res.update({
                    "video_url": primary_track.get("video_url") or primary_track.get("url", ""),
                    "video_headers": primary_track.get("video_headers") or primary_track.get("headers", {}),
                    "video_segments": primary_track.get("video_segments") or None,
                    "audio_tracks": combined_tracks,
                    "total_segments": primary_track.get("count", 0),
                    "direct_file": False,
                })
        log(f"[+] 🚀 DiziTime: '{page_title}' başarıyla çözümlendi!")
        return best_res

    return None


class DizitimeExtractor(BaseExtractor):
    """Strategy extractor for DiziTime platform pages."""

    @property
    def name(self) -> str:
        return "DiziTime Platform"

    def can_handle(self, url: str) -> bool:
        low = url.lower()
        return "dizitime" in low

    def extract(self, url: str, session=None, log_callback=None) -> ExtractorResult:
        data = resolve_dizitime_page(url, session=session, log_callback=log_callback)
        if not data or not (data.get("video_url") or data.get("video_segments")):
            return None

        return ExtractorResult(
            success=True,
            title=data.get("title", "DiziTime Video"),
            video_url=data.get("video_url", ""),
            video_headers=data.get("video_headers", {}),
            audio_tracks=data.get("audio_tracks", []),
            subtitles=data.get("subtitles", []),
            total_segments=data.get("total_segments") or len(data.get("video_segments") or []),
            direct_file=data.get("direct_file", False),
            raw_url=url,
            video_segments=data.get("video_segments"),
        )


__all__ = ["DizitimeExtractor", "resolve_dizitime_page"]
