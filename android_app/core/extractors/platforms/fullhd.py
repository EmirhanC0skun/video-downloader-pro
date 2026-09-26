# -*- coding: utf-8 -*-
"""
Video Downloader Pro — FullHDFilmizlesene & FullHDFilmizle.mom Platform Extractor.

FullHDFilmizlesene:
  - HTML'de <div class="frg" data-code="BASE64"> → base64 decode → iframe HTML
  - İçindeki iframe src veya m3u8 URL'si çözülür.

FullHDFilmizle.mom (FilmPlus WordPress plugin):
  - window.videoAjax.ajaxurl + post_id + nonce → AJAX POST → embed URL
  - Embed URL'sinden HLS stream çözülür.
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

from extractors.base import BaseExtractor, ExtractorResult, DEFAULT_HEADERS
from extractors.variants import extract_media_playlist_timeline, select_best_variant_url, extract_master_quality_variants
from extractors.subtitles import extract_subtitles_from_m3u8
from extractors.platforms.anime import solve_x_sp
from extractors.embeds.players import resolve_rapidvid_embed
from logger import get_logger

logger = get_logger("extractors.platforms.fullhd")


class FullHDFilmizleseneExtractor(BaseExtractor):
    """Strategy extractor for FullHDFilmizlesene (.now TLD) — data-code base64 player."""

    @property
    def name(self) -> str:
        return "FullHDFilmizlesene Platform"

    def can_handle(self, url: str) -> bool:
        low = url.lower()
        return "fullhdfilmizlesene" in low

    def extract(self, url: str, session=None, log_callback=None) -> ExtractorResult:
        self.log(f"[*] FullHDFilmizlesene taranıyor: {url}", log_callback)
        sess = session or requests.Session()
        headers = dict(DEFAULT_HEADERS)
        headers["Referer"] = url

        # curl_cffi fallback için Cloudflare bypass dene
        page_html = ""
        try:
            r = sess.get(url, headers=headers, timeout=15)
            if r.status_code == 200:
                page_html = r.text
        except Exception:
            logger.debug("FullHDFilmizlesene primary page request failed", exc_info=True)

        if (not page_html or len(page_html) < 500) and c_requests:
            try:
                r_cf = c_requests.get(url, headers=headers, impersonate="chrome124", timeout=15)
                if r_cf.status_code == 200:
                    page_html = r_cf.text
            except Exception as ex_cf:
                logger.debug(f"FullHDFilmizlesene curl_cffi error: {ex_cf}")

        if not page_html:
            return None

        title_m = re.search(r'<title>([^<]+)</title>', page_html)
        film_title = title_m.group(1).split("izle")[0].strip() if title_m else "FullHDFilmizlesene Video"

        # 0. Modern FullHDFilmizlesene JavaScript Obfuscation: var scx = {...} (ROT13 + Base64)
        scx_match = re.search(r'var\s+scx\s*=\s*(\{.*?\});', page_html, re.DOTALL)
        if scx_match:
            try:
                import codecs
                scx_obj = json.loads(scx_match.group(1))
                def _find_strings(obj):
                    res = []
                    if isinstance(obj, dict):
                        for v in obj.values():
                            res.extend(_find_strings(v))
                    elif isinstance(obj, list):
                        for it in obj:
                            res.extend(_find_strings(it))
                    elif isinstance(obj, str):
                        res.append(obj)
                    return res

                for s_val in _find_strings(scx_obj):
                    if len(s_val) > 10:
                        try:
                            rot = codecs.decode(s_val, 'rot_13')
                            dec_url = base64.b64decode(rot).decode('utf-8', errors='ignore').strip()
                            if dec_url.startswith("http"):
                                self.log(f"[+] FullHDFilmizlesene scx embed çözüldü: {dec_url}", log_callback)
                                result = self._resolve_embed(sess, dec_url, url, film_title, headers)
                                if result:
                                    return result
                                try:
                                    from extractors.registry import default_registry
                                    sub_res = default_registry.resolve(dec_url, session=sess, log_callback=log_callback)
                                    if sub_res and sub_res.get("success"):
                                        return ExtractorResult(
                                            success=True,
                                            title=film_title or sub_res.get("title", "FullHDFilmizlesene Video"),
                                            video_url=sub_res.get("video_url", ""),
                                            video_headers=sub_res.get("video_headers", headers),
                                            video_segments=sub_res.get("video_segments", []),
                                            video_durations=sub_res.get("video_durations"),
                                            audio_tracks=sub_res.get("audio_tracks", []),
                                            subtitles=sub_res.get("subtitles", []),
                                            total_segments=sub_res.get("total_segments", 0),
                                            direct_file=sub_res.get("direct_file", False),
                                            raw_url=url,
                                        )
                                except Exception as ex_sub:
                                    logger.debug(f"FullHDFilmizlesene scx sub-resolve notice: {ex_sub}")
                        except Exception:
                            continue
            except Exception as ex_scx:
                logger.debug(f"FullHDFilmizlesene scx parse error: {ex_scx}")

        # 1. <div class="frg" data-code="BASE64"> → base64 decode → iframe HTML
        frg_matches = re.findall(
            r'<div[^>]+class=["\'][^"\']*frg[^"\']*["\'][^>]+data-code=["\']([^"\']+)["\']',
            page_html, re.IGNORECASE
        )
        # Ters sıra da dene
        if not frg_matches:
            frg_matches = re.findall(
                r'data-code=["\']([^"\']+)["\'][^>]+class=["\'][^"\']*frg[^"\']*["\']',
                page_html, re.IGNORECASE
            )

        if not frg_matches:
            # Genel data-code attribute arama
            frg_matches = re.findall(r'data-code=["\']([A-Za-z0-9+/=]{20,})["\']', page_html)

        for b64_code in frg_matches:
            try:
                decoded = base64.b64decode(b64_code + "==").decode("utf-8", errors="ignore")
                # decoded içinde iframe src veya m3u8 ara
                ifr_m = re.search(r'<iframe[^>]+src=["\']([^"\']+)["\']', decoded, re.IGNORECASE)
                m3u8_m = re.search(r'(https?://[^\s"\'<>]+\.m3u8(?:\?[^\s"\'<>]*)?)', decoded)

                embed_url = None
                if ifr_m:
                    embed_url = urljoin(url, ifr_m.group(1).strip())
                elif m3u8_m:
                    # Doğrudan m3u8 — segment listesi oluştur
                    m3u8_url = m3u8_m.group(1)
                    segs = self._resolve_m3u8_segments(sess, m3u8_url, headers)
                    if segs:
                        return ExtractorResult(
                            success=True,
                            title=film_title,
                            video_url=segs[0],
                            video_headers=headers,
                            video_segments=segs,
                            total_segments=len(segs),
                            direct_file=False,
                            raw_url=url,
                        )

                if embed_url:
                    self.log(f"[+] FullHDFilmizlesene data-code iframe: {embed_url}", log_callback)
                    result = self._resolve_embed(sess, embed_url, url, film_title, headers)
                    if result:
                        return result
                    try:
                        from extractors.registry import default_registry
                        sub_res = default_registry.resolve(embed_url, session=sess, log_callback=log_callback)
                        if sub_res and sub_res.get("success"):
                            return ExtractorResult(
                                success=True,
                                title=film_title or sub_res.get("title", "FullHDFilmizlesene Video"),
                                video_url=sub_res.get("video_url", ""),
                                video_headers=sub_res.get("video_headers", headers),
                                video_segments=sub_res.get("video_segments", []),
                                video_durations=sub_res.get("video_durations"),
                                audio_tracks=sub_res.get("audio_tracks", []),
                                subtitles=sub_res.get("subtitles", []),
                                total_segments=sub_res.get("total_segments", 0),
                                direct_file=sub_res.get("direct_file", False),
                                raw_url=url,
                            )
                    except Exception as ex_sub:
                        logger.debug(f"FullHDFilmizlesene registry sub-resolve error: {ex_sub}")
            except Exception as ex_b64:
                logger.debug(f"FullHDFilmizlesene data-code parse error: {ex_b64}")

        # 2. Sayfadan doğrudan iframe ara
        iframes = re.findall(r'<iframe[^>]+src=["\']([^"\']+)["\']', page_html, re.IGNORECASE)
        for ifr in iframes:
            ifr_full = urljoin(url, ifr.strip())
            if any(k in ifr_full.lower() for k in ["player", "embed", "video", "stream", "youtube"]):
                result = self._resolve_embed(sess, ifr_full, url, film_title, headers)
                if result:
                    return result
                try:
                    from extractors.registry import default_registry
                    sub_res = default_registry.resolve(ifr_full, session=sess, log_callback=log_callback)
                    if sub_res and sub_res.get("success"):
                        return ExtractorResult(
                            success=True,
                            title=film_title or sub_res.get("title", "FullHDFilmizlesene Video"),
                            video_url=sub_res.get("video_url", ""),
                            video_headers=sub_res.get("video_headers", headers),
                            video_segments=sub_res.get("video_segments", []),
                            video_durations=sub_res.get("video_durations"),
                            audio_tracks=sub_res.get("audio_tracks", []),
                            subtitles=sub_res.get("subtitles", []),
                            total_segments=sub_res.get("total_segments", 0),
                            direct_file=sub_res.get("direct_file", False),
                            raw_url=url,
                        )
                except Exception:
                    logger.debug("FullHDFilmizlesene nested iframe resolve failed", exc_info=True)

        # 3. Sayfadan doğrudan m3u8 ara
        m3u8_urls = re.findall(r'(https?://[^\s"\'<>]+\.m3u8(?:\?[^\s"\'<>]*)?)', page_html)
        for m3u8_url in m3u8_urls:
            segs = self._resolve_m3u8_segments(sess, m3u8_url, headers)
            if segs:
                return ExtractorResult(
                    success=True,
                    title=film_title,
                    video_url=segs[0],
                    video_headers=headers,
                    video_segments=segs,
                    total_segments=len(segs),
                    direct_file=False,
                    raw_url=url,
                )

        return None

    def _resolve_embed(self, sess, embed_url, referer_url, title, parent_headers):
        """Embed URL'sinden HLS stream çözmeye çalışır."""
        try:
            if "rapidvid" in embed_url.lower():
                rv_data = resolve_rapidvid_embed(embed_url, session=sess, headers=parent_headers, parent_url=referer_url)
                if rv_data and rv_data.get("success"):
                    return ExtractorResult(
                        success=True,
                        title=title,
                        video_url=rv_data.get("video_url", ""),
                        video_headers=rv_data.get("video_headers", {}),
                        video_segments=rv_data.get("video_segments", []),
                        video_durations=rv_data.get("video_durations"),
                        audio_tracks=rv_data.get("audio_tracks", []),
                        subtitles=rv_data.get("subtitles", []),
                        total_segments=rv_data.get("total_segments", 0),
                        direct_file=False,
                        raw_url=embed_url
                    )

            emb_h = {"User-Agent": parent_headers["User-Agent"], "Referer": referer_url}
            r_emb = sess.get(embed_url, headers=emb_h, timeout=12)
            if r_emb.status_code != 200:
                return None
            emb_html = r_emb.text

            if "rapidvid" in emb_html.lower() or "av(" in emb_html:
                rv_data = resolve_rapidvid_embed(embed_url, session=sess, headers=parent_headers, parent_url=referer_url)
                if rv_data and rv_data.get("success"):
                    return ExtractorResult(
                        success=True,
                        title=title,
                        video_url=rv_data.get("video_url", ""),
                        video_headers=rv_data.get("video_headers", emb_h),
                        video_segments=rv_data.get("video_segments", []),
                        video_durations=rv_data.get("video_durations"),
                        audio_tracks=rv_data.get("audio_tracks", []),
                        subtitles=rv_data.get("subtitles", []),
                        total_segments=rv_data.get("total_segments", 0),
                        direct_file=False,
                        raw_url=embed_url
                    )

            # m3u8 ara
            m3u8_m = re.search(
                r'(?:file|src)["\']?\s*[:=]\s*["\']?(https?://[^\s"\'<>]+\.m3u8(?:\?[^\s"\'<>]*)?)',
                emb_html, re.IGNORECASE
            ) or re.search(r'(https?://[^\s"\'<>]+\.m3u8(?:\?[^\s"\'<>]*)?)', emb_html)

            if m3u8_m:
                m3u8_url = m3u8_m.group(1)
                segs = self._resolve_m3u8_segments(sess, m3u8_url, emb_h)
                if segs:
                    subs = extract_subtitles_from_m3u8(m3u8_url, custom_headers=emb_h)
                    return ExtractorResult(
                        success=True,
                        title=title,
                        video_url=segs[0],
                        video_headers=emb_h,
                        video_segments=segs,
                        subtitles=subs or [],
                        total_segments=len(segs),
                        direct_file=False,
                        raw_url=referer_url,
                    )
        except Exception as ex:
            logger.debug(f"FullHDFilmizlesene embed resolve error: {ex}")
        return None


class FullHDFilmizleMomExtractor(BaseExtractor):
    """Strategy extractor for FullHDFilmizle.mom — WordPress FilmPlus AJAX player.

    Zincir:
    1. Film sayfası → window.videoAjax (ajaxurl, nonce) + post_id + Change_Source(player_name)
    2. AJAX POST get_video_url → {"success":true,"data":{"url":"https://setplay.shop/player/?t=TOKEN"}}
    3. setplay.shop → SPG.cerceve(id, data_b64, key_b64) XOR decode → fastplay.mom/video/ID
    4. fastplay.mom → window.FSP.stream = "/manifests/ID/master.txt?verify=TOKEN"
    5. CDN (SPG.isin decode) → master.txt → HLS segment listesi
    """

    @property
    def name(self) -> str:
        return "FullHDFilmizle.mom Platform"

    def can_handle(self, url: str) -> bool:
        low = url.lower()
        return "fullhdfilmizle.mom" in low or ("fullhdfilmizle" in low and ".mom" in low)

    def _xor_decode(self, data_b64: str, key_b64: str) -> str:
        """SPG atob(data) XOR atob(key) → URL."""
        try:
            data_bytes = base64.b64decode(data_b64 + "==")
            key_bytes = base64.b64decode(key_b64 + "==")
            result = ""
            for i, b in enumerate(data_bytes):
                result += chr(b ^ key_bytes[i % len(key_bytes)])
            return result.split("|")[0]
        except Exception:
            return ""

    def extract(self, url: str, session=None, log_callback=None) -> ExtractorResult:
        self.log(f"[*] FullHDFilmizle.mom taranıyor: {url}", log_callback)
        sess = session or requests.Session()
        headers = dict(DEFAULT_HEADERS)
        headers["Referer"] = url

        page_html = ""
        try:
            r = sess.get(url, headers=headers, timeout=15)
            if r.status_code == 200:
                page_html = r.text
        except Exception:
            logger.debug("FullHDFilmizle.mom primary page request failed", exc_info=True)

        if (not page_html or len(page_html) < 500) and c_requests:
            try:
                r_cf = c_requests.get(url, headers=headers, impersonate="chrome124", timeout=15)
                if r_cf.status_code == 200:
                    page_html = r_cf.text
            except Exception as ex_cf:
                logger.debug(f"FullHDFilmizle.mom curl_cffi error: {ex_cf}")

        if not page_html:
            return None

        title_m = re.search(r'<title>([^<]+)</title>', page_html)
        film_title = title_m.group(1).split("izle")[0].strip() if title_m else "FullHDFilmizle Video"

        # 1. WordPress FilmPlus AJAX parametrelerini çıkar
        ajax_url_m = re.search(r"ajaxurl\s*[=:'\"]+\s*['\"]([^'\"]+)['\"]", page_html)
        post_id_m = (
            re.search(r'data-part=["\'](\d+)["\']', page_html)
            or re.search(r'Change_Source\s*\(\s*["\'](\d+)["\']', page_html)
            or re.search(r'(?:post_id|postid)\s*[=:,]\s*[\'"]?(\d+)', page_html)
        )
        nonce_m = re.search(r"nonce['\"]?\s*[=:,]\s*['\"]([a-f0-9]{8,})['\"]", page_html, re.IGNORECASE)

        if not (ajax_url_m and post_id_m and nonce_m):
            logger.debug("FullHDFilmizle.mom: AJAX params not found")
            return None

        ajax_url_val = ajax_url_m.group(1)
        post_id = post_id_m.group(1)
        nonce = nonce_m.group(1)

        # 2. Change_Source(post_id, player_name) → player isimlerini bul
        source_calls = re.findall(
            r"Change_Source\s*\(\s*['\"]?(\d+)['\"]?\s*,\s*['\"]([^'\"]+)['\"]",
            page_html
        )
        player_names = list(dict.fromkeys([pn for _, pn in source_calls]))
        if not player_names:
            player_names = ["SetPlay", "main", "default"]

        parsed = urlparse(url)
        ajax_headers = {
            "User-Agent": headers["User-Agent"],
            "Referer": url,
            "Origin": f"{parsed.scheme}://{parsed.netloc}",
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        embed_url = None
        for pname in player_names:
            try:
                r_ajax = sess.post(
                    ajax_url_val,
                    data={"action": "get_video_url", "post_id": post_id,
                          "player_name": pname, "nonce": nonce},
                    headers=ajax_headers,
                    timeout=12,
                )
                if r_ajax.status_code == 200:
                    aj_data = r_ajax.json()
                    if aj_data.get("success") and aj_data.get("data", {}).get("url"):
                        embed_url = aj_data["data"]["url"]
                        self.log(f"[+] FullHDFilmizle.mom AJAX '{pname}' -> {embed_url[:60]}", log_callback)
                        break
            except Exception as ex_aj:
                logger.debug(f"FullHDFilmizle.mom AJAX error for '{pname}': {ex_aj}")

        if not embed_url:
            logger.debug("FullHDFilmizle.mom: no embed URL from AJAX")
            return None

        # 3. setplay.shop → SPG.cerceve XOR decode → fastplay.mom URL
        if "setplay.shop" in embed_url:
            result = self._resolve_setplay_chain(sess, embed_url, url, film_title, headers)
            if result:
                return result

        # 4. Genel embed zinciri deneme (setplay dışı)
        result = self._resolve_embed_chain(sess, embed_url, url, film_title, headers)
        if result:
            return result

        return None

    def _resolve_setplay_chain(self, sess, setplay_url, referer, title, parent_headers):
        """setplay.shop → SPG.cerceve XOR → fastplay.mom → window.FSP.stream → CDN HLS."""
        try:
            sp_h = {"User-Agent": parent_headers["User-Agent"], "Referer": referer}
            r_sp = sess.get(setplay_url, headers=sp_h, timeout=15, allow_redirects=True)
            if r_sp.status_code != 200:
                return None
            sp_html = r_sp.text

            # SPG.cerceve("id", data_b64, key_b64)
            cerceve_m = re.search(
                r'SPG\.cerceve\s*\(\s*["\']([^"\']+)["\']\s*,\s*["\']([^"\']+)["\']\s*,\s*["\']([^"\']+)["\']',
                sp_html
            )
            if not cerceve_m:
                return None

            data_b64 = cerceve_m.group(2)
            key_b64 = cerceve_m.group(3)
            iframe_src = self._xor_decode(data_b64, key_b64)
            logger.debug(f"setplay.shop XOR → {iframe_src[:80]}")

            if not iframe_src or not iframe_src.startswith("http"):
                # Fallback: KOKEN + jeton
                koken_m = re.search(r'KOKEN\s*=\s*["\']([^"\']+)["\']', sp_html)
                jeton_m = re.search(r'jeton\s*=\s*["\']([^"\']+)["\']', sp_html)
                if koken_m and jeton_m:
                    iframe_src = f"{koken_m.group(1)}/embed/?t={jeton_m.group(1)}"

            if not iframe_src:
                return None

            return self._resolve_fastplay(sess, iframe_src, setplay_url, title, parent_headers)

        except Exception as ex:
            logger.debug(f"FullHDFilmizle.mom setplay chain error: {ex}")
            return None

    def _resolve_fastplay(self, sess, fastplay_url, referer, title, parent_headers):
        """fastplay.mom → window.FSP.stream → CDN manifest → HLS segments."""
        try:
            fp_h = {"User-Agent": parent_headers["User-Agent"], "Referer": referer}
            r_fp = sess.get(fastplay_url, headers=fp_h, timeout=15, allow_redirects=True)
            if r_fp.status_code != 200:
                return None
            fp_html = r_fp.text
            fp_base = r_fp.url  # final URL after redirects

            # window.FSP.stream: "/manifests/ID/master.txt?verify=TOKEN"
            fsp_m = re.search(r'stream\s*:\s*["\']([^"\']+)["\']', fp_html)
            if not fsp_m:
                return None
            stream_path = fsp_m.group(1)

            # CDN domains: SPG.isin(data_b64, key_b64) → xor decode → "srv.x.cfd|srv.y.cfd|..."
            isin_m = re.search(
                r'SPG\.isin\s*\(\s*["\']([^"\']+)["\']\s*,\s*["\']([^"\']+)["\']',
                fp_html
            )
            cdn_domains = []
            if isin_m:
                isin_decoded = self._xor_decode(isin_m.group(1), isin_m.group(2))
                cdn_domains = [d.strip() for d in isin_decoded.split("|") if d.strip()]

            # Determine fastplay base host for manifest
            from urllib.parse import urlparse as _up
            fp_parsed = _up(fp_base)
            fp_host = f"{fp_parsed.scheme}://{fp_parsed.netloc}"

            # Calculate X-Sp if present
            x_sp = None
            try:
                x_sp = solve_x_sp(fp_html)
            except Exception:
                logger.debug("FullHDFilmizle.mom x-sp extraction failed", exc_info=True)

            manifest_h = {"User-Agent": "Mozilla/5.0", "Referer": fastplay_url}
            if x_sp:
                manifest_h["X-Sp"] = x_sp

            # Try CDN domains first, then fastplay.mom itself
            hosts_to_try = [f"https://{cdn}" for cdn in cdn_domains] + [fp_host]

            for host in hosts_to_try:
                manifest_url = urljoin(host, stream_path)
                try:
                    r_m = sess.get(manifest_url, headers=manifest_h, timeout=10, allow_redirects=True)
                    if r_m.status_code == 200 and r_m.text.strip().startswith("#EXTM3U"):
                        lines = [l.strip() for l in r_m.text.splitlines() if l.strip()]

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
                                    a_uri = urljoin(manifest_url, uri_m.group(1))
                                    try:
                                        r_a = sess.get(a_uri, headers=manifest_h, timeout=10)
                                        if r_a.status_code == 200:
                                            a_segs, a_durations = extract_media_playlist_timeline(a_uri, r_a.text)
                                            if a_segs:
                                                audio_tracks.append({
                                                    "name": t_name,
                                                    "url": a_uri,
                                                    "segments": a_segs,
                                                    "durations": a_durations,
                                                    "language": t_lang,
                                                    "headers": manifest_h,
                                                })
                                    except Exception:
                                        logger.debug("FullHDFilmizle.mom audio rendition parse failed", exc_info=True)

                        # Subtitles
                        subs = []
                        for line in lines:
                            if line.startswith("#EXT-X-MEDIA:TYPE=SUBTITLES"):
                                name_m = re.search(r'NAME=["\']([^"\']+)["\']', line)
                                uri_m = re.search(r'URI=["\']([^"\']+)["\']', line)
                                if uri_m:
                                    subs.append({
                                        "name": name_m.group(1) if name_m else "Altyazı",
                                        "url": urljoin(manifest_url, uri_m.group(1)),
                                        "lang": "tr" if "türk" in (name_m.group(1) if name_m else "").lower() else "en"
                                    })

                        # Video segments
                        video_segs, video_durations = self._parse_m3u8(
                            sess,
                            r_m.url or manifest_url,
                            r_m.text,
                            manifest_h,
                            return_timeline=True,
                        )

                        if video_segs:
                            return ExtractorResult(
                                success=True,
                                title=title,
                                video_url=video_segs[0],
                                video_headers=manifest_h,
                                video_segments=video_segs,
                                video_durations=video_durations,
                                audio_tracks=audio_tracks if audio_tracks else None,
                                subtitles=subs,
                                total_segments=len(video_segs),
                                direct_file=False,
                                raw_url=fastplay_url,
                            )
                except Exception:
                    continue

            # Also try m3u8 URLs directly from fastplay HTML
            m3u8s = re.findall(r'(https?://[^\s"\'<>]+\.m3u8(?:\?[^\s"\'<>]*)?)', fp_html)
            for m3u8_url in m3u8s:
                segs = self._resolve_m3u8_segments(sess, m3u8_url, manifest_h)
                if segs:
                    return ExtractorResult(
                        success=True,
                        title=title,
                        video_url=segs[0],
                        video_headers=manifest_h,
                        video_segments=segs,
                        total_segments=len(segs),
                        direct_file=False,
                        raw_url=fastplay_url,
                    )

        except Exception as ex:
            logger.debug(f"FullHDFilmizle.mom fastplay resolve error: {ex}")
        return None

    def _parse_m3u8(self, sess, base_url, content, headers, return_timeline=False):
        """Master veya media playlist'i parse eder, segment listesi döndürür."""
        lines = [l.strip() for l in content.splitlines() if l.strip()]
        variant_lines = [
            line
            for line in lines
            if not line.startswith("#")
            and re.search(r"\.(?:m3u8|txt)(?:[?#]|$)", line, re.IGNORECASE)
        ]
        if variant_lines:
            best = select_best_variant_url(base_url, content, default=urljoin(base_url, variant_lines[0]))
            try:
                r2 = sess.get(best, headers=headers, timeout=10, allow_redirects=True)
                if r2.status_code == 200:
                    lines = [l.strip() for l in r2.text.splitlines() if l.strip()]
                    base_url = r2.url
            except Exception:
                logger.debug("FullHDFilmizle.mom child playlist request failed", exc_info=True)
        segments, durations = extract_media_playlist_timeline(base_url, "\n".join(lines))
        if return_timeline:
            return segments, durations
        return segments

    def _resolve_embed_chain(self, sess, embed_url, referer_url, title, parent_headers):
        """Genel embed URL'si çözücü (setplay dışı)."""
        try:
            emb_h = {"User-Agent": parent_headers["User-Agent"], "Referer": referer_url}
            r_emb = sess.get(embed_url, headers=emb_h, timeout=12, allow_redirects=True)
            if r_emb.status_code != 200:
                return None
            emb_html = r_emb.text
            final_url = r_emb.url

            m3u8_m = re.search(
                r'(?:file|src)["\']?\s*[:=]\s*["\']?(https?://[^\s"\'<>]+\.m3u8(?:\?[^\s"\'<>]*)?)',
                emb_html, re.IGNORECASE
            ) or re.search(r'(https?://[^\s"\'<>]+\.m3u8(?:\?[^\s"\'<>]*)?)', emb_html)

            if m3u8_m:
                m3u8_url = m3u8_m.group(1)
                segs = self._resolve_m3u8_segments(sess, m3u8_url, emb_h)
                if segs:
                    return ExtractorResult(
                        success=True,
                        title=title,
                        video_url=segs[0],
                        video_headers=emb_h,
                        video_segments=segs,
                        total_segments=len(segs),
                        direct_file=False,
                        raw_url=referer_url,
                    )
        except Exception as ex:
            logger.debug(f"FullHDFilmizle.mom embed chain error: {ex}")
        return None


__all__ = ["FullHDFilmizleseneExtractor", "FullHDFilmizleMomExtractor"]
