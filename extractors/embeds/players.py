# -*- coding: utf-8 -*-
"""
Video Downloader Pro — Common Web Player Embed Extractors.
Handles Pichive, BiPlayer, PopcornVakti, VideoPark, CanliTvNews, and VidSrc.
"""

import re
import json
from urllib.parse import urlparse, urljoin, quote, quote_plus
import requests

try:
    from curl_cffi import requests as c_requests
except Exception:
    c_requests = None

from extractors.base import BaseExtractor, ExtractorResult
from extractors.generic_hls import decrypt_cryptojs_aes
from extractors.subtitles import extract_subtitles_from_tracks
from extractors.variants import extract_media_playlist_timeline, select_best_variant_url
from logger import get_logger

logger = get_logger("extractors.embeds.players")


def resolve_vidsrc_embed(embed_url, session=None, headers=None):
    """Vidsrc (vidsrc.to, vidsrc.me, vidsrc.xyz, 2embed.to) embed akışını çözer."""
    session = session or requests.Session()
    req_headers = dict(headers or {})
    req_headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": embed_url
    })
    try:
        r = session.get(embed_url, headers=req_headers, timeout=10)
        if r.status_code == 200:
            text = r.text
            iframes = re.findall(r'<iframe[^>]+src=["\']([^"\']+)["\']', text)
            for ifr in iframes:
                full_ifr = urljoin(embed_url, ifr)
                if any(x in full_ifr for x in ["rcp", "prorcp", "embed", "vidsrc", "2embed"]):
                    r_sub = session.get(full_ifr, headers={"Referer": embed_url, "User-Agent": req_headers["User-Agent"]}, timeout=10)
                    if r_sub.status_code == 200:
                        m3u8_m = re.findall(r'["\'](https?://[^"\']+\.m3u8[^"\']*)["\']', r_sub.text)
                        if m3u8_m:
                            return m3u8_m[0]
    except Exception as e:
        logger.debug(f"resolve_vidsrc_embed error: {e}")
    return None


def resolve_pichive_embed(embed_url, session=None, headers=None, parent_url=None):
    """Pichive / RoketTV (four.pichive.online / pichive.online) oynatıcı çözücü."""
    session = session or requests.Session()
    req_headers = dict(headers or {})
    ref = parent_url or req_headers.get("Referer") or "https://roketdizi.life/"
    req_headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": ref
    })
    try:
        html = ""
        for try_ref in [ref, "https://roketdizi.life/", "https://dizilla.now/", "https://four.pichive.online/"]:
            req_headers["Referer"] = try_ref
            r = session.get(embed_url, headers=req_headers, timeout=12)
            if "openPlayer" in r.text or "source2.php" in r.text:
                html = r.text
                break

        play_list = ""
        m_call = re.search(r'openPlayer\s*\(([\s\S]*?)\)\s*;', html)
        subtitles = []
        if m_call:
            args_str = m_call.group(1)
            pl_matches = re.findall(r"['\"]([A-Za-z0-9+/=]{40,})['\"]", args_str)
            if pl_matches:
                play_list = pl_matches[0]

            sub_matches = re.findall(r'\[\s*\{\s*[\'"]file[\'"]\s*:[\s\S]*?\}\s*\]', args_str)
            for sm in sub_matches:
                try:
                    s_items = json.loads(sm)
                    for sit in s_items:
                        s_f = sit.get("file")
                        if s_f:
                            s_lbl = sit.get("label") or "Türkçe Altyazı"
                            s_lng = sit.get("lang") or "tur"
                            is_tr = any(k in f"{s_lbl} {s_lng}".lower() for k in ["türk", "turk", "tr"])
                            subtitles.append({
                                "url": s_f,
                                "name": s_lbl,
                                "label": s_lbl,
                                "lang": "tur" if is_tr else "eng",
                                "headers": {"User-Agent": req_headers["User-Agent"], "Referer": embed_url}
                            })
                except Exception as e:
                    logger.debug(f"Pichive subtitles error: {e}")

        if not play_list:
            pl_match = re.search(r'openPlayer\s*\(\s*[\'"]([A-Za-z0-9+/=]{40,})[\'"]', html)
            if pl_match:
                play_list = pl_match.group(1)
            else:
                for q_str in re.findall(r'[\'"]([A-Za-z0-9+/=]{40,})[\'"]', html):
                    if len(q_str) > 40:
                        play_list = q_str
                        break

        if play_list:
            parsed_u = urlparse(embed_url)
            base_pichive = f"{parsed_u.scheme}://{parsed_u.netloc}"
            api_url = f"{base_pichive}/source2.php?v=" + quote_plus(play_list)

            ajax_headers = {
                'User-Agent': req_headers['User-Agent'],
                'Referer': embed_url,
                'Origin': base_pichive,
                'X-Requested-With': 'XMLHttpRequest'
            }
            r_api = session.get(api_url, headers=ajax_headers, timeout=10)
            res_json = r_api.json()
            sources = res_json.get("playlist", [{}])[0].get("sources", [])
            if sources:
                m_url = sources[0].get("file")
                audio_tracks = []
                video_segments = []
                qual_variants = []
                best_video_url = m_url
                m_hdrs = {'User-Agent': req_headers['User-Agent'], 'Referer': embed_url, 'Origin': base_pichive}

                if m_url:
                    try:
                        r_m = c_requests.get(m_url, headers=m_hdrs, impersonate="chrome124", timeout=12) if c_requests else session.get(m_url, headers=m_hdrs, timeout=12)
                        if r_m.status_code == 200:
                            m_text = r_m.text
                            # 1. Ses Kanalları (#EXT-X-MEDIA:TYPE=AUDIO)
                            for a_name, a_uri in re.findall(r'#EXT-X-MEDIA:TYPE=AUDIO.*?NAME=[\'"]([^\'"]+)[\'"].*?URI=[\'"]([^\'"]+)[\'"]', m_text, re.IGNORECASE):
                                aud_sub_url = urljoin(m_url, a_uri)
                                try:
                                    r_aud = c_requests.get(aud_sub_url, headers=m_hdrs, impersonate="chrome124", timeout=12) if c_requests else session.get(aud_sub_url, headers=m_hdrs, timeout=12)
                                    if r_aud.status_code == 200:
                                        all_aud_segs, aud_durations = extract_media_playlist_timeline(
                                            aud_sub_url,
                                            r_aud.text,
                                        )
                                        if all_aud_segs:
                                            n_low = a_name.lower()
                                            is_tr = any(k in n_low for k in ["turk", "türk", "tr", "dublaj"])
                                            label = f"Türkçe Dublaj ({a_name})" if is_tr else f"Orijinal / İngilizce ({a_name})"
                                            audio_tracks.append({
                                                "name": label,
                                                "lang": "tur" if is_tr else "eng",
                                                "segments": all_aud_segs,
                                                "durations": aud_durations,
                                                "sample_segment_url": all_aud_segs[0],
                                                "count": len(all_aud_segs),
                                                "headers": m_hdrs
                                            })
                                except Exception as aud_err:
                                    logger.debug(f"Pichive audio resolve note: {aud_err}")

                            # 2. Kalite Varyantları ve Video Segmentleri
                            from extractors.variants import extract_master_quality_variants
                            qual_variants = extract_master_quality_variants(m_url, m_text)
                            sub_url = qual_variants[0]["url"] if qual_variants else (
                                urljoin(m_url, [l.strip() for l in m_text.splitlines() if l.strip() and not l.startswith("#")][-1])
                                if any(l.strip() and not l.startswith("#") for l in m_text.splitlines()) else m_url
                            )
                            r_sub = c_requests.get(sub_url, headers=m_hdrs, impersonate="chrome124", timeout=12) if c_requests else session.get(sub_url, headers=m_hdrs, timeout=12)
                            if r_sub.status_code == 200:
                                init_match = re.search(r'#EXT-X-MAP:URI=["\']([^"\']+)["\']', r_sub.text)
                                init_seg = [urljoin(sub_url, init_match.group(1))] if init_match else []
                                v_segs = [urljoin(sub_url, l.strip()) for l in r_sub.text.splitlines() if l.strip() and not l.startswith("#")]
                                video_segments = init_seg + v_segs
                                best_video_url = sub_url
                    except Exception as ex_m:
                        logger.debug(f"Pichive master parse note: {ex_m}")

                return {
                    "video_url": best_video_url,
                    "url": best_video_url,
                    "master_url": m_url,
                    "base_host": base_pichive,
                    "subtitles": subtitles,
                    "headers": m_hdrs,
                    "audio_tracks": audio_tracks,
                    "video_segments": video_segments,
                    "total_segments": len(video_segments),
                    "qualities": qual_variants
                }
    except Exception as e:
        logger.debug(f"resolve_pichive_embed error: {e}")
    return None


def resolve_popcornvakti_embed(embed_url, session=None, headers=None, return_meta=False):
    """PopcornVakti (film.popcornvakti.net / popcornvakti) oynatıcı çözücü."""
    session = session or requests.Session()
    req_headers = dict(headers or {})
    req_headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": embed_url
    })
    try:
        if c_requests:
            r = c_requests.get(embed_url, headers=req_headers, impersonate="chrome124", timeout=12)
        else:
            r = session.get(embed_url, headers=req_headers, timeout=12)
        if r.status_code == 200:
            html = r.text
            if html.strip().startswith("#EXTM3U") or "#EXT-X-STREAM-INF" in html or "#EXTINF" in html:
                from extractors.variants import extract_master_quality_variants
                qual_variants = extract_master_quality_variants(embed_url, html)
                variant_url = qual_variants[0]["url"] if qual_variants else embed_url
                r_v = c_requests.get(variant_url, headers=req_headers, impersonate="chrome124", timeout=12) if c_requests else session.get(variant_url, headers=req_headers, timeout=12)
                segs = []
                durations = []
                if r_v.status_code == 200:
                    segs, durations = extract_media_playlist_timeline(variant_url, r_v.text)
                res_dict = {
                    "url": variant_url,
                    "video_url": variant_url,
                    "subtitles": [],
                    "segments": segs,
                    "durations": durations,
                    "video_segments": segs,
                    "total_segments": len(segs),
                    "is_m3u8": True,
                    "direct_file": False,
                    "headers": req_headers
                }
                if return_meta:
                    return res_dict
                return variant_url

            aes_m = re.search(r'CryptoJS\.AES\.decrypt\(\s*["\']([^"\']+)["\']\s*,\s*["\']([^"\']+)["\']', html)
            if aes_m:
                dec = decrypt_cryptojs_aes(aes_m.group(1), aes_m.group(2))
                f_m = re.search(r'file:\s*["\']([^"\']+)["\']', dec)
                subs = extract_subtitles_from_tracks(dec, embed_url, headers=req_headers)
                if f_m:
                    stream_u = f_m.group(1)
                    if stream_u != embed_url:
                        sub_res = resolve_popcornvakti_embed(stream_u, session=session, headers=req_headers, return_meta=True)
                        if sub_res and isinstance(sub_res, dict) and sub_res.get("segments"):
                            if subs:
                                sub_res.setdefault("subtitles", []).extend(subs)
                            if return_meta:
                                return sub_res
                            return sub_res.get("url") or stream_u
                    if return_meta:
                        return {"url": stream_u, "subtitles": subs}
                    return stream_u
    except Exception as e:
        logger.debug(f"resolve_popcornvakti_embed error: {e}")
    return None


def resolve_biplayer_embed(embed_url, session=None, headers=None, return_meta=False):
    """BiCaps BiPlayer (bicaps.live/biplayer/vid/<id>) oynatıcı çözücü."""
    session = session or requests.Session()
    req_headers = dict(headers or {})
    req_headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": embed_url
    })
    try:
        if c_requests:
            r = c_requests.get(embed_url, headers=req_headers, impersonate="chrome124", timeout=12)
        else:
            r = session.get(embed_url, headers=req_headers, timeout=12)
        if r.status_code == 200:
            drv_m = re.search(r'<iframe[^>]+src=["\']([^"\']+)["\']', r.text)
            if drv_m:
                drv_u = urljoin(embed_url, drv_m.group(1))
                drv_hdrs = dict(req_headers)
                drv_hdrs["Referer"] = embed_url
                if c_requests:
                    r_drv = c_requests.get(drv_u, headers=drv_hdrs, impersonate="chrome124", timeout=12)
                else:
                    r_drv = session.get(drv_u, headers=drv_hdrs, timeout=12)
                if r_drv.status_code == 200:
                    pop_m = re.search(r'<iframe[^>]+src=["\']([^"\']+)["\']', r_drv.text)
                    if pop_m:
                        pop_u = urljoin(drv_u, pop_m.group(1))
                        return resolve_popcornvakti_embed(pop_u, session=session, headers=drv_hdrs, return_meta=return_meta)
    except Exception as e:
        logger.debug(f"resolve_biplayer_embed error: {e}")
    return None


def resolve_videopark_embed(embed_url, session=None, headers=None, return_meta=False):
    """VideoPark (videopark.top) oynatıcı çözücü."""
    session = session or requests.Session()
    req_headers = dict(headers or {})
    req_headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": embed_url
    })
    try:
        if c_requests:
            r = c_requests.get(embed_url, headers=req_headers, impersonate="chrome124", timeout=12)
        else:
            r = session.get(embed_url, headers=req_headers, timeout=12)
        if r.status_code == 200:
            html = r.text
            subs = extract_subtitles_from_tracks(html, embed_url, headers=req_headers)

            sd_m = re.search(r'["\']stream_url["\']\s*:\s*["\']([^"\']+)["\']', html)
            if sd_m:
                st_u = sd_m.group(1)
                return {"url": st_u, "subtitles": subs} if return_meta else st_u

            f_m = re.search(r'file:\s*["\']([^"\']+\.m3u8[^"\']*)["\']', html)
            if f_m:
                st_u = f_m.group(1)
                return {"url": st_u, "subtitles": subs} if return_meta else st_u

            w_m = re.search(r"const WORKER_URL\s*=\s*['\"]([^'\"]+)['\"]", html)
            p_m = re.search(r"const PUB_ID\s*=\s*['\"]([^'\"]+)['\"]", html)
            t_m = re.search(r"const VIDEO_TITLE\s*=\s*['\"]([^'\"]+)['\"]", html)
            pub_m = re.search(r"const PUBLISHER_ID\s*=\s*['\"]([^'\"]+)['\"]", html)
            if w_m and p_m:
                w_url = w_m.group(1)
                p_id = p_m.group(1)
                title = t_m.group(1) if t_m else ""
                pub_id = pub_m.group(1) if pub_m else ""
                api_u = f"{w_url}/api/stream?pubId={quote(p_id)}&title={quote(title)}"
                if pub_id:
                    api_u += f"&publisherId={quote(pub_id)}"
                if c_requests:
                    r_api = c_requests.get(api_u, headers={"Referer": embed_url, "User-Agent": req_headers["User-Agent"]}, impersonate="chrome124", timeout=12)
                else:
                    r_api = session.get(api_u, headers={"Referer": embed_url, "User-Agent": req_headers["User-Agent"]}, timeout=12)
                if r_api.status_code == 200:
                    data = r_api.json()
                    hls = data.get("hlsSource", {}).get("file")
                    api_tracks = data.get("tracks") or data.get("subtitles") or []
                    if isinstance(api_tracks, list):
                        for t in api_tracks:
                            if isinstance(t, dict) and (t.get("file") or t.get("src")):
                                s_url = urljoin(embed_url, t.get("file") or t.get("src"))
                                s_lbl = t.get("label") or t.get("name") or "Altyazı"
                                is_tr = any(k in f"{s_lbl} {t.get('lang','')}".lower() for k in ["turk", "türk", "tr"])
                                subs.append({
                                    "url": s_url, "name": s_lbl, "label": s_lbl,
                                    "lang": "tur" if is_tr else "eng",
                                    "headers": req_headers
                                })
                    if hls:
                        return {"url": hls, "subtitles": subs} if return_meta else hls

            wb_m = re.search(r'const WORKER_BASE\s*=\s*["\']([^"\']+)["\']', html)
            vid_m = re.search(r'const VIDEO_ID\s*=\s*(\d+)', html)
            if wb_m and vid_m:
                wb_url = wb_m.group(1).replace(r"\/", "/").rstrip("/")
                st_u = f"{wb_url}/v/{vid_m.group(1)}"
                return {"url": st_u, "subtitles": subs} if return_meta else st_u
    except Exception as e:
        logger.debug(f"resolve_videopark_embed error: {e}")
    return None


def resolve_canlitvnews_embed(embed_url, session=None, headers=None):
    """Canlitvnews / PhiPlayer oynatıcı çözücü."""
    session = session or requests.Session()
    req_headers = dict(headers or {})
    req_headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": embed_url
    })
    try:
        vid_m = re.search(r'vid=([a-f0-9]+)', embed_url)
        vid = vid_m.group(1) if vid_m else None

        parsed = urlparse(embed_url)
        base_origin = f"{parsed.scheme}://{parsed.netloc}"
        ajax_url = f"{base_origin}/player/ajax_sources.php"

        if not vid:
            if c_requests:
                r_page = c_requests.get(embed_url, headers=req_headers, impersonate="chrome124", timeout=10)
            else:
                r_page = session.get(embed_url, headers=req_headers, timeout=10)
            if r_page.status_code == 200:
                h_m = re.search(r"var\s+hash\s*=\s*['\"]([a-f0-9]+)['\"]", r_page.text)
                if h_m:
                    vid = h_m.group(1)

        if vid:
            post_headers = dict(req_headers)
            post_headers.update({
                "Origin": base_origin,
                "X-Requested-With": "XMLHttpRequest"
            })
            post_data = {"vid": vid, "alternative": "ankacdn", "ord": 0}
            if c_requests:
                r_ajax = c_requests.post(ajax_url, headers=post_headers, data=post_data, impersonate="chrome124", timeout=12)
            else:
                r_ajax = session.post(ajax_url, headers=post_headers, data=post_data, timeout=12)

            if r_ajax.status_code == 200:
                data = r_ajax.json()
                sources = data.get("source", [])
                if sources:
                    best_src = sources[0].get("file")
                    if best_src:
                        return {
                            "video_url": best_src,
                            "headers": {
                                "User-Agent": req_headers["User-Agent"],
                                "Referer": f"{base_origin}/",
                                "Origin": base_origin
                            }
                        }
    except Exception as e:
        logger.debug(f"resolve_canlitvnews_embed error: {e}")
    return None


class PichiveExtractor(BaseExtractor):
    @property
    def name(self) -> str: return "Pichive Embed"
    def can_handle(self, url: str) -> bool: return "pichive" in url.lower()
    def extract(self, url: str, session=None, log_callback=None) -> ExtractorResult:
        data = resolve_pichive_embed(url, session=session)
        if not data or not data.get("video_url"): return None
        v_segs = data.get("video_segments") or []
        return ExtractorResult(
            success=True, title="Pichive Video", video_url=data["video_url"],
            video_headers=data.get("headers", {}),
            audio_tracks=data.get("audio_tracks", []),
            subtitles=data.get("subtitles", []),
            total_segments=len(v_segs) if v_segs else 0,
            direct_file=False,
            video_segments=v_segs if v_segs else None,
            raw_url=url
        )


class VideoparkExtractor(BaseExtractor):
    @property
    def name(self) -> str: return "VideoPark Embed"
    def can_handle(self, url: str) -> bool: return "videopark" in url.lower()
    def extract(self, url: str, session=None, log_callback=None) -> ExtractorResult:
        data = resolve_videopark_embed(url, session=session, return_meta=True)
        if not data: return None
        stream = data.get("url") if isinstance(data, dict) else data
        subs = data.get("subtitles", []) if isinstance(data, dict) else []
        if not stream: return None
        return ExtractorResult(
            success=True, title="VideoPark Video", video_url=stream,
            video_headers={"User-Agent": "Mozilla/5.0", "Referer": url},
            subtitles=subs, total_segments=0, direct_file=not (".m3u8" in stream), raw_url=url
        )


class BiplayerExtractor(BaseExtractor):
    @property
    def name(self) -> str: return "BiPlayer Embed"
    def can_handle(self, url: str) -> bool: return any(k in url.lower() for k in ["biplayer", "bicaps.live/biplayer"])
    def extract(self, url: str, session=None, log_callback=None) -> ExtractorResult:
        data = resolve_biplayer_embed(url, session=session, return_meta=True)
        if not data: return None
        stream = data.get("url") if isinstance(data, dict) else data
        subs = data.get("subtitles", []) if isinstance(data, dict) else []
        v_segs = data.get("video_segments") if isinstance(data, dict) else None
        if not stream: return None
        is_direct = False if (v_segs or ".m3u8" in stream or ".png" in stream) else True
        return ExtractorResult(
            success=True, title="BiPlayer Video", video_url=stream,
            video_headers=data.get("headers", {"User-Agent": "Mozilla/5.0", "Referer": url}) if isinstance(data, dict) else {"User-Agent": "Mozilla/5.0", "Referer": url},
            subtitles=subs, total_segments=len(v_segs) if v_segs else 0,
            direct_file=is_direct,
            video_segments=v_segs,
            raw_url=url
        )


class CanlitvnewsExtractor(BaseExtractor):
    @property
    def name(self) -> str: return "Canlitvnews Embed"
    def can_handle(self, url: str) -> bool: return any(k in url.lower() for k in ["canlitvnews", "canlitv.news"])
    def extract(self, url: str, session=None, log_callback=None) -> ExtractorResult:
        data = resolve_canlitvnews_embed(url, session=session)
        if not data or not data.get("video_url"): return None
        return ExtractorResult(
            success=True, title="Canlitvnews Video", video_url=data["video_url"],
            video_headers=data.get("headers", {}), subtitles=[],
            total_segments=1, direct_file=True, raw_url=url
        )


def decode_rapidvid(e: str) -> str:
    """Rapidvid av() / _() obfuscation decode: reverse -> b64decode -> K9L shift -> b64decode."""
    try:
        import base64
        rev = e[::-1]
        t = base64.b64decode(rev + "==").decode("latin1")
        o = ""
        key = "K9L"
        for i in range(len(t)):
            r = key[i % 3]
            n = ord(t[i]) - (ord(r[0]) % 5 + 1)
            o += chr(n)
        return base64.b64decode(o + "==").decode("utf-8")
    except Exception as ex:
        logger.debug(f"decode_rapidvid error: {ex}")
        return ""


def resolve_rapidvid_embed(embed_url, session=None, headers=None, parent_url=None):
    """RapidVid / FullHDFilmizlesene embed oynatıcı çözücü."""
    sess = session or requests.Session()
    ref = parent_url or "https://www.fullhdfilmizlesene.now/"
    req_h = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": ref
    }
    if headers:
        req_h.update(headers)
    try:
        r = sess.get(embed_url, headers=req_h, timeout=12)
        if r.status_code != 200:
            return None
        html = r.text

        # Extract encoded master M3U8
        av_m = re.search(r'(?:av|_)\s*\(\s*["\']([A-Za-z0-9+/=_-]{20,})["\']\s*\)', html)
        if not av_m:
            return None

        enc_str = av_m.group(1)
        master_url = decode_rapidvid(enc_str)
        if not master_url or not master_url.startswith("http"):
            return None

        # Extract subtitles from jwSetup.tracks
        subs = []
        tracks_m = re.search(r'jwSetup\.tracks\s*=\s*(\[.*?\]);', html, re.DOTALL)
        if tracks_m:
            try:
                raw_tracks = json.loads(tracks_m.group(1))
                for tr in raw_tracks:
                    if tr.get("kind") in ("captions", "subtitles") and tr.get("file"):
                        lbl = tr.get("label", "Altyazı").strip()
                        subs.append({
                            "name": lbl,
                            "url": tr.get("file"),
                            "lang": "tr" if "türk" in lbl.lower() else "en"
                        })
            except Exception:
                logger.debug("RapidVid subtitle track parsing failed", exc_info=True)

        # Fetch master playlist
        stream_h = {
            "User-Agent": req_h["User-Agent"],
            "Referer": embed_url
        }
        r_m = sess.get(master_url, headers=stream_h, timeout=12)
        if r_m.status_code != 200:
            return None
        m_text = r_m.text
        lines = [l.strip() for l in m_text.splitlines() if l.strip()]

        # Audio tracks
        audio_tracks = []
        for line in lines:
            if line.startswith("#EXT-X-MEDIA:TYPE=AUDIO"):
                name_m = re.search(r'NAME=["\']([^"\']+)["\']', line)
                lang_m = re.search(r'LANGUAGE=["\']([^"\']+)["\']', line)
                uri_m = re.search(r'URI=["\']([^"\']+)["\']', line)
                t_name = name_m.group(1) if name_m else "Ses"
                t_lang = lang_m.group(1) if lang_m else ""
                if uri_m:
                    a_uri = urljoin(master_url, uri_m.group(1))
                    try:
                        r_a = sess.get(a_uri, headers=stream_h, timeout=10)
                        if r_a.status_code == 200:
                            a_segs, a_durations = extract_media_playlist_timeline(a_uri, r_a.text)
                            if a_segs:
                                audio_tracks.append({
                                    "name": t_name,
                                    "url": a_uri,
                                    "segments": a_segs,
                                    "durations": a_durations,
                                    "language": t_lang,
                                    "headers": stream_h
                                })
                    except Exception:
                        logger.debug("RapidVid audio rendition parsing failed", exc_info=True)

        video_segs = []
        video_durations = []
        best_v = select_best_variant_url(master_url, m_text)
        if best_v:
            r_v = sess.get(best_v, headers=stream_h, timeout=10)
            if r_v.status_code == 200:
                video_segs, video_durations = extract_media_playlist_timeline(
                    best_v,
                    r_v.text,
                )

        return {
            "success": True,
            "video_url": video_segs[0] if video_segs else master_url,
            "video_headers": stream_h,
            "video_segments": video_segs,
            "video_durations": video_durations,
            "audio_tracks": audio_tracks,
            "subtitles": subs,
            "total_segments": len(video_segs),
            "direct_file": False,
            "raw_url": embed_url
        }
    except Exception as ex:
        logger.debug(f"resolve_rapidvid_embed error: {ex}")
        return None


class RapidvidExtractor(BaseExtractor):
    @property
    def name(self) -> str: return "RapidVid Embed"
    def can_handle(self, url: str) -> bool: return "rapidvid" in url.lower()
    def extract(self, url: str, session=None, log_callback=None) -> ExtractorResult:
        data = resolve_rapidvid_embed(url, session=session)
        if not data or not data.get("success"): return None
        return ExtractorResult(
            success=True,
            title="RapidVid Video",
            video_url=data.get("video_url", ""),
            video_headers=data.get("video_headers", {}),
            video_segments=data.get("video_segments", []),
            audio_tracks=data.get("audio_tracks", []),
            subtitles=data.get("subtitles", []),
            total_segments=data.get("total_segments", 0),
            direct_file=False,
            raw_url=url
        )


__all__ = [
    "resolve_vidsrc_embed",
    "resolve_pichive_embed",
    "resolve_popcornvakti_embed",
    "resolve_biplayer_embed",
    "resolve_videopark_embed",
    "resolve_canlitvnews_embed",
    "decode_rapidvid",
    "resolve_rapidvid_embed",
    "PichiveExtractor",
    "VideoparkExtractor",
    "BiplayerExtractor",
    "CanlitvnewsExtractor",
    "RapidvidExtractor",
]
