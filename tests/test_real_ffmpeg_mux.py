# -*- coding: utf-8 -*-
"""
Integration test for real, physical FFmpeg multiplexing and MP4 container validation.
Runs with zero mocks: generates synthetic video (testsrc) and audio (sine), executes
mux_video_and_audio, and asserts valid MP4 box structure (ftyp, moov/mdat) on disk.
"""

import os
import sys
import shutil
import tempfile
import subprocess
import unittest

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine_core.ffmpeg import get_ffmpeg_path, FFmpegMixin, write_concat_file


class TestRealFFmpegMux(unittest.TestCase):
    """Gerçek subprocess tabanlı FFmpeg muxing ve MP4 çıktı bütünlüğü testi."""

    def setUp(self):
        self.ffmpeg_bin = get_ffmpeg_path()
        if not self.ffmpeg_bin or not os.path.exists(self.ffmpeg_bin):
            raise unittest.SkipTest("FFmpeg ikilisi bulunamadı; gerçek muxing testi atlandı.")
        self.test_dir = tempfile.mkdtemp(prefix="vdp_real_mux_")

    def tearDown(self):
        if hasattr(self, "test_dir") and os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_real_ffmpeg_mux_and_mp4_container_validation(self):
        """1 saniyelik sentetik video ve ses akışlarını FFmpeg ile gerçek MP4 dosyasına birleştirir ve doğrular."""
        v_path = os.path.join(self.test_dir, "synth_video.ts")
        a_path = os.path.join(self.test_dir, "synth_audio.ts")

        # 1. Sentetik video akışı üret (1 saniye H.264 TS)
        res_v = subprocess.run([
            self.ffmpeg_bin, "-y",
            "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=30",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            v_path
        ], capture_output=True, text=True, timeout=30)
        self.assertEqual(res_v.returncode, 0, f"Sentetik video oluşturulamadı: {res_v.stderr}")
        self.assertTrue(os.path.exists(v_path))
        self.assertGreater(os.path.getsize(v_path), 0)

        # 2. Sentetik ses akışı üret (1 saniye 1000Hz sinüs AAC TS)
        res_a = subprocess.run([
            self.ffmpeg_bin, "-y",
            "-f", "lavfi", "-i", "sine=frequency=1000:duration=1",
            "-c:a", "aac",
            a_path
        ], capture_output=True, text=True, timeout=30)
        self.assertEqual(res_a.returncode, 0, f"Sentetik ses oluşturulamadı: {res_a.stderr}")
        self.assertTrue(os.path.exists(a_path))
        self.assertGreater(os.path.getsize(a_path), 0)

        # 3. Gerçek mux_video_and_audio çağrısı (Mock'suz)
        out_mp4 = os.path.join(self.test_dir, "output.mp4")
        mixin = FFmpegMixin()
        logs = []
        success = mixin.mux_video_and_audio(
            video_concat_path=v_path,
            audio_concat_path=a_path,
            output_filepath=out_mp4,
            log_callback=logs.append
        )

        # 4. Dosya varlığı ve boyut kontrolleri
        self.assertTrue(success, "mux_video_and_audio başarıyla True dönmelidir")
        self.assertTrue(os.path.exists(out_mp4), "Nihai MP4 dosyası diskte oluşturulmalıdır")
        self.assertGreater(os.path.getsize(out_mp4), 1024, "Nihai MP4 dosyası anlamlı bir boyuta (>1KB) sahip olmalıdır")

        # 5. MP4 Konteyner atom/box başlık doğrulaması
        with open(out_mp4, "rb") as f_mp4:
            header = f_mp4.read(1024)
            self.assertIn(b"ftyp", header, "MP4 konteyneri ftyp atomu içermelidir")
            f_mp4.seek(0)
            body = f_mp4.read()
            self.assertTrue(b"moov" in body or b"mdat" in body, "MP4 konteyneri moov veya mdat atomu içermelidir")

        # 6. FFmpeg decode doğrulaması (Null muxer ile stream oynatılabilirlik testi)
        probe_res = subprocess.run([
            self.ffmpeg_bin, "-v", "error",
            "-i", out_mp4,
            "-f", "null", "-"
        ], capture_output=True, text=True, timeout=30)
        self.assertEqual(probe_res.returncode, 0, f"Üretilen MP4 hatasız çözülebilir olmalıdır: {probe_res.stderr}")

        # 7. Concat demuxer listesi (.txt) girdi formatıyla da mux doğrulaması
        v_concat = os.path.join(self.test_dir, "concat_video.txt")
        with open(v_concat, "w", encoding="utf-8") as f_cv:
            f_cv.write(f"file '{os.path.abspath(v_path).replace(chr(92), '/')}'\n")

        a_concat = os.path.join(self.test_dir, "concat_audio.txt")
        with open(a_concat, "w", encoding="utf-8") as f_ca:
            f_ca.write(f"file '{os.path.abspath(a_path).replace(chr(92), '/')}'\n")

        out_concat_mp4 = os.path.join(self.test_dir, "output_concat.mp4")
        success_concat = mixin.mux_video_and_audio(
            video_concat_path=v_concat,
            audio_concat_path=a_concat,
            output_filepath=out_concat_mp4,
            log_callback=logs.append
        )
        self.assertTrue(success_concat, "Concat listeli mux_video_and_audio başarıyla True dönmelidir")
        self.assertTrue(os.path.exists(out_concat_mp4))
        self.assertGreater(os.path.getsize(out_concat_mp4), 1024)
        with open(out_concat_mp4, "rb") as f_cmp4:
            self.assertIn(b"ftyp", f_cmp4.read(1024), "Concat çıktısı geçerli ftyp atomu içermelidir")

    def test_real_multi_audio_concat_handles_space_and_apostrophe_paths(self):
        """Üretim concat yazıcısını Windows özel yollarında gerçek FFmpeg ile doğrular."""
        special_dir = os.path.join(self.test_dir, "O'Brien medya alanı")
        os.makedirs(special_dir, exist_ok=True)
        video_path = os.path.join(special_dir, "görüntü parçası.ts")
        turkish_audio_path = os.path.join(special_dir, "Türkçe ses parçası.ts")
        english_audio_path = os.path.join(special_dir, "English audio part.ts")

        video_result = subprocess.run([
            self.ffmpeg_bin, "-y",
            "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=30",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            video_path,
        ], capture_output=True, text=True, timeout=30)
        self.assertEqual(video_result.returncode, 0, video_result.stderr)

        for frequency, audio_path in (
            (700, turkish_audio_path),
            (1100, english_audio_path),
        ):
            audio_result = subprocess.run([
                self.ffmpeg_bin, "-y",
                "-f", "lavfi", "-i", f"sine=frequency={frequency}:duration=1",
                "-c:a", "aac",
                audio_path,
            ], capture_output=True, text=True, timeout=30)
            self.assertEqual(audio_result.returncode, 0, audio_result.stderr)

        video_concat = os.path.join(special_dir, "concat görüntü.txt")
        turkish_concat = os.path.join(special_dir, "concat Türkçe.txt")
        english_concat = os.path.join(special_dir, "concat English.txt")
        write_concat_file(video_concat, [video_path])
        write_concat_file(turkish_concat, [turkish_audio_path])
        write_concat_file(english_concat, [english_audio_path])

        output_path = os.path.join(special_dir, "çift sesli O'Brien çıktı.mp4")
        success = FFmpegMixin().mux_multi_audio_and_video(
            v_concat_path=video_concat,
            audio_concats=[
                (turkish_concat, "Türkçe", "tur"),
                (english_concat, "English", "eng"),
            ],
            output_filepath=output_path,
        )

        self.assertTrue(success)
        self.assertGreater(os.path.getsize(output_path), 1024)
        for stream_selector in ("0:v:0", "0:a:0", "0:a:1"):
            decode_result = subprocess.run([
                self.ffmpeg_bin, "-v", "error",
                "-i", output_path,
                "-map", stream_selector,
                "-f", "null", "-",
            ], capture_output=True, text=True, timeout=30)
            self.assertEqual(decode_result.returncode, 0, decode_result.stderr)


if __name__ == "__main__":
    unittest.main()
