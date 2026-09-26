# -*- coding: utf-8 -*-
"""
Video Downloader Pro — Modular Extractors Package.
"""

from extractors.base import BaseExtractor, ExtractorResult, RESULT_DEFAULTS, normalize_extraction_result
from extractors.registry import ExtractorRegistry, default_registry
from extractors.direct import DirectMediaExtractor
from extractors.generic import GenericMediaExtractor
from extractors.dailymotion import DailymotionExtractor
from extractors.series_film import SeriesFilmExtractor
from extractors.generic_hls import decrypt_cryptojs_aes, unpack_js
from extractors.variants import extract_master_quality_variants, select_best_variant_url
from extractors.universal import UniversalYtDlpExtractor

__all__ = [
    "BaseExtractor",
    "ExtractorResult",
    "RESULT_DEFAULTS",
    "normalize_extraction_result",
    "ExtractorRegistry",
    "default_registry",
    "DirectMediaExtractor",
    "GenericMediaExtractor",
    "DailymotionExtractor",
    "SeriesFilmExtractor",
    "decrypt_cryptojs_aes",
    "unpack_js",
    "extract_master_quality_variants",
    "select_best_variant_url",
    "UniversalYtDlpExtractor"
]

