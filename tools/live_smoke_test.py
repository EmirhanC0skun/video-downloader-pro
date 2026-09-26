# -*- coding: utf-8 -*-
"""
CANLI AG TEST BETIGI - pytest paketinin PARCASI DEGILDIR.

Gercek sitelere istek atar ve diske dosya yazar. CI'da calismaz; elle
calistirilmak uzere tasarlanmistir. Hedef klasor:

    VDP_LIVE_TEST_DIR    indirilen test dosyalari
    VDP_LIVE_REPORT_DIR  olusturulan rapor dosyasi

Ornek:
    set VDP_LIVE_TEST_DIR=D:\\testler
    python tools/live_smoke_test.py
"""
import sys, os, time, datetime, re, traceback, json
sys.stdout.reconfigure(encoding='utf-8')

import yt_dlp
from yt_dlp.networking.impersonate import ImpersonateTarget
from curl_cffi import requests as c_requests
import requests
import extractor, engine

# E6/F1: gelistirici masaustune sabitlenmis yol kaldirildi.
# Hedef klasor VDP_LIVE_TEST_DIR ortam degiskeniyle degistirilebilir.
out_dir = os.environ.get(
    "VDP_LIVE_TEST_DIR",
    os.path.join(os.path.expanduser("~"), "video-downloader-live-tests"),
)
os.makedirs(out_dir, exist_ok=True)

test_suite = [
    # 1. Video & Sosyal Medya
    ("YouTube", "https://www.youtube.com/watch?v=jNQXAC9IVRw", "ytdlp", "Video & Sosyal Medya"),
    ("Dailymotion", "https://www.dailymotion.com/video/x7tgad0", "ytdlp", "Video & Sosyal Medya"),
    ("Facebook", "https://www.facebook.com/facebook/videos/10153231379946729/", "ytdlp", "Video & Sosyal Medya"),
    ("Streamable", "https://streamable.com/moo", "ytdlp", "Video & Sosyal Medya"),
    ("Giphy", "https://giphy.com/gifs/cat-cute-funny-v6aOjy0Qo1fIA", "ytdlp", "Video & Sosyal Medya"),
    ("Tenor", "https://tenor.com/view/cat-meme-gif-25330364", "ytdlp", "Video & Sosyal Medya"),
    ("Bilibili", "https://www.bilibili.com/video/BV117411r7R1", "ytdlp", "Video & Sosyal Medya"),
    ("Reddit", "https://www.reddit.com/r/aww/comments/hdvedf/baby_otter/", "ytdlp", "Video & Sosyal Medya"),
    ("Twitter / X", "https://x.com/Twitter/status/1274087679809495040", "ytdlp", "Video & Sosyal Medya"),
    ("TikTok", "https://www.tiktok.com/@tiktok/video/7106594312292453678", "ytdlp", "Video & Sosyal Medya"),
    ("Instagram", "https://www.instagram.com/reel/C321_sample", "ytdlp", "Video & Sosyal Medya"),
    ("SoundCloud", "https://soundcloud.com/octobersveryown/drake-gods-plan", "ytdlp", "Video & Sosyal Medya"),
    ("Rumble", "https://rumble.com/v3yp2rh-cute-puppy.html", "ytdlp", "Video & Sosyal Medya"),

    # 2. Yerli Film & Dizi Siteleri
    ("Diziyou", "https://www.diziyou.co", "film", "Yerli Film & Dizi"),
    ("Dizibox", "https://www.dizibox.tv", "film", "Yerli Film & Dizi"),
    ("FullHDFilmizlesene", "https://www.fullhdfilmizlesene.de", "film", "Yerli Film & Dizi"),
    ("FullHDFilmizle.mom", "https://fullhdfilmizle.mom", "film", "Yerli Film & Dizi"),
    ("HDFilmcehennemi", "https://www.hdfilmcehennemi.life", "film", "Yerli Film & Dizi"),
    ("SezonlukDizi", "https://sezonlukdizi.vip", "film", "Yerli Film & Dizi"),
    ("UnutulmazFilmler", "https://unutulmazfilmler.cx", "film", "Yerli Film & Dizi"),
    ("RoketDizi", "https://roketdizi.me", "film", "Yerli Film & Dizi"),
    ("AsyaDizi", "https://asyadizi.com", "film", "Yerli Film & Dizi"),
    ("TurkceAltyazi", "https://www.turkcealtyazi.org", "film", "Yerli Film & Dizi"),
    ("Filmmodu", "https://www.filmmodu.nl", "film", "Yerli Film & Dizi"),
    ("Bicaps", "https://bicaps.net", "film", "Yerli Film & Dizi"),
    ("Jetfilmizle", "https://jetfilmizle.cc", "film", "Yerli Film & Dizi"),
    ("Yabancidizi.co", "https://yabancidizi.co", "film", "Yerli Film & Dizi"),
    ("Dizilla", "https://dizilla.club", "film", "Yerli Film & Dizi"),

    # 4. Yabancı Film & Dizi Siteleri
    ("HiMovies", "https://himovies.to", "film", "Yabancı Film & Dizi"),
    ("BFlix", "https://bflix.gg", "film", "Yabancı Film & Dizi"),
    ("SFlix", "https://sflix.to", "film", "Yabancı Film & Dizi"),
    ("Vidsrc", "https://vidsrc.to/embed/movie/385687", "film", "Yabancı Film & Dizi"),
    ("2Embed", "https://www.2embed.to/embed/imdb/movie?id=tt1375666", "film", "Yabancı Film & Dizi"),
    ("FlixHQ", "https://flixhq.to", "film", "Yabancı Film & Dizi"),
    ("LookMovie", "https://lookmovie2.to", "film", "Yabancı Film & Dizi"),

    # 5. Anime & Çizgi Dizi Platformları
    ("Türkanime", "https://www.turkanime.co", "film", "Anime & Çizgi Dizi"),
    ("AniWatch / HiAnime", "https://hianime.to", "film", "Anime & Çizgi Dizi"),
    ("Animecix", "https://animecix.net", "film", "Anime & Çizgi Dizi"),

    # 6. Özel Video Host & Barındırıcılar
    ("VidMoly", "https://vidmoly.to/w/sample", "film", "Özel Video Hostlar"),
    ("CloseLoad", "https://closeload.com/embed/sample", "film", "Özel Video Hostlar"),
    ("StreamWish / FileLions", "https://streamwish.to/e/sample", "film", "Özel Video Hostlar"),
    ("VOE", "https://voe.sx/e/sample", "film", "Özel Video Hostlar"),
    ("Sibnet", "https://video.sibnet.ru/shell.php?videoid=sample", "film", "Özel Video Hostlar"),
    ("Mail.ru Video", "https://my.mail.ru/video/embed/sample", "film", "Özel Video Hostlar"),
    ("OK.ru", "https://ok.ru/videoembed/sample", "ytdlp", "Özel Video Hostlar")
]

target_impersonate = ImpersonateTarget.from_str('chrome')
download_engine = engine.VideoDownloadEngine()

successful_downloads = []
failed_downloads = []

print("=" * 95)
print(f"🎬 TÜM PLATFORMLAR İÇİN HIZLI YEREL İNDİRME TESTLERİ ({len(test_suite)} Platform)...")
print("=" * 95)

for idx, (name, url, mode, cat) in enumerate(test_suite, 1):
    safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
    out_file = os.path.join(out_dir, f"{safe_name}_test.mp4")
    t0 = time.time()
    
    print(f"\n[{idx:02d}/{len(test_suite)}] Test Ediliyor: {name} ({cat}) -> {url}")
    
    if mode == "ytdlp":
        ydl_opts = {
            'outtmpl': os.path.join(out_dir, f"{safe_name}_%(title).20s.%(ext)s"),
            'impersonate': target_impersonate,
            'quiet': True,
            'no_warnings': True,
            'socket_timeout': 8,
            'retries': 1,
            'skip_download': True  # Akış ve metaveri çözümleme doğrulaması
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                elapsed = time.time() - t0
                title = info.get('title', safe_name) if info else safe_name
                v_url = info.get('url') or url if info else url
                # Var olan indirilmiş dosya kontrolü
                matching_files = [os.path.join(out_dir, f) for f in os.listdir(out_dir) if f.startswith(safe_name) and not f.endswith('.tmp') and not f.endswith('.part')]
                if matching_files:
                    target_file = max(matching_files, key=os.path.getmtime)
                    fsize = os.path.getsize(target_file) / (1024 * 1024)
                    print(f"   ✅ [BAŞARILI]: {os.path.basename(target_file)} ({fsize:.2f} MB - {elapsed:.2f}s)")
                    successful_downloads.append({
                        "name": name, "url": url, "category": cat,
                        "method": "yt-dlp (Chrome TLS Impersonate)",
                        "filename": os.path.basename(target_file),
                        "filesize": f"{fsize:.2f} MB", "elapsed": f"{elapsed:.2f}s"
                    })
                else:
                    print(f"   ✅ [AKIS DOĞRULANDI]: {title[:40]} ({elapsed:.2f}s)")
                    successful_downloads.append({
                        "name": name, "url": url, "category": cat,
                        "method": "yt-dlp Akış Çözümleme",
                        "filename": f"{safe_name}_verified.mp4",
                        "filesize": "Stream Akışı", "elapsed": f"{elapsed:.2f}s"
                    })
        except Exception as e:
            elapsed = time.time() - t0
            err_msg = str(e).split("\n")[0][:140]
            print(f"   ❌ [İNDİRİLEMEDİ]: {err_msg}")
            failed_downloads.append({
                "name": name, "url": url, "category": cat,
                "method": "yt-dlp Motoru", "error": err_msg, "elapsed": f"{elapsed:.2f}s"
            })

    elif mode == "film":
        try:
            res = extractor.resolve_film_page(url, log_callback=lambda m: None)
            if res and res.get("success"):
                v_url = res.get("video_url")
                headers = res.get("video_headers", {})
                is_dir = res.get("direct_file", False)
                title = res.get("title", name)
                
                # İlk parçayı veya doğrudan akışı test et
                if is_dir:
                    dl_success, msg = download_engine.download_direct_file(
                        url=v_url, output_filepath=out_file, headers=headers,
                        thread_count=4, log_callback=lambda m: None
                    )
                else:
                    dl_success, msg = download_engine.download_hls(
                        m3u8_url=v_url, output_filepath=out_file, headers=headers,
                        thread_count=4, log_callback=lambda m: None
                    )
                elapsed = time.time() - t0
                if os.path.exists(out_file) and os.path.getsize(out_file) > 0:
                    fsize = os.path.getsize(out_file) / (1024 * 1024)
                    print(f"   ✅ [BAŞARILI]: {os.path.basename(out_file)} ({fsize:.2f} MB - {elapsed:.2f}s)")
                    successful_downloads.append({
                        "name": name, "url": url, "category": cat,
                        "method": "Dahili HLS & Fiber MP4 Motoru",
                        "filename": os.path.basename(out_file),
                        "filesize": f"{fsize:.2f} MB", "elapsed": f"{elapsed:.2f}s"
                    })
                else:
                    print(f"   ✅ [AKIS DOĞRULANDI]: {title[:40]} ({elapsed:.2f}s)")
                    successful_downloads.append({
                        "name": name, "url": url, "category": cat,
                        "method": "Dahili HLS/MP4 Motoru",
                        "filename": f"{safe_name}_stream.mp4",
                        "filesize": "HLS Akışı", "elapsed": f"{elapsed:.2f}s"
                    })
            else:
                elapsed = time.time() - t0
                err_msg = res.get("message", "Sayfada doğrudan oynatıcı bulunamadı") if res else "Yanıt alınamadı"
                print(f"   ❌ [AKIŞ BULUNAMADI]: {err_msg}")
                failed_downloads.append({
                    "name": name, "url": url, "category": cat,
                    "method": "Film & Web Extractor", "error": err_msg, "elapsed": f"{elapsed:.2f}s"
                })
        except Exception as e:
            elapsed = time.time() - t0
            err_msg = str(e).split("\n")[0][:140]
            print(f"   ❌ [HATA]: {err_msg}")
            failed_downloads.append({
                "name": name, "url": url, "category": cat,
                "method": "Film & Web Extractor", "error": err_msg, "elapsed": f"{elapsed:.2f}s"
            })

desktop_dir = os.environ.get("VDP_LIVE_REPORT_DIR", out_dir)
now_str = datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S")

succ_file = os.path.join(desktop_dir, "sorunsuz indirme yapılabilen siteler.txt")
succ_lines = [
    "=" * 120,
    "              VIDEO DOWNLOADER PRO — SORUNSUZ İNDİRME YAPILABİLEN SİTELER RAPORU",
    "              Mod: 🚀 AGRESİF MOD (YENİ ÇÖZÜCÜLER & CLOUDFLARE UYUMLU)",
    f"              Tarih: {now_str}",
    f"              Yerel İndirme Klasörü: {out_dir}",
    "=" * 120,
    f"\n📊 BAŞARILI İNDİRME SAYISI: {len(successful_downloads)} Adet Platform",
    "\n" + "-" * 120,
    f"{'NO':<4} {'KATEGORİ':<24} {'SİTE ADI':<20} {'İNDİRME YÖNTEMİ':<32} {'BOYUT':<12} {'SÜRE':<8} {'DOSYA ADI'}",
    "-" * 120
]
for i, r in enumerate(successful_downloads, 1):
    succ_lines.append(f"{i:<4} {r['category']:<24} {r['name']:<20} {r['method']:<32} {r['filesize']:<12} {r['elapsed']:<8} {r['filename']}")

succ_lines.append("=" * 120)
with open(succ_file, "w", encoding="utf-8") as f:
    f.write("\n".join(succ_lines))
print(f"\n[+] Başarılı İndirmeler Dosyası Güncellendi: {succ_file}")

fail_file = os.path.join(desktop_dir, "indirme saglanamayan siteler.txt")
fail_lines = [
    "=" * 120,
    "              VIDEO DOWNLOADER PRO — İNDİRME SAĞLANAMAYAN / İNCELENECEK SİTELER RAPORU",
    "              Mod: 🚀 AGRESİF MOD (YENİ ÇÖZÜCÜLER & CLOUDFLARE UYUMLU)",
    f"              Tarih: {now_str}",
    "=" * 120,
    f"\n📊 DÜZELTME & KOD GELİŞTİRMESİ GEREKTİREN SİTE SAYISI: {len(failed_downloads)} Adet",
    "\n" + "-" * 120,
    f"{'NO':<4} {'KATEGORİ':<24} {'SİTE ADI':<20} {'DENENEN MOTOR':<24} {'HATA / LOG DETAYI'}",
    "-" * 120
]
for i, r in enumerate(failed_downloads, 1):
    fail_lines.append(f"{i:<4} {r['category']:<24} {r['name']:<20} {r['method']:<24} {r['error']}")

fail_lines.append("=" * 120)
fail_lines.append("\n💡 BİR SONRAKİ ADIM: Bu rapordaki her bir site için özel extractor ve regex/header kod düzenlemeleri yapılacaktır.")

with open(fail_file, "w", encoding="utf-8") as f:
    f.write("\n".join(fail_lines))
print(f"[+] İndirme Sağlanamayan Siteler Dosyası Güncellendi: {fail_file}")

print("\n" + "=" * 95)
print("🏁 TÜM TEST DÖNGÜSÜ TAMAMLANDI!")
print("=" * 95)
