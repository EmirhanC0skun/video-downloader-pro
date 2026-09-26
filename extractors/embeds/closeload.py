# -*- coding: utf-8 -*-
"""
Video Downloader Pro — CloseLoad Embed Extractor.
Resolves closeload.com / closeload.top obfuscated streams using Python/Node interpreter.
"""

import re
import base64
import subprocess
from urllib.parse import urljoin
import requests

try:
    from curl_cffi import requests as c_requests
except Exception:
    c_requests = None

from extractors.base import BaseExtractor, ExtractorResult
from extractors.generic_hls import unpack_js
from extractors.subtitles import extract_subtitles_from_tracks
from logger import get_logger

logger = get_logger("extractors.embeds.closeload")


def decrypt_closeload_python(func_code, call_code):
    """CloseLoad fonksiyonunu saf Python ile satır satır yorumlar."""
    try:
        raw_parts_m = re.search(r'\(\s*(\[[^\]]+\])\s*\)', call_code)
        if not raw_parts_m:
            return None
        parts = re.findall(r'["\']([^"\']+)["\']', raw_parts_m.group(1))
        if not parts:
            return None
        result = ''.join(parts).replace(r'\/', '/')

        for line in func_code.splitlines():
            line = line.strip()
            if 'reverse().join' in line:
                result = result[::-1]
            elif 'atob(result)' in line:
                try:
                    result = base64.b64decode(result).decode('latin1')
                except Exception as e:
                    logger.debug(f"decrypt_closeload_python atob error: {e}")
            elif 'base +' in line:
                m_shift = re.search(r'base\s*\+\s*(\d+)', line)
                if m_shift:
                    shift = int(m_shift.group(1))
                    r = []
                    for c in result:
                        if 'a' <= c <= 'z':
                            r.append(chr((ord(c) - 97 + shift) % 26 + 97))
                        elif 'A' <= c <= 'Z':
                            r.append(chr((ord(c) - 65 + shift) % 26 + 65))
                        else:
                            r.append(c)
                    result = ''.join(r)

        # XOR döngüsü
        acc_m = re.search(r'var\s+acc\s*=\s*(\d+)', func_code)
        step_m = re.search(r'acc\s*=\s*\(\s*acc\s*\+\s*(\d+)\s*\)', func_code)
        if acc_m and step_m:
            acc = int(acc_m.group(1))
            step = int(step_m.group(1))
            unmix = []
            for c in result:
                b = ord(c)
                acc = (acc + step) % 256
                plain = b ^ acc
                acc = (acc + b) % 256
                unmix.append(chr(plain))
            result = ''.join(unmix)
        return result.strip()
    except Exception as e:
        logger.debug(f"decrypt_closeload_python error: {e}")
        return None


def resolve_closeload_embed(embed_url, session=None, headers=None):
    """CloseLoad (closeload.com, closeload.top) video akışını çözer."""
    session = session or requests.Session()
    req_headers = dict(headers or {})
    req_headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": embed_url
    })
    try:
        text = ""
        if c_requests:
            try:
                r_c = c_requests.get(embed_url, headers=req_headers, impersonate="chrome124", timeout=12)
                if r_c.status_code == 200:
                    text = r_c.text
            except Exception as e:
                logger.debug(f"closeload c_requests error: {e}")
        if not text:
            r = session.get(embed_url, headers=req_headers, timeout=12)
            if r.status_code == 200:
                text = r.text

        if text:
            # Dinamik CloseLoad fonksiyonu: function dc_xxx(...) { ... }
            func_m = re.search(r'function\s+(dc_[a-zA-Z0-9_]+)\s*\([^)]*\)\s*\{.*?\n\}', text, re.DOTALL)
            if func_m:
                func_name = func_m.group(1)
                call_m = re.search(re.escape(func_name) + r'\s*\(\s*\[[^\]]+\]\s*\)', text)
                if call_m:
                    func_str = func_m.group(0)
                    call_str = call_m.group(0)
                    # Yöntem A: Saf Python yorumlayıcı (Hızlı, güvenli, bağımsız)
                    dec_url = decrypt_closeload_python(func_str, call_str)
                    if dec_url and dec_url.startswith("http"):
                        subs = extract_subtitles_from_tracks(text, embed_url)
                        return {"video_url": dec_url, "headers": {"User-Agent": req_headers["User-Agent"], "Referer": embed_url}, "subtitles": subs}

                    # Yöntem B: Node.js ile çalıştırma (Yedek)
                    try:
                        js_code = f"function atob(a) {{ return Buffer.from(a, 'base64').toString('binary'); }}\n{func_str}\nconsole.log({call_str});"
                        res_node = subprocess.run(["node", "-e", js_code], capture_output=True, text=True, timeout=4)
                        if res_node.returncode == 0:
                            dec_url = res_node.stdout.strip()
                            if dec_url.startswith("http"):
                                subs = extract_subtitles_from_tracks(text, embed_url)
                                return {"video_url": dec_url, "headers": {"User-Agent": req_headers["User-Agent"], "Referer": embed_url}, "subtitles": subs}
                    except Exception as e:
                        logger.debug(f"closeload node execution error: {e}")

            if "eval(function(p,a,c,k,e,d" in text:
                text += "\n" + unpack_js(text)

            m3u8_m = re.findall(r'["\'](https?://[^"\']+\.m3u8[^"\']*)["\']', text)
            if m3u8_m:
                subs = extract_subtitles_from_tracks(text, embed_url)
                return {"video_url": m3u8_m[0], "headers": {"User-Agent": req_headers["User-Agent"], "Referer": embed_url}, "subtitles": subs}
            b64_m = re.findall(r'atob\(["\']([a-zA-Z0-9+/=]+)["\']\)', text)
            for b in b64_m:
                try:
                    dec = base64.b64decode(b).decode('utf-8', errors='ignore')
                    if ".m3u8" in dec or ".mp4" in dec:
                        final_u = dec if dec.startswith("http") else urljoin(embed_url, dec)
                        subs = extract_subtitles_from_tracks(text, embed_url)
                        return {"video_url": final_u, "headers": {"User-Agent": req_headers["User-Agent"], "Referer": embed_url}, "subtitles": subs}
                except Exception as e:
                    logger.debug(f"closeload atob decode error: {e}")
    except Exception as e:
        logger.debug(f"resolve_closeload_embed error: {e}")
    return None


class CloseloadExtractor(BaseExtractor):
    """Strategy extractor for CloseLoad embeds."""

    @property
    def name(self) -> str:
        return "CloseLoad Embed"

    def can_handle(self, url: str) -> bool:
        return "closeload" in url.lower()

    def extract(self, url: str, session=None, log_callback=None) -> ExtractorResult:
        self.log(f"[+] CloseLoad embed çözülüyor: {url}", log_callback)
        data = resolve_closeload_embed(url, session=session)
        if not data or not data.get("video_url"):
            return None

        video_url = data["video_url"]
        headers = data.get("headers", {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": url
        })
        return ExtractorResult(
            success=True,
            title="CloseLoad Video",
            video_url=video_url,
            video_headers=headers,
            audio_tracks=[],
            subtitles=data.get("subtitles", []),
            total_segments=0,
            direct_file=not (".m3u8" in video_url),
            raw_url=url
        )


__all__ = ["CloseloadExtractor", "decrypt_closeload_python", "resolve_closeload_embed"]
