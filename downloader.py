# -*- coding: utf-8 -*-
"""HLS / segment akisi komut satiri indiricisi."""

import os
import sys
import argparse
from tqdm import tqdm
from engine import VideoDownloadEngine


def main_cli():
    # Dogrudan `python downloader.py` ile calistirildiginda main.py'nin yaptigi
    # stdout yeniden yapilandirmasi devreye girmez; burada da guvenceye al.
    for _s in (sys.stdout, sys.stderr):
        if _s is not None and hasattr(_s, "reconfigure"):
            try:
                _s.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

    parser = argparse.ArgumentParser(description="HLS / JPEG Segment Video İndirici & Birleştirici")
    parser.add_argument("--url", "-u", type=str, help="Örnek segment URL'si (Örn: https://.../video/seg_025.jpg)")
    parser.add_argument("--output", "-o", type=str, default="video.mp4", help="Kaydedilecek çıktı dosyası (Varsayılan: video.mp4)")
    parser.add_argument("--referer", "-r", type=str, default=None, help="Referer / Site URL'si")
    parser.add_argument("--threads", "-t", type=int, default=8, help="Eşzamanlı iş parçacığı sayısı (Varsayılan: 8)")
    parser.add_argument("--start", "-s", type=int, default=None, help="Başlangıç segment numarası (Örn: 1 veya 0)")
    parser.add_argument("--total", "-n", type=int, default=None, help="Toplam / Bitiş segment sayısı")
    parser.add_argument("--merge", "-m", choices=["auto", "ffmpeg", "binary"], default="auto", help="Birleştirme modu (Varsayılan: auto)")
    parser.add_argument("--keep-temp", action="store_true", help="İndirilen geçici segmentleri silme")

    args = parser.parse_args()

    print("=" * 65)
    print("    ⚡ HLS / JPEG Segment Video İndirici & Birleştirici (CLI)")
    print("=" * 65)

    sample_url = args.url
    if not sample_url:
        sample_url = input("\nÖrnek Segment URL'sini yapıştırın:\n(Örn: https://.../video/seg_025.jpg)\n> ").strip()
        if not sample_url:
            print("[!] Hata: URL boş olamaz.")
            sys.exit(1)

    referer = args.referer
    if not referer and not args.url:
        ref_input = input("\nReferer / Site URL'si (Boş bırakılırsa ana domain kullanılır):\n> ").strip()
        referer = ref_input if ref_input else None

    output_filepath = args.output
    if not args.url and output_filepath == "video.mp4":
        out_input = input("\nKaydedilecek dosya adı (Varsayılan: video.mp4):\n> ").strip()
        if out_input:
            output_filepath = out_input

    if not output_filepath.endswith((".mp4", ".ts", ".mkv")):
        output_filepath += ".mp4"

    thread_count = args.threads
    if not args.url and thread_count == 8:
        th_input = input("\nEşzamanlı indirme sayısı (Varsayılan: 8):\n> ").strip()
        if th_input.isdigit():
            thread_count = int(th_input)

    engine = VideoDownloadEngine()

    pbar = None
    last_completed = 0

    def progress_callback(completed, total, total_bytes, speed_bps):
        nonlocal pbar, last_completed
        if pbar is None and total > 0:
            pbar = tqdm(total=total, desc="İndiriliyor", unit="parça", dynamic_ncols=True)
        if pbar:
            delta = completed - last_completed
            if delta > 0:
                pbar.update(delta)
                last_completed = completed
            speed_mb = speed_bps / (1024 * 1024)
            pbar.set_postfix_str(f"{speed_mb:.2f} MB/s")

    def log_callback(msg):
        if pbar:
            tqdm.write(msg)
        else:
            print(msg)

    print("\n[+] İndirme işlemi başlatılıyor...")
    success, result = engine.run_download(
        sample_url=sample_url,
        output_filepath=output_filepath,
        referer=referer,
        total_segments=args.total,
        start_index=args.start,
        thread_count=thread_count,
        merge_mode=args.merge,
        progress_callback=progress_callback,
        log_callback=log_callback,
        keep_temp=args.keep_temp
    )

    if pbar:
        pbar.close()

    if success:
        print(f"\n[✓] Başarıyla tamamlandı: {os.path.abspath(result)}")
    else:
        print(f"\n[✗] Hata: {result}")
        sys.exit(1)


if __name__ == "__main__":
    main_cli()
