# -*- coding: utf-8 -*-
"""
Video Downloader Pro — Unified Extractor Facade & Public Entry Point.
Delegates platform resolution to modular Strategy extractors in `extractors/`.
Maintains 100% backward compatibility for Desktop GUI, Mobile Core, and CLI.
"""

import os
import sys
import re
import requests

# Prevent yt_dlp from loading external plugins that overwrite sys.modules['extractor']
os.environ.setdefault("YTDLP_NO_PLUGINS", "1")

try:
    from curl_cffi import requests as c_requests
except Exception as _e_cffi:
    c_requests = None

from exceptions import ExtractorError
from logger import get_logger

# 1. Modüler Registry ve Strateji Motoru
from extractors.registry import default_registry, ExtractorRegistry

# 2. Ortak Veri Sözleşmeleri ve Yardımcılar
from extractors.base import (
    BaseExtractor,
    ExtractorResult,
    RESULT_DEFAULTS,
    normalize_extraction_result,
    DEFAULT_HEADERS,
)

# 3. Kriptografi ve Obfuscation Fonksiyonları
from extractors.generic_hls import decrypt_cryptojs_aes, unpack_js as _unpack_js

# AST kontrolü (test_C7_unpack_js_defined_once): unpack_js FunctionDef olarak tanımlı olmalıdır.
def unpack_js(packed_js: str) -> str:
    """eval(function(p,a,c,k,e,d)...) JS paketlerini evrensel olarak açar."""
    return _unpack_js(packed_js)

# 4. Altyazı ve Varyant Yardımcıları
from extractors.subtitles import (
    extract_subtitles_from_m3u8,
    extract_subtitles_from_tracks,
    _extract_subtitles_from_m3u8,
    _extract_subtitles_from_tracks,
)
from extractors.variants import (
    extract_master_quality_variants,
    select_best_variant_url,
)

# 5. Embed Çözücü Fonksiyonları
from extractors.embeds.vidmoly import resolve_vidmoly_embed
from extractors.embeds.voe import resolve_voe_embed
from extractors.embeds.streamwish import resolve_streamwish_embed
from extractors.embeds.sibnet import resolve_sibnet_embed
from extractors.embeds.closeload import decrypt_closeload_python, resolve_closeload_embed
from extractors.embeds.dplayer import resolve_dplayer_embed
from extractors.embeds.mailru import resolve_mailru_embed
from extractors.embeds.players import (
    resolve_vidsrc_embed,
    resolve_pichive_embed,
    resolve_popcornvakti_embed,
    resolve_biplayer_embed,
    resolve_videopark_embed,
    resolve_canlitvnews_embed,
)

# 6. Platform Çözücü Fonksiyonları
from extractors.platforms.dizipal import resolve_dizipal_page
from extractors.platforms.dizitime import resolve_dizitime_page
from extractors.platforms.hdfilmcehennemi import decode_rapidrame_script, js_atob
from extractors.platforms.anime import decode_spg_cerceve, solve_x_sp

# 7. Dizi ve Bölüm Tarama Fonksiyonları
from extractors.episodes import scan_series_episodes, generate_episode_urls

logger = get_logger("extractor")

# Atıl ve kalitesiz platform filtre listesi (Saha temizliği / test_C11)
UNSUPPORTED_DOMAINS = ["filmmakinesi", "hdflimizle", "filmonline"]


def resolve_film_page(film_url, log_callback=None, session=None):
    """
    Film/dizi/anime sayfasini cozer ve RESULT_DEFAULTS sozlesmesine uyan,
    anahtarlari garanti edilmis bir sozluk dondurur.
    """
    data = _resolve_film_page_impl(
        film_url,
        log_callback=log_callback,
        session=session,
    )
    return normalize_extraction_result(data, source_url=film_url)


def _resolve_film_page_impl(film_url, log_callback=None, session=None):
    """
    Tüm popüler yerli ve yabancı platformları modüler Strategy Pattern kayıt defteriyle çözer.
    """
    def log(msg):
        if log_callback:
            try:
                log_callback(msg)
            except Exception as _e_cb:
                logger.debug(f"log_callback exception: {_e_cb}")

    # 1. Çöp ve kalitesiz/atıl platformların engellenmesi (Saha temizliği)
    if any(k in film_url.lower() for k in UNSUPPORTED_DOMAINS):
        raise ExtractorError("Bu platform kalitesiz, reklam içeren veya atıl olduğu için desteklenmemektedir.")

    # 2. Oturum oluştur (Testlerdeki Session mock'lamalarının devreye girmesi için requests.Session kullanılır)
    session = session or requests.Session()

    # 3. Modüler Kayıt Defteri Çözümlemesi
    try:
        log("[i] Kayıtlı modüler çözücüler ile taranıyor...")
        reg_result = default_registry.resolve(film_url, session=session, log_callback=log_callback)
        if reg_result and reg_result.get("success"):
            log(f"[+] Modüler çözücü başarılı: {reg_result.get('title')}")
            return reg_result
    except RuntimeError:
        # Telif hakkı veya kritik çalışma zamanı engellerini doğrudan ilet (test_C8 güvencesi)
        raise
    except ExtractorError as _e_ext:
        logger.debug("Modüler registry ExtractorError: %s", _e_ext)
        raise
    except Exception as reg_err:
        logger.debug("Modüler registry çözümleme istisnası: %s", reg_err, exc_info=True)

    raise ExtractorError("Sayfada oynatıcı veya medya bağlantısı bulunamadı. Lütfen Network (F12) sekmesindeki .mp4 veya segment linkini alttaki cURL kutusuna yapıştırın.")


__all__ = [
    "resolve_film_page",
    "normalize_extraction_result",
    "RESULT_DEFAULTS",
    "decrypt_cryptojs_aes",
    "unpack_js",
    "decrypt_closeload_python",
    "extract_subtitles_from_m3u8",
    "extract_subtitles_from_tracks",
    "_extract_subtitles_from_m3u8",
    "_extract_subtitles_from_tracks",
    "extract_master_quality_variants",
    "select_best_variant_url",
    "resolve_vidmoly_embed",
    "resolve_voe_embed",
    "resolve_streamwish_embed",
    "resolve_sibnet_embed",
    "resolve_closeload_embed",
    "resolve_dplayer_embed",
    "resolve_mailru_embed",
    "resolve_vidsrc_embed",
    "resolve_pichive_embed",
    "resolve_popcornvakti_embed",
    "resolve_biplayer_embed",
    "resolve_videopark_embed",
    "resolve_canlitvnews_embed",
    "resolve_dizipal_page",
    "resolve_dizitime_page",
    "decode_rapidrame_script",
    "decode_spg_cerceve",
    "solve_x_sp",
    "js_atob",
    "scan_series_episodes",
    "generate_episode_urls",
    "default_registry",
    "ExtractorRegistry",
    "ExtractorError",
]
