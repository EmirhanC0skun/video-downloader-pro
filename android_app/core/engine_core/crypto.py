# -*- coding: utf-8 -*-
"""
Video Downloader Pro — HLS Segment Cryptography.
Handles AES-128-CBC segment decryption, PKCS#7 unpadding, and IV derivation.
"""

try:
    from Crypto.Cipher import AES
except ImportError:
    try:
        from Cryptodome.Cipher import AES
    except ImportError:
        AES = None

try:
    from logger import get_logger
except ImportError:
    try:
        from core.logger import get_logger
    except ImportError:
        import logging
        def get_logger(name):
            return logging.getLogger(name)

logger = get_logger("engine_core.crypto")

def derive_hls_iv(segment_index):
    """
    HLS (RFC 8216 §5.2): EXT-X-KEY satirinda IV verilmediginde IV, segmentin
    medya sira numarasinin 128-bit big-endian gosterimidir.
    """
    try:
        return int(segment_index).to_bytes(16, "big")
    except Exception:
        return bytes(16)


def decrypt_hls_segment(data, key, iv, segment_index=None):
    """
    AES-128-CBC sifreli bir HLS segmentini cozer ve PKCS#7 dolgusunu kaldirir.

    Basarisizlikta None dondurur; cagiran taraf sifreli veriyi diske YAZMAMALIDIR.
    """
    if AES is None:
        logger.warning("pycryptodome kurulu degil; AES-128 sifreli segment cozulemiyor.")
        return None
    if not key or not data:
        return None
    if not iv:
        if segment_index is None:
            return None
        iv = derive_hls_iv(segment_index)
    if len(data) % 16 != 0:
        logger.debug("AES segment uzunlugu 16'nin kati degil (%d bayt); cozme atlandi.", len(data))
        return None
    try:
        plain = AES.new(key, AES.MODE_CBC, iv).decrypt(data)
    except Exception as ex:
        logger.warning("AES-128 segment cozme hatasi: %s", ex)
        return None
    if not plain:
        return None
    pad_len = plain[-1]
    if 1 <= pad_len <= 16 and plain[-pad_len:] == bytes([pad_len]) * pad_len:
        plain = plain[:-pad_len]
    return plain




__all__ = ["derive_hls_iv", "decrypt_hls_segment", "AES"]
