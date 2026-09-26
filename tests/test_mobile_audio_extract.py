# -*- coding: utf-8 -*-
"""
B4 regresyon testleri — mobil "Saf Python" ses ayıklayıcısı.

Sentetik bir MPEG-TS akışı üretilip ADTS çerçevelerinin eksiksiz ve doğru
sırayla geri alındığı doğrulanır. Ağ erişimi yoktur.
"""

import os
import sys
import tempfile
import unittest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "android_app"))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from mobile_engine import MobileDownloadController


AUDIO_PID = 0x0101


def make_adts_frame(payload_len, marker):
    """Geçerli bir ADTS başlığı + doldurulmuş gövde üretir."""
    total = 7 + payload_len
    assert 7 <= total <= 8192
    header = bytearray(7)
    header[0] = 0xFF
    header[1] = 0xF1                       # MPEG-4, layer 00, CRC yok
    header[2] = 0x40 | (4 << 2)            # AAC-LC, örnekleme indeksi 4 (44.1 kHz)
    header[3] = ((total >> 11) & 0x03)
    header[4] = (total >> 3) & 0xFF
    header[5] = ((total & 0x07) << 5) | 0x1F
    header[6] = 0xFC
    return bytes(header) + bytes([marker]) * payload_len


def ts_packets(pid, payload, first_is_pes=True):
    """Yükü 188 baytlık TS paketlerine böler."""
    packets = []
    idx = 0
    first = True
    while idx < len(payload):
        header = bytearray(4)
        header[0] = 0x47
        header[1] = (0x40 if first else 0x00) | ((pid >> 8) & 0x1F)
        header[2] = pid & 0xFF
        body = payload[idx:idx + (188 - 4)]
        idx += len(body)
        if len(body) < 184:
            # adaptation field ile doldur: 1 uzunluk baytı + (stuff-1) dolgu baytı
            stuff = 184 - len(body)
            header[3] = 0x30
            af = bytes([stuff - 1]) + b"\xff" * (stuff - 1)
            packets.append(bytes(header) + af + body)
        else:
            header[3] = 0x10
            packets.append(bytes(header) + body)
        first = False
    return b"".join(packets)


def build_pat():
    section = bytearray()
    section += bytes([0x00, 0xB0, 0x0D, 0x00, 0x01, 0xC1, 0x00, 0x00])
    section += bytes([0x00, 0x01, 0xE0 | ((0x1000 >> 8) & 0x1F), 0x1000 & 0xFF])
    section += bytes([0x00, 0x00, 0x00, 0x00])          # CRC yer tutucu
    return ts_packets(0x0000, b"\x00" + bytes(section))


def build_pmt():
    body = bytearray()
    body += bytes([0x0F,                                  # stream_type = AAC/ADTS
                   0xE0 | ((AUDIO_PID >> 8) & 0x1F), AUDIO_PID & 0xFF,
                   0xF0, 0x00])
    section_len = 9 + len(body) + 4
    section = bytearray()
    section += bytes([0x02, 0xB0 | ((section_len >> 8) & 0x0F), section_len & 0xFF])
    section += bytes([0x00, 0x01, 0xC1, 0x00, 0x00])
    section += bytes([0xE0 | ((AUDIO_PID >> 8) & 0x1F), AUDIO_PID & 0xFF])
    section += bytes([0xF0, 0x00])
    section += body
    section += bytes([0x00, 0x00, 0x00, 0x00])
    return ts_packets(0x1000, b"\x00" + bytes(section))


def build_pes(frames):
    payload = b"".join(frames)
    pes = bytearray(b"\x00\x00\x01\xC0")
    length = len(payload) + 3
    pes += bytes([(length >> 8) & 0xFF, length & 0xFF])
    pes += bytes([0x80, 0x00, 0x00])                       # PES başlık, ek alan yok
    pes += payload
    return ts_packets(AUDIO_PID, bytes(pes))


class TestPureAudioExtraction(unittest.TestCase):

    def setUp(self):
        self.ctrl = MobileDownloadController()
        self.tmp = tempfile.mkdtemp(prefix="vdp_b4_")

    def test_adts_frame_length_rejects_false_positives(self):
        """Rastgele 0xFFFx deseni geçerli çerçeve sayılmamalı."""
        valid = make_adts_frame(100, 0xAA)
        self.assertEqual(self.ctrl._adts_frame_length(valid, 0), len(valid))

        # layer alanı sıfır değil -> geçersiz
        bad = bytearray(valid)
        bad[1] |= 0x06
        self.assertEqual(self.ctrl._adts_frame_length(bytes(bad), 0), 0)

        # örnekleme indeksi 13 -> geçersiz
        bad2 = bytearray(valid)
        bad2[2] = (bad2[2] & 0xC3) | (13 << 2)
        self.assertEqual(self.ctrl._adts_frame_length(bytes(bad2), 0), 0)

        self.assertEqual(self.ctrl._adts_frame_length(b"\xff\xf0", 0), 0)

    def test_frames_spanning_packet_boundaries_are_not_lost(self):
        """
        B4'ün asıl hatası: çerçeveler parça sınırında kayboluyordu.
        Her biri TS paketinden büyük 40 çerçeve yazılıp hepsinin geri geldiği doğrulanır.
        """
        frames = [make_adts_frame(500 + i, (i % 250) + 1) for i in range(40)]
        ts = build_pat() + build_pmt() + build_pes(frames)

        src = os.path.join(self.tmp, "input.ts")
        dst = os.path.join(self.tmp, "output.aac")
        with open(src, "wb") as f:
            f.write(ts)

        ok, res = self.ctrl._extract_audio_pure_python(src, dst)
        self.assertTrue(ok, f"Ayıklama başarısız: {res}")

        expected = b"".join(frames)
        actual = open(dst, "rb").read()
        self.assertEqual(len(actual), len(expected),
                         "Bazı ADTS çerçeveleri kayboldu veya fazladan bayt yazıldı (B4)")
        self.assertEqual(actual, expected)

    def test_non_ts_container_reports_failure_instead_of_copying(self):
        """
        MP4 girdisi olduğu gibi kopyalanıp .mp3 adıyla 'başarılı' raporlanmamalı.
        """
        src = os.path.join(self.tmp, "input.mp4")
        dst = os.path.join(self.tmp, "output.aac")
        with open(src, "wb") as f:
            f.write(b"\x00\x00\x00\x20ftypisom" + b"Z" * 40000)

        ok, res = self.ctrl._extract_audio_pure_python(src, dst)
        self.assertFalse(ok, "MP4 girdisinde sessizce 'başarılı' dönülmemeli (B4)")
        self.assertFalse(os.path.exists(dst), "Geçersiz çıktı dosyası bırakıldı (B4)")
        self.assertIn("MPEG-TS", str(res))

    def test_empty_audio_stream_reports_failure(self):
        """Ses çerçevesi olmayan TS akışında başarısızlık dönmeli."""
        ts = build_pat() + build_pmt() + ts_packets(0x0200, b"\xAB" * 4000)
        src = os.path.join(self.tmp, "novideo.ts")
        dst = os.path.join(self.tmp, "out.aac")
        with open(src, "wb") as f:
            f.write(ts)

        ok, res = self.ctrl._extract_audio_pure_python(src, dst)
        self.assertFalse(ok)
        self.assertFalse(os.path.exists(dst))


if __name__ == "__main__":
    unittest.main()
