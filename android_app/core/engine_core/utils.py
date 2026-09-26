# -*- coding: utf-8 -*-
"""
Video Downloader Pro — Engine Utilities and File System Helpers.
"""

import os
import re
import time
import stat
import shutil
import socket
from urllib.parse import urlparse, urlunparse
import requests

try:
    from logger import get_logger
except ImportError:
    try:
        from core.logger import get_logger
    except ImportError:
        import logging
        def get_logger(name):
            return logging.getLogger(name)

logger = get_logger("engine_core.utils")

def _fast_v4_create_conn(address, timeout=socket._GLOBAL_DEFAULT_TIMEOUT,
                         source_address=None, socket_options=None):
    """Compatibility helper that tunes only the connection explicitly made through it.

    The function remains exported for facade compatibility, but importing this module
    no longer replaces urllib3's process-global connection factory.
    """
    import urllib3.util.connection as urllib3_conn

    sock = urllib3_conn.create_connection(
        address,
        timeout=timeout,
        source_address=source_address,
        socket_options=socket_options,
    )
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 2 * 1024 * 1024)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except Exception:
        logger.debug("Soket tamponu ayarlanamadi (SO_RCVBUF/TCP_NODELAY)", exc_info=True)
    return sock



def _remove_readonly(func, path, exc_info):
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        logger.debug("[engine.py:51] _remove_readonly() sessiz istisna yutuldu", exc_info=True)


def cleanup_filesystem_path(target_path, retries=3, delay=0.05):
    """
    Windows ve POSIX dosya kilitlerine karşı dirençli güvenli klasör/dosya temizleme yardımcısı.
    Dosyaların salt-okunur niteliklerini temizler ve kısa gecikmeli tekrar dener.
    """
    if not target_path or not os.path.exists(target_path):
        return True
    for attempt in range(retries):
        try:
            if os.path.isdir(target_path):
                shutil.rmtree(target_path, onerror=_remove_readonly)
            elif os.path.isfile(target_path):
                try:
                    os.chmod(target_path, stat.S_IWRITE)
                except Exception:
                    logger.debug("[engine.py:69] cleanup_filesystem_path() sessiz istisna yutuldu", exc_info=True)
                os.remove(target_path)
            if not os.path.exists(target_path):
                logger.info(f"Geçici yol başarıyla temizlendi: {target_path}")
                return True
        except Exception as e:
            logger.debug(f"Temizleme denemesi {attempt+1}/{retries} başarısız ({target_path}): {e}")
            time.sleep(delay)
    lingering = os.path.exists(target_path)
    if lingering:
        logger.warning(f"Geçici dosya/klasör kilitli kaldı ve silinemedi: {target_path}")
    return not lingering



def fix_mojibake(text: str) -> str:
    """UTF-8 baytlarının Latin-1 / Windows-1252 / ISO-8859 olarak yanlış çözülmesiyle
    oluşan Türkçe karakter bozulmalarını (Ã¶ -> ö, Ã¼ -> ü, Ä± -> ı vb.) düzeltir."""
    if not text or not isinstance(text, str):
        return text
    if any(c in text for c in ("Ã", "Ä", "Å", "Â", "â")):
        try:
            return text.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            try:
                return text.encode("windows-1252").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
    return text


def sanitize_filename(name: str, max_length: int = 100) -> str:
    """
    Dosya adını işletim sistemi (Windows/NTFS & POSIX) ve medya oynatıcılar (Windows Media Player, VLC) için güvenli hale getirir.
    Türkçe karakterleri (ç, ğ, ı, ö, ş, ü, Ç, Ğ, İ, Ö, Ş, Ü) ve boşlukları korur;
    HTML etiketlerini, altyazı otomatik eşleşmesini bozan virgül (,), noktalı virgül (;) ve yasaklı karakterleri temizler.
    """
    if not name:
        return "film"
    s = fix_mojibake(str(name))
    # HTML varlıklarını (örn: &amp;) ve HTML etiketlerini temizle
    s = s.replace("&amp;", "&").replace("&quot;", "").replace("&lt;", "").replace("&gt;", "")
    s = re.sub(r'<[^>]+>', '', s)
    # '|' ve '/' karakterlerini okunaklı tireye dönüştür
    s = re.sub(r'\s*[|/]\s*', ' - ', s)
    # Virgül ve noktalı virgülleri boşluğa çevir (Windows Media Player altyazı eşleşmesini garanti eder)
    s = re.sub(r'[,;]', ' ', s)
    # Yasaklı işletim sistemi karakterlerini temizle: \ * ? : " < > | ve kontrol karakterleri
    cleaned = re.sub(r'[\\*?:"<>|\x00-\x1f]', '_', s)
    # Birden fazla alt çizgiyi veya boşluğu sadeleştir
    cleaned = re.sub(r'_+', '_', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip("._ -")
    if not cleaned:
        return "film"
    # Windows ayrılmış dosya adları kontrolü (CON, PRN, AUX, NUL, COM1-9, LPT1-9)
    stem = os.path.splitext(cleaned)[0].upper()
    if stem in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        cleaned = f"_{cleaned}"
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length].rstrip("._ -")
    return cleaned


def format_human_duration(seconds: float) -> str:
    """Saniyeyi kullanıcı dostu 'X dk Y sn' veya 'Z sn' formatına dönüştürür."""
    if seconds is None or seconds < 0:
        return ""
    seconds = int(round(seconds))
    if seconds < 60:
        return f"{seconds} sn"
    mins = seconds // 60
    secs = seconds % 60
    if mins < 60:
        return f"{mins} dk {secs} sn" if secs > 0 else f"{mins} dk"
    hours = mins // 60
    rem_mins = mins % 60
    return f"{hours} sa {rem_mins} dk" if rem_mins > 0 else f"{hours} sa"


def format_human_filesize(size_bytes: int) -> str:
    """Bayt miktarını kullanıcı dostu 'MB' veya 'GB' formatına dönüştürür."""
    if size_bytes is None or size_bytes < 0:
        return ""
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"




def parse_curl_command(curl_str):
    """
    Tarayıcıdan kopyalanan cURL (bash, Windows cmd, PowerShell vb.) komutunu ayrıştırır.
    """
    raw = curl_str.strip()
    cleaned = re.sub(r'\^\s*\r?\n', ' ', raw)
    cleaned = re.sub(r'\\\s*\r?\n', ' ', cleaned)

    url = ""
    url_flag_match = re.search(r'--url\s+[\^"\']*(https?://[^\s"\'\^]+)[\^"\']*', cleaned, re.IGNORECASE)
    if url_flag_match:
        url = url_flag_match.group(1).strip('^"\'')
    else:
        all_urls = re.findall(r'(?:^|[\s"\'\^])(https?://[^\s"\'\^\\]+)', cleaned)
        for u in all_urls:
            u_clean = u.strip('^"\'')
            idx = cleaned.find(u)
            preceding = cleaned[max(0, idx-25):idx].lower()
            if "referer" not in preceding and "origin" not in preceding:
                url = u_clean
                break
        if not url and all_urls:
            url = all_urls[0].strip('^"\'')

    headers = {}
    chunks = re.split(r'\s+(?:-H|--header)\s+', cleaned)
    if len(chunks) > 1:
        for chunk in chunks[1:]:
            chunk_match = re.match(r'^(.*?)(?=\s+-[a-zA-Z]|\s+--[a-zA-Z]|$)', chunk, re.DOTALL)
            header_raw = chunk_match.group(1).strip() if chunk_match else chunk.strip()

            h_clean = re.sub(r'^[\^"\'\\]+', '', header_raw)
            h_clean = re.sub(r'[\^"\'\\]+$', '', h_clean)
            h_clean = h_clean.replace('^\\^"', '"').replace('^"', '"').replace('\\"', '"').replace('^', '')

            if ":" in h_clean:
                key, val = h_clean.split(":", 1)
                k_clean = key.strip().strip('"\'')
                v_clean = val.strip().strip('^"\'')
                if k_clean and v_clean:
                    headers[k_clean] = v_clean

    cookie_match = re.search(r'(?:-b|--cookie)\s+[\^"\']*(.*?)[\^"\']*(?=\s+-[a-zA-Z]|\s*$)', cleaned)
    if cookie_match:
        c_raw = cookie_match.group(1).strip().replace('^\\^"', '"').replace('^"', '"').replace('^', '').strip('^"\'')
        if c_raw:
            headers["Cookie"] = c_raw

    return url, headers


def parse_segment_url(sample_url):
    """
    Örnek segment URL'sinden taban prefix, sayı padding'i, uzantı, query string ve başlangıç indeksini ayrıştırır.
    """
    url_cleaned = sample_url.strip()
    parsed = urlparse(url_cleaned)
    path = parsed.path
    query_fragment = ""
    if parsed.query:
        query_fragment += f"?{parsed.query}"
    if parsed.fragment:
        query_fragment += f"#{parsed.fragment}"

    match = re.search(r'^(.*?)(\d+)(\.[a-zA-Z0-9]+)$', path)
    if not match:
        match_alt = re.search(r'^(.*?)(\d+)(.*)$', path)
        if not match_alt:
            raise ValueError("Geçersiz URL formatı. Segment numarası tespit edilemedi.")
        path_prefix = match_alt.group(1)
        digits = match_alt.group(2)
        ext = match_alt.group(3)
    else:
        path_prefix = match.group(1)
        digits = match.group(2)
        ext = match.group(3)

    sample_index = int(digits)
    padding = len(digits)
    base_prefix = urlunparse((parsed.scheme, parsed.netloc, path_prefix, '', '', ''))

    return base_prefix, padding, ext, query_fragment, sample_index


def build_segment_url(prefix, index, padding, ext, query_fragment=""):
    seg_num_str = str(index).zfill(padding)
    return f"{prefix}{seg_num_str}{ext}{query_fragment}"


def probe_url(url, headers, timeout=4, session=None):
    """
    Segmentin var olup olmadigini govdeyi indirmeden dogrular.

    HEAD desteklenmiyorsa `Range: bytes=0-0` ile akis modunda tek bayt istenir ve
    yanit her durumda kapatilarak baglanti havuzuna geri verilir.
    """
    req_client = session if session is not None else requests
    try:
        res = req_client.head(url, headers=headers, timeout=timeout, allow_redirects=True)
        if res.status_code == 200:
            return True, 200, None
        # 403/405/501: sunucu HEAD desteklemiyor olabilir, Range GET ile dogrula
        if res.status_code not in (403, 405, 501):
            return False, res.status_code, f"HTTP {res.status_code}"
    except Exception:
        logger.debug("probe_url(): HEAD basarisiz, Range GET'e geciliyor", exc_info=True)

    range_headers = dict(headers or {})
    range_headers["Range"] = "bytes=0-0"
    res = None
    try:
        res = req_client.get(url, headers=range_headers, timeout=timeout,
                             allow_redirects=True, stream=True)
        if res.status_code in (200, 206):
            return True, res.status_code, None
        return False, res.status_code, f"HTTP {res.status_code}"
    except Exception as e:
        return False, 0, f"Bağlantı Hatası: {e}"
    finally:
        if res is not None:
            try:
                res.close()
            except Exception:
                logger.debug("probe_url(): yanit kapatilamadi", exc_info=True)


def _close_owned(session_obj, owns):
    """Yalnizca bu fonksiyonun actigi oturumu kapatir."""
    if owns and session_obj is not None:
        try:
            session_obj.close()
        except Exception:
            logger.debug("_close_owned(): oturum kapatilamadi", exc_info=True)



def is_valid_segment_file(path):
    """Segment dosyasının diskte mevcut ve geçerli medya verisi içerdiğini doğrular.
    MPEG-TS süreksizlik ve PAT/PMT paketleri (188 bayt, 376 bayt vb.) 512 bayttan küçük
    olabilir. Boş dosyaları, HTML hata sayfalarını, M3U8 listelerini ve
    son paketi eksik/kesik kalmış TS segmentlerini eler."""
    if not (path and os.path.exists(path)):
        return False
    try:
        sz = os.path.getsize(path)
        if sz <= 0:
            return False
        with open(path, "rb") as f:
            head = f.read(188)
            if not head:
                return False
            # HTML hata sayfası veya M3U8 listesi kontrolü
            if head.startswith(b"<!DOCTYPE") or head.startswith(b"<html") or head.startswith(b"<HTML"):
                return False
            if head.startswith(b"#EXTM3U") or head.startswith(b"#EXT-X"):
                return False
            if b"<html" in head.lower() or b"<body" in head.lower():
                return False
            stripped_head = head.lstrip().lower()
            if stripped_head.startswith((b"{", b"[", b"<?xml", b"<error")):
                return False
            if b"access denied" in stripped_head or b"cloudflare ray id" in stripped_head:
                return False

            # MPEG-TS doğrulama: İlk bayt 0x47 ve dosya sonundaki son 188 baytlık paket de 0x47 ile başlamalıdır.
            if head[0] == 0x47:
                if sz > 512:
                    f.seek(sz - 188)
                    tail = f.read(188)
                    if not tail or tail[0] != 0x47:
                        return False
                return True

            # MP4 / AAC vb. diğer akışlar veya test verileri için geçerli kabul et
            return True
    except Exception:
        return False



__all__ = [
    "_remove_readonly",
    "cleanup_filesystem_path",
    "fix_mojibake",
    "sanitize_filename",
    "format_human_duration",
    "format_human_filesize",
    "parse_curl_command",
    "parse_segment_url",
    "build_segment_url",
    "probe_url",
    "_close_owned",
    "is_valid_segment_file",
    "_fast_v4_create_conn",
]
