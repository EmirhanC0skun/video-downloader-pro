# -*- coding: utf-8 -*-
"""
Generic HLS & JavaScript Obfuscation Extractor.
Handles JWPlayer, eval-packed JavaScript, and AES-256 decrypted streams.
"""

import re
import base64
import hashlib
from logger import get_logger

logger = get_logger("extractors.generic_hls")

try:
    from Crypto.Cipher import AES
except ImportError:
    AES = None


def decrypt_cryptojs_aes(encrypted_b64: str, passphrase: str) -> str:
    """CryptoJS.AES.decrypt(ciphertext, passphrase) Python equivalent."""
    if not encrypted_b64 or not passphrase:
        return ""
    try:
        encrypted = base64.b64decode(encrypted_b64)
        if not encrypted.startswith(b"Salted__"):
            return ""
    except Exception:
        return ""

    if AES is None:
        logger.warning("PyCryptodome not installed; cannot decrypt AES-256.")
        return ""

    try:
        salt = encrypted[8:16]
        ciphertext = encrypted[16:]
        passphrase_bytes = passphrase.encode('utf-8') if isinstance(passphrase, str) else passphrase

        key_iv = b""
        prev = b""
        while len(key_iv) < (32 + 16):
            prev = hashlib.md5(prev + passphrase_bytes + salt).digest()
            key_iv += prev

        key = key_iv[:32]
        iv = key_iv[32:48]

        cipher = AES.new(key, AES.MODE_CBC, iv)
        decrypted = cipher.decrypt(ciphertext)
        pad_len = decrypted[-1]
        return decrypted[:-pad_len].decode('utf-8', errors='ignore')
    except Exception as ex:
        logger.debug(f"AES Decryption error: {ex}")
        return ""


def unpack_js(packed_js: str) -> str:
    """Unpacks eval(function(p,a,c,k,e,d)...) JS packages."""
    pattern = r"\}\s*\(\s*['\"](.*?)['\"]\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*['\"](.*?)['\"]\s*\.split\(\s*['\"]\|['\"]\s*\)"
    match = re.search(pattern, packed_js)
    if not match:
        return packed_js

    payload, radix, count, symtab = match.groups()
    radix = int(radix)
    symtab = symtab.split('|')

    def unbase(val, r):
        digits = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
        res = 0
        for ch in val:
            res = res * r + digits.index(ch)
        return res

    def lookup(match_obj):
        word = match_obj.group(0)
        try:
            idx = unbase(word, radix)
            if idx < len(symtab) and symtab[idx]:
                return symtab[idx]
            return word
        except Exception:
            return word

    return re.sub(r'\b\w+\b', lookup, payload)
