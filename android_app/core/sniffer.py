# -*- coding: utf-8 -*-
"""
Video Downloader Pro — Sniffer Facade / Adapter.
Asıl paket dinleyici ve varyant yakalayıcı modülü tools/packet_sniffer.py konumuna taşınmiştır.
Geriye dönük API ve test uyumluluğu için temel semboller buradandışa aktarılmaktadır.
"""

import sys
import os

_tools_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools")
if _tools_dir not in sys.path:
    sys.path.insert(0, _tools_dir)

try:
    from tools.packet_sniffer import (
        decrypt_rapidvid_av,
        pick_highest_bandwidth_variant,
        parse_master_m3u8_payload,
        sniff_media_stream,
    )
except ImportError:
    try:
        from packet_sniffer import (
            decrypt_rapidvid_av,
            pick_highest_bandwidth_variant,
            parse_master_m3u8_payload,
            sniff_media_stream,
        )
    except Exception as _err:
        from logger import get_logger
        get_logger("sniffer").debug("packet_sniffer aktarilamadi: %s", _err)


__all__ = [
    "decrypt_rapidvid_av",
    "pick_highest_bandwidth_variant",
    "parse_master_m3u8_payload",
    "sniff_media_stream",
]
