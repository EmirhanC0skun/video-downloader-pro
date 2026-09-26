# Proje Bağlamı (Project Context) - Video Downloader Pro Suite

## 1. Proje Amacı ve Kapsamı
Bu proje, web sitelerindeki parçalanmış ve uzantısı maskelenmiş video/ses akışlarını (`.ts`, `seg_xxx.jpg`, `seg_xxx.png`, `.m3u8`) otomatik tespit edip, Türkçe/İngilizce ses kanallarıyla birlikte çoklu iş parçacığı (multithreading) ile indiren, FFmpeg ile tek parça sesli `.mp4` video dosyası olarak birleştiren (Muxing), aynı zamanda YouTube/Sosyal Medya indirme ve MP3/WAV ses dönüştürme yeteneklerine sahip profesyonel bir masaüstü yazılım paketidir.

---

## 2. Mimari ve Çözülen Temel Problemler
- **Ayrık Ses & Görüntü (Split Streams):** Modern film oynatıcıları (SetFilm/FastPlay/Shaka) videoyu `video/seg_xxx.jpg`, Türkçe sesi `tur/seg_xxx.png` olarak ayrı sunar. Motorumuz her iki akışı eşzamanlı indirip FFmpeg `-c copy -map 0:v:0 -map 1:a:0` ile kayıpsız birleştirir.
- **Otomatik Film Çözücü (`extractor.py`):** Kullanıcının F12/cURL kopyalamasına gerek kalmadan doğrudan sayfa linkinden WordPress AJAX, `SPG.cerceve` XOR şifre çözümü, `X-Sp` FNV-1a jeton üretimi ve master playlist ayrıştırmasını tam otomatik gerçekleştirir.
- **AES-128 Şifreli HLS:** `engine.decrypt_hls_segment()` PKCS#7 dolgusunu kaldırır ve IV verilmediğinde segment medya sırasından türetir (RFC 8216 §5.2). Çözme başarısız olursa segment **yazılmaz** — bozuk dosya üretilmez.
- **YouTube & Sosyal Medya İndirici:** `yt-dlp` entegrasyonu ile 1080p/4K video ve MP3 ses indirme desteği.
- **Medya & Ses Dönüştürücü:** Herhangi bir video dosyasını tek tıkla 320 kbps MP3 veya stüdyo kalitesinde WAV formatına çevirme.
- **Bağımsız Çalıştırılabilirlik (.EXE):** `imageio-ffmpeg` ve `PyInstaller` entegrasyonu sayesinde harici Python veya FFmpeg kurulumu gerektirmeden bağımsız Windows masaüstü programı olarak çalışır.

---

## 3. Dosya Yapısı

### Çekirdek (tek doğruluk kaynağı — depo kökü)
- `extractor.py`: Film sayfası, iframe, SPG XOR şifre çözücü, X-Sp jeton üreteci ve ses/görüntü akış ayrıştırıcı. Genel giriş noktası `resolve_film_page()`, sonucu `normalize_extraction_result()` ile tek bir sözleşmeye oturtur (`RESULT_DEFAULTS`).
- `engine.py`: Çift/çok kanallı akış indiricisi, AES-128 çözücü, FFmpeg muxer, YouTube `yt-dlp` motoru ve MP3/WAV ses dönüştürücü.
- `sniffer.py`: Master M3U8 ayrıştırıcı ve ağ dinleyici yedek yolu.
- `gui.py`: Çok sekmeli (Film, YouTube, Kuyruk, MP3 Dönüştürücü, Geçmiş, Ayarlar) CustomTkinter arayüzü.
- `history.py`: Thread-safe SQLite WAL geçmiş yöneticisi (tembel başlatma — `import` yan etkisi yoktur).
- `logger.py`: Merkezî loglama. `VDP_DEBUG=1` ile tam yığın izleri dosyaya yazılır.
- `exceptions.py`: Alan bazlı hata hiyerarşisi.
- `main.py`: Ana başlatıcı (`--cli` ile komut satırı modu).

### Modüler çözücüler
- `extractors/`: `BaseExtractor` / `ExtractorResult` sözleşmesi ve `ExtractorRegistry`.
  Registry, `resolve_film_page()` içindeki tüm statik çözücüler başarısız olduğunda
  **son çare** olarak devreye girer. `SeriesFilmExtractor` bilerek monolite geri
  çağrı yapmaz (sonsuz özyineleme olurdu).

### Mobil
- `android_app/core/`: **ÜRETİLMİŞ** çekirdek kopyası. Elle düzenlenmez;
  `python tools/sync_mobile_core.py` ile kökten yansıtılır. Flet APK derlemesi
  yalnızca `android_app/` ağacını paketlediği için bu kopya zorunludur.
- `android_app/theme.py`: Tek kaynaklı mobil renk paleti.
- `android_app/mobile_engine.py`: Mobil indirme denetleyicisi, bildirim çubuğu
  entegrasyonu ve saf-Python MPEG-TS ADTS ses ayıklayıcısı.
- `android_app/views/`: Flet arayüz görünümleri.

### Araçlar ve testler
- `tools/sync_mobile_core.py`: Çekirdeği mobil pakete yansıtır. `--check` ile CI doğrulaması.
- `tools/live_smoke_test.py`, `tools/live_full_test.py`: Canlı ağ testleri (elle çalıştırılır, CI'da değil).
- `tests/`: 116 çevrimdışı test. `test_audit_regressions.py` kod denetiminde
  bulunan her hata için (A1…F5) regresyon koruması sağlar.
- `build_exe.py` + `VideoDownloaderPro.spec`: Tek doğruluk kaynağı spec dosyasıdır.
- `docs/research/`: Site analizleri, oynatıcı JS örnekleri ve geçmiş raporlar.

---

## 4. Değişmez Kurallar
1. Çekirdek modül değiştiyse `python tools/sync_mobile_core.py` çalıştırılır.
2. Yeni bir hata düzeltilirse, düzeltme geri alındığında kırılacak bir test eklenir.
3. Tkinter widget'ları yalnızca ana iş parçacığından (`after`/`after_idle`) güncellenir.
4. Kullanıcıya göre değişen yollar ortam değişkeni veya `~/.video_downloader/settings.json` üzerinden okunur.
5. Yutulan istisnalar en azından `logger.debug(..., exc_info=True)` ile kaydedilir.
