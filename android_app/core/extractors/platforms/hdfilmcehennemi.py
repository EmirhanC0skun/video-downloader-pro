# -*- coding: utf-8 -*-
"""
Video Downloader Pro — HDFilmcehennemi & Rapidrame Platform Extractor.
Resolves Rapidrame dynamic JavaScript decryption, mirror hosts, and WordPress FilmPlus AJAX.
"""

import re
import json
import base64
import subprocess
from urllib.parse import parse_qs, urlparse, urljoin, urlunparse
import requests

try:
    from curl_cffi import requests as c_requests
except Exception:
    c_requests = None

from extractors.base import BaseExtractor, ExtractorResult, DEFAULT_HEADERS
from extractors.subtitles import extract_subtitles_from_tracks, extract_subtitles_from_m3u8
from extractors.variants import extract_master_quality_variants, extract_media_playlist_timeline
from extractors.embeds.vidmoly import resolve_vidmoly_embed
from extractors.embeds.streamwish import resolve_streamwish_embed
from logger import get_logger

logger = get_logger("extractors.platforms.hdfilmcehennemi")


def _rapidrame_cdn_candidates(url):
    candidates = [url]
    parsed = urlparse(url)
    if not parsed.netloc.lower().endswith(".rapidrame.com"):
        return candidates
    query = parse_qs(parsed.query)
    for key in ("srv", "p1", "p2"):
        for shard in query.get(key, []):
            if not re.fullmatch(r"s\d+", shard, re.IGNORECASE):
                continue
            candidate = urlunparse(parsed._replace(netloc=f"{shard.lower()}.rapidrame.com"))
            if candidate not in candidates:
                candidates.append(candidate)
    return candidates


def _decode_dean_edwards_sources(html):
    """Resolve packed player variables inside an isolated Node VM context."""
    source_names = []
    for name in re.findall(
        r'(?<!//)sources\s*:\s*\[\s*\{\s*file\s*:\s*(\w+)',
        html,
        re.IGNORECASE,
    ):
        if name not in source_names:
            source_names.append(name)
    if not source_names:
        return None

    packed_scripts = re.findall(
        r'eval\((function\(p,a,c,k,e,d\).*?\}\))\)',
        html,
        re.DOTALL,
    )
    for packed_expression in packed_scripts:
        try:
            expression_b64 = base64.b64encode(packed_expression.encode("utf-8")).decode("ascii")
            names_json = json.dumps(source_names)
            js_code = f"""
            const vm = require('vm');
            const expression = Buffer.from('{expression_b64}', 'base64').toString('utf8');
            const helpers = {{
                atob: (value) => Buffer.from(value, 'base64').toString('binary'),
                btoa: (value) => Buffer.from(value, 'binary').toString('base64')
            }};
            const unpacked = vm.runInNewContext('(' + expression + ')', helpers, {{timeout: 1000}});
            const sandbox = {{...helpers}};
            vm.runInNewContext(String(unpacked), sandbox, {{timeout: 1000}});
            const names = {names_json};
            for (const name of names) {{
                const value = sandbox[name];
                if (typeof value === 'string' &&
                    (value.startsWith('http://') || value.startsWith('https://'))) {{
                    process.stdout.write(value);
                    break;
                }}
            }}
            """
            proc = subprocess.run(
                ["node", "-e", js_code],
                capture_output=True,
                text=True,
                timeout=5,
            )
            decoded = proc.stdout.strip()
            if proc.returncode == 0 and decoded.startswith(("http://", "https://")):
                return decoded
            if proc.returncode != 0:
                logger.debug("Rapidrame packed script VM failed: %s", proc.stderr.strip())
        except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
            logger.debug("Rapidrame packed script decode failed: %s", exc)
    return None


def js_atob(s):
    try:
        return base64.b64decode(s).decode('latin1')
    except Exception:
        return s


def decode_rapidrame_script(html):
    """
    HDFilmcehennemi / Rapidrame player içerisindeki dinamik JS şifreleyicisini evrensel olarak çözer.
    """
    packed_source = _decode_dean_edwards_sources(html)
    if packed_source:
        return packed_source

    # 1. Saf Python Dönüştürücü Motoru (Hızlı, güvenli ve bağımsız)
    func_match = re.search(r'function\s+(dc_\w+)\(value_parts\)\s*\{(.*?return unmix;.*?)\}', html, re.DOTALL)
    var_match = re.search(r'var\s+(s_\w+)\s*=\s*(dc_\w+)\((\[.*?\])\);', html, re.DOTALL)

    if func_match and var_match:
        try:
            func_body = func_match.group(2)
            parts = json.loads(var_match.group(3))
            cur = "".join(parts)

            for line in func_body.split(";"):
                line = line.strip()
                if "result = atob(result)" in line:
                    cur = js_atob(cur)
                elif "result.split('').reverse().join('')" in line:
                    cur = cur[::-1]
                elif "result.replace(/[a-zA-Z]/g" in line:
                    rot_match = re.search(r'\+\s*(\d+)\)\s*%\s*26', line)
                    if rot_match:
                        shift = int(rot_match.group(1))
                        new_chars = []
                        for c in cur:
                            o = ord(c)
                            if 65 <= o <= 90:
                                new_chars.append(chr((o - 65 + shift) % 26 + 65))
                            elif 97 <= o <= 122:
                                new_chars.append(chr((o - 97 + shift) % 26 + 97))
                            else:
                                new_chars.append(c)
                        cur = "".join(new_chars)

            acc_match = re.search(r'var\s+acc\s*=\s*(\d+)', func_body)
            step_match = re.search(r'acc\s*=\s*\(acc\s*\+\s*(\d+)\)\s*%\s*256', func_body)
            if acc_match and step_match:
                acc = int(acc_match.group(1))
                step = int(step_match.group(1))
                unmix = bytearray()
                for ch in cur:
                    b = ord(ch)
                    acc = (acc + step) % 256
                    plain = b ^ acc
                    acc = (acc + b) % 256
                    unmix.append(plain)

                try:
                    res = unmix.decode('utf-8')
                except Exception:
                    res = unmix.decode('latin1', errors='ignore')
                if res and res.startswith("http"):
                    return res
        except Exception as e:
            logger.debug(f"decode_rapidrame_script python error: {e}")

    # 2. Node.js ile çalıştırma (Yedek fallback)
    if func_match and var_match:
        try:
            js_code = f"""
            function atob(str) {{ return Buffer.from(str, 'base64').toString('binary'); }}
            function btoa(str) {{ return Buffer.from(str, 'binary').toString('base64'); }}
            {func_match.group(0)}
            process.stdout.write({var_match.group(2)}({var_match.group(3)}));
            """
            proc = subprocess.run(["node", "-e", js_code], capture_output=True, text=True, timeout=4)
            if proc.returncode == 0 and proc.stdout.strip().startswith("http"):
                return proc.stdout.strip()
        except Exception as ex_node:
            logger.debug(f"decode_rapidrame_script node error: {ex_node}")

    # 3. Genel script blokları için son çare çözümleme
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
    for s in scripts:
        var_m = re.search(r'var\s+(\w+)\s*=\s*(\w+)\((\[[^\]]+\])\);', s, re.DOTALL)
        if var_m and "function " in s:
            v_name = var_m.group(1)
            try:
                js_code = f"""
                function atob(str) {{ return Buffer.from(str, 'base64').toString('binary'); }}
                function btoa(str) {{ return Buffer.from(str, 'binary').toString('base64'); }}
                {s}
                if (typeof {v_name} !== 'undefined') {{
                    process.stdout.write(String({v_name}));
                }}
                """
                proc = subprocess.run(["node", "-e", js_code], capture_output=True, text=True, timeout=4)
                if proc.returncode == 0 and proc.stdout.strip().startswith("http"):
                    return proc.stdout.strip()
            except Exception as ex_node:
                logger.debug(f"decode_rapidrame_script node error: {ex_node}")

    return None


class HDFilmcehennemiExtractor(BaseExtractor):
    """Strategy extractor for HDFilmcehennemi and Rapidrame players."""

    @property
    def name(self) -> str:
        return "HDFilmcehennemi & Rapidrame"

    def can_handle(self, url: str) -> bool:
        low = url.lower()
        return "hdfilmcehennemi" in low or "rapidrame" in low

    def extract(self, url: str, session=None, log_callback=None) -> ExtractorResult:
        self.log(f"[*] HDFilmcehennemi taranıyor: {url}", log_callback)
        sess = session or (c_requests.Session(impersonate="chrome124") if c_requests else requests.Session())
        headers = dict(DEFAULT_HEADERS)
        headers["Referer"] = url

        try:
            r = sess.get(url, headers=headers, timeout=12)
            if r.status_code != 200:
                return None
            page_html = r.text
        except Exception as e:
            logger.debug(f"HDFilmcehennemi fetch error: {e}")
            return None

        title_m = re.search(r'<title>([^<]+)</title>', page_html)
        film_title = title_m.group(1).split("izle")[0].strip() if title_m else "HDFilmcehennemi Video"

        rapidrame_matches = re.findall(r'(https?://[^\s"\'<>]+(?:hdfilmcehennemi|rapidrame)[^\s"\'<>]+(?:embed|video)[^\s"\'<>]*)', page_html)
        if not rapidrame_matches:
            iframes = re.findall(r'<iframe[^>]+(?:src|data-src)=[\'"]([^\'"]+)[\'"]', page_html)
            rapidrame_matches = [i for i in iframes if "embed" in i or "video" in i or "rapidrame" in i]

        player_ids = list(dict.fromkeys(re.findall(r'data-video=[\'"](\d+)[\'"]', page_html)))
        ajax_headers = dict(headers)
        ajax_headers["X-Requested-With"] = "fetch"
        for player_id in player_ids:
            ajax_url = urljoin(url, f"/video/{player_id}/")
            try:
                ajax_response = sess.get(ajax_url, headers=ajax_headers, timeout=12)
                if not ajax_response or ajax_response.status_code != 200:
                    continue
                try:
                    payload = ajax_response.json()
                except (ValueError, AttributeError):
                    payload = json.loads(ajax_response.text)
                player_html = ""
                if isinstance(payload, dict):
                    player_html = payload.get("html", "")
                    if not player_html and isinstance(payload.get("data"), dict):
                        player_html = payload["data"].get("html", "")
                for iframe_url in re.findall(
                    r'<iframe[^>]+(?:src|data-src)=[\'"]([^\'"]+)[\'"]',
                    player_html,
                    re.IGNORECASE,
                ):
                    absolute_iframe = urljoin(url, iframe_url)
                    if absolute_iframe not in rapidrame_matches:
                        rapidrame_matches.append(absolute_iframe)
            except (requests.RequestException, ValueError, TypeError) as ajax_exc:
                logger.debug("HDFilmcehennemi AJAX player %s failed: %s", player_id, ajax_exc)

        if rapidrame_matches:
            candidate_embeds = []
            prioritized_embeds = sorted(
                rapidrame_matches,
                key=lambda candidate: 0 if "/rplayer/" in candidate.lower() else 1,
            )
            for matched_embed in prioritized_embeds:
                embed_url = urljoin(url, matched_embed)
                if embed_url.startswith("//"):
                    embed_url = "https:" + embed_url
                if embed_url not in candidate_embeds:
                    candidate_embeds.append(embed_url)

                c_host = urlparse(embed_url).netloc
                for m_ext in [".nl", ".net", ".io", ".org", ".mobi"]:
                    alt_e = embed_url.replace(c_host, f"www.hdfilmcehennemi{m_ext}")
                    if alt_e not in candidate_embeds:
                        candidate_embeds.append(alt_e)

            for ce in candidate_embeds:
                try:
                    ce_parsed = urlparse(ce)
                    ce_origin = f"{ce_parsed.scheme}://{ce_parsed.netloc}"
                    rr_headers = {
                        "User-Agent": headers["User-Agent"],
                        "Referer": url,
                        "Origin": ce_origin
                    }
                    r_rr = sess.get(ce, headers=rr_headers, timeout=12)
                    if not r_rr or r_rr.status_code != 200:
                        continue

                    # 1. Rapidrame dinamik JS şifre çözümü
                    dec_u = decode_rapidrame_script(r_rr.text)

                    # 2. İkincil gömülü oynatıcı kontrolü (VidMoly / StreamWish / iFrame)
                    if not dec_u:
                        sub_ifrs = re.findall(r'<iframe[^>]+src=[\'"]([^\'"]+)[\'"]', r_rr.text)
                        for s_ifr in sub_ifrs:
                            if s_ifr.startswith("//"): s_ifr = "https:" + s_ifr
                            if "vidmoly" in s_ifr:
                                dec_u = resolve_vidmoly_embed(s_ifr, session=sess, headers=rr_headers)
                                if dec_u: break
                            elif "streamwish" in s_ifr or "swish" in s_ifr:
                                dec_u = resolve_streamwish_embed(s_ifr, session=sess, headers=rr_headers)
                                if dec_u: break

                    # 3. HTML içi doğrudan m3u8 taraması
                    if not dec_u:
                        m3_direct = re.findall(r'["\'](https?://[^"\']+\.m3u8[^"\']*)["\']', r_rr.text)
                        if m3_direct:
                            dec_u = m3_direct[0]

                    if dec_u:
                        if dec_u.startswith("//"):
                            dec_u = "https:" + dec_u
                        elif dec_u.startswith("/"):
                            dec_u = urljoin(ce, dec_u)

                        stream_headers = {
                            "User-Agent": headers["User-Agent"],
                            "Referer": ce,
                            "Origin": ce_origin
                        }
                        subs = extract_subtitles_from_tracks(r_rr.text, ce, headers=stream_headers)

                        is_m3u8 = (".m3u8" in dec_u.lower() or "/txt/" in dec_u.lower() or "master.txt" in dec_u.lower())
                        audio_tracks = []
                        if is_m3u8:
                            try:
                                r_mst = None
                                for manifest_candidate in _rapidrame_cdn_candidates(dec_u):
                                    try:
                                        candidate_response = sess.get(
                                            manifest_candidate,
                                            headers=stream_headers,
                                            timeout=10,
                                        )
                                    except Exception as manifest_exc:
                                        logger.debug(
                                            "Rapidrame manifest shard failed (%s): %s",
                                            urlparse(manifest_candidate).netloc,
                                            manifest_exc,
                                        )
                                        continue
                                    if candidate_response and candidate_response.status_code == 200:
                                        r_mst = candidate_response
                                        dec_u = manifest_candidate
                                        break
                                if r_mst and r_mst.status_code == 200:
                                    m_subs = extract_subtitles_from_m3u8(r_mst.text, dec_u, headers=stream_headers)
                                    if m_subs:
                                        subs.extend(m_subs)

                                    # Ses Kanallarını Yakala (#EXT-X-MEDIA:TYPE=AUDIO)
                                    for a_name, a_uri in re.findall(r'#EXT-X-MEDIA:TYPE=AUDIO.*?NAME=[\'"]([^\'"]+)[\'"].*?URI=[\'"]([^\'"]+)[\'"]', r_mst.text, re.IGNORECASE):
                                        aud_url = urljoin(dec_u, a_uri)
                                        try:
                                            r_aud = sess.get(aud_url, headers=stream_headers, timeout=10)
                                            if r_aud.status_code == 200:
                                                a_segs, a_durations = extract_media_playlist_timeline(aud_url, r_aud.text)
                                                if a_segs:
                                                    is_tr = any(k in a_name.lower() for k in ["turk", "türk", "tr", "dub"])
                                                    label = f"Türkçe Dublaj ({a_name})" if is_tr else f"Orijinal / İngilizce ({a_name})"
                                                    audio_tracks.append({
                                                        "name": label,
                                                        "lang": "tur" if is_tr else "eng",
                                                        "sample_segment_url": a_segs[0],
                                                        "segments": a_segs,
                                                        "durations": a_durations,
                                                        "count": len(a_segs),
                                                        "headers": stream_headers
                                                    })
                                        except Exception:
                                            logger.debug("HDFilmcehennemi audio rendition parse failed", exc_info=True)

                                    variants = extract_master_quality_variants(dec_u, r_mst.text)
                                    best_stream = variants[0]["url"] if variants else (
                                        urljoin(dec_u, [l.strip() for l in r_mst.text.splitlines() if l.strip() and not l.startswith("#")][-1])
                                        if any(l.strip() and not l.startswith("#") for l in r_mst.text.splitlines()) else dec_u
                                    )
                                    r_sub = sess.get(best_stream, headers=stream_headers, timeout=10)
                                    if r_sub and r_sub.status_code == 200:
                                        segs = [urljoin(best_stream, l.strip()) for l in r_sub.text.splitlines() if l.strip() and not l.startswith("#")]
                                        if segs:
                                            # Subtitle deduplication
                                            seen_s = set()
                                            dedup_s = []
                                            for s in subs:
                                                u_s = s.get("url") if isinstance(s, dict) else s
                                                if u_s and u_s not in seen_s:
                                                    seen_s.add(u_s)
                                                    dedup_s.append(s)

                                            return ExtractorResult(
                                                success=True,
                                                title=film_title,
                                                video_url=best_stream,
                                                video_headers=stream_headers,
                                                audio_tracks=audio_tracks,
                                                subtitles=dedup_s,
                                                total_segments=len(segs),
                                                direct_file=False,
                                                video_segments=segs,
                                                raw_url=url
                                            )
                            except Exception as ex_m3:
                                logger.debug(f"HDFilmcehennemi HLS resolve note: {ex_m3}")

                        # HLS candidates are valid only after both the master and the
                        # selected media playlist have been fetched successfully.
                        if is_m3u8:
                            continue

                        # Direct stream fallback (yalnızca m3u8 değilse ve geçerli URL ise)
                        return ExtractorResult(
                            success=True,
                            title=film_title,
                            video_url=dec_u,
                            video_headers=stream_headers,
                            audio_tracks=audio_tracks,
                            subtitles=subs,
                            total_segments=0 if is_m3u8 else 1,
                            direct_file=not is_m3u8,
                            raw_url=url
                        )
                except Exception as ce_err:
                    logger.debug(f"Candidate embed error: {ce_err}")

        return None


__all__ = ["HDFilmcehennemiExtractor", "decode_rapidrame_script", "js_atob"]
