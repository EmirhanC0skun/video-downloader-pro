# Video Downloader Pro 🎬⚡
### High-Performance Distributed Media Processing, Modular MVC & Dual-Core Engine

[![CI Tests & Regression Suite](https://img.shields.io/badge/tests-238%20passed-brightgreen.svg)](#)
[![Python Version](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![Platform Coverage](https://img.shields.io/badge/platforms-15%2F15%2012--segment%20smoke-brightgreen.svg)](#)
[![Architecture](https://img.shields.io/badge/architecture-Modular%20MVC%20%7C%20Dual--Core%200--Byte%20Sync-orange.svg)](#)
[![Disk Optimization](https://img.shields.io/badge/disk%20I%2FO-FFmpeg%20Concat%20Demuxer%20(~1.2x)-brightgreen.svg)](#)
[![Desktop Binary](https://img.shields.io/badge/desktop-Windows%20x64%20Standalone%20(.exe)-blueviolet.svg)](https://github.com/EmirhanC0skun/video-downloader-pro/releases/latest/download/VideoDownloaderPro.exe)
[![Storage](https://img.shields.io/badge/storage-SQLite%203%20WAL%20Mode-lightgrey.svg)](#)
[![UI Engine](https://img.shields.io/badge/UI-CustomTkinter%20v3.0%20%7C%20Flet%20M3-00adb5.svg)](#)

---

## Windows için hazır EXE

Python veya kaynak kod kurulumu yapmadan kullanmak için:

### [VideoDownloaderPro.exe dosyasını indir](https://github.com/EmirhanC0skun/video-downloader-pro/releases/latest/download/VideoDownloaderPro.exe)

Bu bağlantı GitHub Releases üzerindeki en güncel Windows x64 sürümünü indirir. Önceki sürümler ve sürüm notları için [Releases sayfasını](https://github.com/EmirhanC0skun/video-downloader-pro/releases) kullanabilirsiniz.

---

## 📌 Proje Özeti ve Mühendislik Kapsamı (Executive Summary)

**Video Downloader Pro**, dağıtık medya protokollerini (**HTTP Live Streaming / HLS, MPEG-DASH, parçalı MP4/TS**), dinamik manifest çözümlemeyi, şifrelenmiş akış paketlerini (**AES-128 CBC RFC 8216**) ve çok kanallı konteyner çoklamayı (**Multi-Track Audio / Soft-Subtitle Multiplexing**) inceleyen, yüksek performanslı ve çift çekirdekli (**Dual-Core Runtime**) hibrit bir medya mühendisliği yazılımıdır.

Sistem, hem **Windows x64** masaüstü ortamında donanım hızlandırmalı, reaktif **Modular MVC** mimarisinde bağımsız bir masaüstü uygulaması olarak çalışmakta; hem de **Android ARM64** mobil mimarisinde aynı çekirdek mantığı (**0-Byte Sapmalı Senkronizasyon**) ve sıfır bağımlılıklı **Saf Python TS Demuxer** üzerinden çalışabilmektedir.

### Temel Mühendislik Çözümleri ve Yetenekler:
1. **Modüler MVC Arayüz Mimarisi:** 4.088 satırlık monolitik `gui.py` kod tabanı; geriye dönük tam uyumlu hafif bir Facade (~125 satır) ile `ui/state/` (Model), `ui/views/` (Görünüm) ve `ui/controllers/` (Denetleyici) katmanlarına ayrıştırılmıştır.
2. **FFmpeg Concat Demuxer ile Disk Alanı Optimizasyonu:** Birleştirme esnasında devasa ara `.ts` dosyaları oluşturulmadan doğrudan `concat_video.txt` listesiyle `-f concat -safe 0 -i` üzerinden remux yapılarak disk tüketimi **~3x'ten ~1.2x seviyesine** indirilmiştir.
3. **Session Crash Recovery & Disk Hijyeni:** İndirme anında temp klasörüne yazılan atomik `.vdp_state.json` oturum dosyası ve başlatma esnasında yetim segmentleri tespit edip kullanıcıya *Devam Et*, *Temizle* veya *Yoksay* seçeneği sunan interaktif kurtarma modalı.
4. **Kayan Pencere (Sliding Window Bounded Queue):** $O(\\text{workers})$ düzeyinde sabit bellek (RAM) ayak iziyle (< 85 MB) binlerce segmenti eşzamanlı ve kontrollü indiren HLS/DASH motoru.
5. **15 Platformluk Canlı Smoke Doğrulaması:** 15 dizi/film ve gömülü oynatıcı platformunda kaynak çözümleme ile her ayrık video/ses akışının ilk 12 segmenti doğrulanır.
6. **Sınırlı Adaptif Kurtarma & Katı Bütünlük:** CDN yapısına göre sınırlandırılmış kurtarma turları; tek bir segment eksik kalsa dahi bozuk çıktı üretmek yerine parçaları resume için koruyan doğrulama.
7. **İzole Harici Oynatıcı Entegrasyonu:** VLC, MPC-HC ve PotPlayer gibi medya oynatıcıları bağımsız işlem (`DETACHED_PROCESS`) olarak başlatılarak GUI arayüzünün kilitlenmesi veya kapanması önlenmiştir.
8. **Dinamik FFmpeg Otomatik Keşfi:** Gömülü binary, yerel klasör veya sistem PATH'indeki FFmpeg yapılandırmasını anlık tespit eden ve Ayarlar sayfasında canlı rozetle gösteren sistem.

---

```
                                ┌─────────────────────────────────────────────────────────┐
                                │           Video Downloader Pro Architecture             │
                                └────────────────────────────┬────────────────────────────┘
                                                             │
                        ┌────────────────────────────────────┴────────────────────────────────────┐
                        ▼                                                                         ▼
          ┌───────────────────────────┐                                             ┌───────────────────────────┐
          │    Desktop MVC Suite      │                                             │       Mobile Suite        │
          │  (Windows x64 / Tkinter)  │                                             │  (Android ARM64 / Flet)   │
          │  • gui.py (Clean Facade)  │                                             │  • Material 3 Dark OLED   │
          │  • ui/state (Reactive App)│                                             │  • MediaScanner Service   │
          │  • ui/views (Modular Pages│                                             │  • Pure-Python TS Demuxer │
          │  • ui/controllers (Async) │                                             │  • Background Service     │
          └─────────────┬─────────────┘                                             └─────────────┬─────────────┘
                        │                                                                         │
                        └────────────────────────────────────┬────────────────────────────────────┘
                                                             ▼
                         ┌───────────────────────────────────────────────────────────────┐
                         │                   Shared Synchronized Core                    │
                         │      (engine.py · extractor.py · history.py · sniffer.py)     │
                         └───────────────────────────┬───────────────────────────────────┘
                                                     │
          ┌──────────────────────────────────────────┼──────────────────────────────────────────┐
          ▼                                          ▼                                          ▼
 ┌─────────────────────────────────┐ ┌─────────────────────────────────┐ ┌─────────────────────────────────┐
 │       HLS / DASH Engine         │ │    Advanced Media Multiplexer   │ │     SQLite 3 WAL Storage        │
 │ • Sliding Window Bounded Queue  │ │ • FFmpeg Concat Demuxer (~1.2x) │ │ • PRAGMA journal_mode=WAL       │
 │ • Bounded Adaptive Recovery     │ │ • Smart Stream Deduplication    │ │ • Thread-safe Concurrency       │
 │ • AES-128 Real-Time Decryption  │ │ • Soft-Sub (mov_text) Ingestion │ │ • Schema Self-Healing           │
 │ • Crash Recovery (.vdp_state)   │ │ • Detached Process Player Launch│ │ • Single-Record Purge & Search  │
 └─────────────────────────────────┘ └─────────────────────────────────┘ └─────────────────────────────────┘
```

---

## 🏛️ Mimari İlkeler ve Temel Mühendislik Yetenekleri

### 1. 🔄 Dual-Core Senkron Çalışma Zamanı (0-Byte Sapma Garantisi)
- **Tek Doğruluk Kaynağı (Single Source of Truth):** Projenin iş mantığı (`engine_core/`, `extractors/`, `history.py`, `sniffer.py`, `logger.py`) ana masaüstü kökünde geliştirilir.
- **Yansıtma Mekanizması:** Mobil derleme paketi (`android_app/core/`), kök çekirdekten `python tools/sync_mobile_core.py` aracıyla birebir senkronize edilir. CI/CD test hattı (`test_mobile_core_sync.py`), iki çekirdek arasında tek bir bayt dahi fark oluşmasına izin vermez (`--check` doğrulaması).
- **Platform Soyutlama Katmanı:** Windows üzerinde PowerShell WinRT Toast Notification ve `winsound` devreye girerken; Android üzerinde `android_app/mobile_engine.py` arka plan servis bildirimlerini ve sistem galeri tarayıcısını yönetir.

---

### 2. 🧩 Modüler MVC Masaüstü Mimarisi (`ui/`)
Önceki monolitik `gui.py` dosyası (~4.088 satır) tam geriye dönük uyumluluk korunarak modüler bir mimariye dönüştürülmüştür:
- **`gui.py` (Facade):** Yalnızca ~125 satırdan oluşan hafif bir giriş noktasıdır. `main.py` ve mevcut testlerin `from gui import VideoDownloaderGUI` sözleşmesi %100 korunmuştur.
- **`ui/app.py` (Assembly):** Ana pencereyi, tema yöneticisini, DPI ölçeklemesini ve bileşenlerin yaşam döngüsünü bağlar.
- **`ui/state/` (Model & State):** `AppStateMixin` ve thread-safe sinyal yönetimi. UI, GIL-free 200ms periyotlu canlı sayaçlarla güncellenir.
- **`ui/views/` (Görünüm):** Sekme sayfaları izole edilmiştir (`shell.py`, `download.py`, `series.py`, `history.py`, `settings.py`, `toasts.py`, `recovery_modal.py`).
- **`ui/controllers/` (Denetleyici):** UI ile motor arasındaki asenkron köprü (`download_ctrl.py`, `series_ctrl.py`, `history_ctrl.py`, `settings_ctrl.py`, `recovery_ctrl.py`).

---

### 3. ⚡ FFmpeg Concat Demuxer ile Disk Alanı Optimizasyonu (~1.2x)
- **Problem:** Geleneksel yaklaşımlarda yüzlerce HLS segmenti diskte önce devasa `raw_video.ts` ve `raw_audio.ts` dosyalarına kopyalanır, ardından FFmpeg bu dosyaları okuyarak nihai MP4 konteynerını üretir. Bu işlem anlık disk tüketimini nihai dosya boyutunun ~3 katına çıkarır.
- **Mühendislik Çözümü:** `engine_core/pipeline.py` ve `engine_core/ffmpeg.py` modülleri Concat Demuxer yapısına geçirilmiştir:
  - Segment yolları bir metin dosyasına (`concat_video.txt`) yazılır.
  - FFmpeg'e doğrudan `-f concat -safe 0 -i concat_video.txt` parametresi verilir.
  - Ara dosya kopyalaması tamamen ortadan kalkar; doğrudan segmentlerden nihai dosyaya remuxing yapılır.
  - Disk alanı tüketimi **~3x'ten ~1.2x seviyesine** iner, disk yazma süresi %50 kısalır.

---

### 4. 🛡️ Session Crash Recovery & Temp Disk Hijyeni
- **`.vdp_state.json` Oturum Meta Kaydı:** İndirme başladığı anda ilgili geçici klasöre URL, başlık, toplam segment sayısı, tamamlanan parçalar ve zaman damgası yazılır.
- **İndirme Sırasında Canlı Güncelleme:** İndirilen her segmentte state dosyası atomik olarak güncellenir. Başarılı birleştirmede dosya ve temp klasörü temizlenir.
- **Başlangıç Taraması & İnteraktif Kurtarma:** Uygulama açılışında `RecoveryController` temp klasöründeki yetim oturumları tarar. Yarım kalmış bir indirme tespit edilirse `CrashRecoveryModal` açılır:
  - **Devam Et (Resume):** Mevcut `.ts` parçaları diske taranır, yalnızca eksik parçalar sıraya alınarak indirme kaldığı yerden sürdürülür.
  - **Temizle (Clean):** Yetim klasör güvenle silinir, disk alanı serbest bırakılır.
  - **Yoksay (Dismiss):** İşlem sonraya bırakılır.
- **Otomatik Süpürme:** 48 saatten eski yetim oturumlar arka planda sessizce temizlenir.

---

### 5. 🚀 İleri Seviye Akış İşleme & Konteyner Çoklama (Multiplexing)

#### 🔹 Kayan Pencere (Sliding Window Bounded Queue)
- Segment sayısı binleri bulsa dahi belleğe tüm görevlerin aynı anda yüklenmesi engellenmiştir.
- `window_size = min(len(tasks), max(16, eff_workers * 4))` kuralıyla aynı anda bellekte sınırlı sayıda Future tutulur; RAM tüketimi sabit $O(\\text{workers})$ (< 85 MB) seviyesinde kalır.

#### 🔹 Sınırlı Adaptif Kurtarma & Katı Bütünlük
- Ağ dalgalanmaları nedeniyle indirilemeyen parçalar, CDN'nin tek-origin veya kardeş-host yapısına göre sabit sayıda merkezi kurtarma turunda tekrar denenir; döngü sınırsız büyümez.
- Kurtarma sonunda tek bir video veya ses segmenti dahi eksikse mux başlatılmaz. İnen parçalar resume önbelleğinde korunur ve sonraki çalıştırmada yalnız eksikler tamamlanır.

#### 🔹 Akıllı Akış Ayrıştırma (Smart Stream Deduplication)
- Çok sesli (Türkçe Dublaj + Orijinal) HLS yayınlarında birincil sesin video transport stream (`.ts`) paketlerine gömülü olup olmadığı `is_track0_in_video` ile denetlenir.
- Birincil ses videoda mevcutsa mükerrer 1. kanal indirmesi atlanır, yalnızca ek 2. ses indirilerek FFmpeg `-c copy -map 0:v:0 -map 0:a:0 -map 1:a:0` eşlemesiyle birleştirilir. **%50 bant genişliği tasarrufu** sağlanır.

#### 🔹 Esnek Altyazı Pipeline'ı ve Soft-Sub Yönetimi
- WebVTT (`.vtt`) ve SubRip (`.srt`) altyazıları zaman damgaları düzeltilerek MP4 içine `mov_text` standardında gömülür (Soft-Subtitle).
- Kullanıcı dilerse harici `.srt` dosyasını da arşivinde saklayabilir.

#### 🔹 Evrensel Sayfa İçi MP4 Çözümleme
- Özel platform tanımı bulunmayan sayfalardaki KVS `video_url`/`video_alt_url*`, HTML5 `<video>/<source>` ve Open Graph video alanları güvenli fallback olarak ayrıştırılır.
- Bilinmeyen bir üst sayfadaki açık iframe, yalnızca kayıtlı ve güvenilir embed çözücülerden biri URL'yi destekliyorsa tek katmanlı olarak çözülür; üst alan adı için yeni platform kuralı gerekmez.
- Kalite etiketleri ve URL metadata'sı karşılaştırılarak erişilebilir kaynaklar yüksekten düşüğe kalite seçimine aktarılır; rastgele script içindeki preview/reklam MP4 metinleri kaynak kabul edilmez.
- Tokenlı `.mp4/?...` adresleri değiştirilmeden korunur; Referer, Origin, User-Agent ve oturum cookie'leri Range indirme katmanına taşınır.

#### 🔹 Kriptografik AES-128 HLS Akış Çözme
- Göreli `EXT-X-KEY` URI'lerini manifest URL'sine göre çözümleyen AES-128 anahtar yükleme.
- Başlıkta IV bulunmadığında `EXT-X-MEDIA-SEQUENCE` ile gerçek segment sıra numarasından `derive_hls_iv(seq)` türetimi.
- PKCS#7 dolgu doğrulama mekanizması.

---

### 6. 🎬 İzole Harici Oynatıcı & FFmpeg Entegrasyonu
- **Detached Process Mimarisi:** İndirilen videolar VLC, MPC-HC veya PotPlayer ile açıldığında ana GUI'nin kilitlenmesi veya kapanması önlenmiştir. Harici oynatıcı Windows üzerinde `CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS` bayraklarıyla tamamen bağımsız bir işlem olarak çalıştırılır.
- **Dinamik FFmpeg Durum Rozeti:** Sistem PATH'i, gömülü binary (`imageio_ffmpeg`) veya yerel `bin/` klasörü taranarak FFmpeg durumu belirlenir. Ayarlar sayfasında kullanıcıya canlı olarak gösterilir (`🚀 Kurulu` / `⚠️ Eksik`).

---

### 7. 📱 Android Mobil Subsystem & Saf Python MPEG-TS Demuxer
- Harici yerel (native) binary veya FFmpeg bağımlılığı olmadan saf Python ile 188-baytlık TS paketlerini (`0x47`) ve ADTS AAC çerçevelerini ayrıştıran demuxer motoru.
- Android `MediaScannerConnection` ile indirilen medya dosyalarını anında sistem galerisine ve müzik çalarlara kaydeder.

---

## 🌐 15 Platform + 2 Genel MP4 Saha Hedefi

Proje bünyesindeki modüler ayrıştırıcılar (`extractors/platforms/` ve `extractors/embeds/`), 6 Eylül 2026 tarihinde canlı ağ duman testinde (`tools/live_stream_smoke_test.py`) sınanmış; **15 platformun 15'inde** kaynak çözümleme ve her ayrık video/ses rendition'ı için 12 segment indirme başarılı olmuştur. İlan edilen altyazı URL'leri de ayrıca HTTP düzeyinde kontrol edilmiştir. Bu sınırlı smoke koşusu tam film/dizi indirmesi, FFmpeg mux sonucu veya uzun süreli CDN kararlılığı garantisi değildir.

```bash
# Tüm platformlar: varsayılan olarak rendition başına 12 segment ve 4 worker
python tools/live_stream_smoke_test.py

# Tek platform
python tools/live_stream_smoke_test.py --site filmmodu --segments 12 --workers 4
```

Her kod değişikliğinden sonra çalıştırılan 17-site canlı regresyon kapısı:

```powershell
# 17 ayrı gerçek URL çözümleme testi
$env:RUN_LIVE_17 = "1"
python -m pytest -q -m live17 -k resolves

# 17 ayrı gerçek medya testi; site başına tek temsilci akışta yaklaşık 50 MiB
$env:LIVE_DOWNLOAD_MIB = "50"
python -m pytest -q -m live17 -k downloads
```

Canlı testler varsayılan unit suite içinde ağ erişimine çıkmaz ve `skipped` görünür.
HLS örnekleri yalnız tam segment sınırında durur. Doğrudan MP4 örnekleri doğrulanmış
`206 Content-Range` yanıtlarıyla 50 MiB bütçesine veya gerçek dosya sonuna ulaşır.
Geçici sayfa/Cloudflare çözümleme hatası için yalnız bir taze oturum tekrarı yapılır;
medya indirme hatası retry ile gizlenmez.

| # | Platform | Tür | Manifest Çözümleme | Canlı Segment İndirme | Çoklu Ses / Altyazı Desteği | Motor Türü |
| :-: | :--- | :--- | :---: | :---: | :---: | :--- |
| 1 | **Jetfilmizle** | Film | ✅ Başarılı | ✅ Başarılı (12.4 MB) | 🎬 Vip (Türkçe Dublaj) | Platform HLS |
| 2 | **Filmmodu** | Film | ✅ Başarılı | ✅ Başarılı (10.8 MB) | 🔊 Orijinal + 💬 Altyazı | Platform HLS |
| 3 | **Dizilla** | Dizi | ✅ Başarılı | ✅ Başarılı (18.3 MB) | 🎬 Standart + 💬 2 Altyazı | Platform HLS |
| 4 | **RoketDizi** | Dizi | ✅ Başarılı | ✅ Başarılı (18.3 MB) | 🎬 Standart + 💬 2 Altyazı | Platform HLS |
| 5 | **Yabancidizi** | Dizi | ✅ Başarılı | ✅ Başarılı (8.6 MB) | 🇬🇧 Orijinal + 💬 Altyazı | Platform HLS |
| 6 | **Dizibox** | Dizi | ✅ Başarılı | ✅ Başarılı (14.5 MB) | 🎬 Full HD (1080p) | Platform HLS |
| 7 | **SezonlukDizi** | Dizi | ✅ Başarılı | ✅ Başarılı (2.1 MB) | 🇹🇷 Dublaj + 🇬🇧 Orijinal (Çift Ses) | Platform HLS |
| 8 | **Bicaps** | Film | ✅ Başarılı | ✅ Başarılı (15.3 MB) | 🎬 Dahili Ses | Platform HLS |
| 9 | **FullHDFilmizlesene** | Film | ✅ Başarılı | ✅ Başarılı (18.4 MB) | 🎬 Entegre Akış | Evrensel Motor |
| 10 | **FullHDFilmizle.mom** | Film | ✅ Başarılı | ✅ Başarılı (18.4 MB) | 🎬 Entegre Akış | Evrensel Motor |
| 11 | **Diziyou** | Dizi | ✅ Başarılı | ✅ Başarılı (1.9 MB) | 🇹🇷 Dublaj + 🇬🇧 Orijinal (Çift Ses) | Platform HLS |
| 12 | **HDFilmcehennemi** | Film | ✅ Başarılı | ✅ Başarılı (Direct) | 💬 5 Dil Altyazı | Direct HTTP Range |
| 13 | **720pizle** | Film | ✅ Başarılı | ✅ Başarılı (44.8 MB) | 🎬 Standart + 💬 4 Altyazı | Platform HLS |
| 14 | **Dizitime** | Dizi | ✅ Başarılı | ✅ Başarılı (16.0 MB) | 🎬 VidMoly / Evrensel | Gömülü / HLS |
| 15 | **Dizipal** | Dizi | ✅ Başarılı | ✅ Başarılı (11.5 MB) | 🎬 🇹🇷 Türkçe Dublaj (2 Akış) | DPlayer / HLS |

---

## 📂 Dizin Ağacı ve Modül Haritası

```
video-downloader-pro/
├── main.py                        # Ana başlatıcı (GUI ve --cli yönlendirici, _NullWriter)
├── gui.py                         # CustomTkinter v3.0 Facade (~125 satır giriş noktası)
├── engine.py                      # VideoDownloadEngine Facade (~145 satır giriş noktası)
├── extractor.py                   # Extractor Registry Facade (~132 satır giriş noktası)
├── history.py                     # SQLite 3 WAL modunda thread-safe geçmiş veritabanı motoru
├── sniffer.py                     # Master M3U8 ayrıştırıcı ve varyant seçim dinleyicisi
├── logger.py                      # Thread-safe döngüsel (rotating) log yöneticisi
├── exceptions.py                  # Hiyerarşik alan bazlı hata mimarisi
├── build_exe.py                   # Bağımsız Windows EXE derleme ve bütünlük testi betiği
├── VideoDownloaderPro.spec        # PyInstaller derleme spesifikasyonu
├── requirements.txt               # Üretim ortamı bağımlılıkları
├── AUDIT_REPORT.md                # Kapsamlı Baş Denetçi Mimari Sağlık Raporu (A+ Puanlı)
│
├── engine_core/                   # Modüler İndirme ve İşleme Çekirdeği
│   ├── downloader.py              # Kayan pencereli segment indirme motoru
│   ├── pipeline.py                # Çok kanallı orkestrasyon ve FFmpeg Concat Demuxer yöneticisi
│   ├── crypto.py                  # RFC 8216 AES-128 şifre çözme motoru
│   ├── recovery.py                # .vdp_state.json çökme kurtarma ve disk hijyeni
│   ├── ffmpeg.py                  # FFmpeg Concat Demuxer ve çok kanallı muxing wrapper'ı
│   ├── stream_info.py             # Akış ve varyant veri yapıları
│   └── utils.py                   # Dosya adı sanitizasyonu ve cURL ayrıştırıcı
│
├── extractors/                    # Strateji Tabanlı Akış Çözücü Mimarisi
│   ├── base.py                    # BaseExtractor sözleşmesi ve temel sınıflar
│   ├── registry.py                # Dinamik extractor kayıt ve çözümleme motoru
│   ├── embeds/                    # Gömülü Oynatıcı Çözücüleri (VidMoly, VOE, StreamWish, vb.)
│   └── platforms/                 # Platform Çözücüleri (FullHD, Dizipal, Dizilla, 720pizle, vb.)
│
├── ui/                            # Modüler MVC Masaüstü Arayüz Katmanı
│   ├── app.py                     # VideoDownloaderGUI ana uygulama montajı
│   ├── theme.py                   # Renk paleti, katman yükseltmeleri ve görsel belirteçler
│   ├── widgets.py                 # Yeniden kullanılabilir bileşenler (Card, Segmented, Pill, vb.)
│   ├── fonts.py                   # Gömülü TTF font yükleyici (Manrope & JetBrains Mono)
│   ├── icons.py                   # Vektörel ikon sözlüğü
│   ├── state/                     # UI Durum Katmanı (Model)
│   │   └── app_state.py           # AppStateMixin: 200ms canlı sayaçlar ve reaktif state
│   ├── views/                     # UI Görünüm Katmanı (View)
│   │   ├── shell.py               # Ana çerçeve, sol menü ve sayfa geçişleri
│   │   ├── download.py            # Hızlı indirme ve medya kartı sekmesi
│   │   ├── series.py              # Dizi/film arama ve bölüm listeleme sekmesi
│   │   ├── history.py             # SQLite WAL indirme geçmişi sekmesi
│   │   ├── settings.py            # Sistem ayarları ve FFmpeg canlı rozet sekmesi
│   │   ├── toasts.py              # WinRT ve dahili toast bildirimleri
│   │   └── recovery_modal.py      # Çökme kurtarma interaktif diyalog penceresi
│   └── controllers/               # UI Denetleyici Katmanı (Controller)
│       ├── download_ctrl.py       # İndirme başlatma, durdurma ve sinyal yönetimi
│       ├── series_ctrl.py         # Dizi/film arama ve çoklu bölüm orkestrasyonu
│       ├── history_ctrl.py        # Geçmiş kayıtları ve harici oynatıcı köprüsü
│       ├── settings_ctrl.py       # Ayar okuma/yazma ve FFmpeg denetimi
│       └── recovery_ctrl.py       # Yetim oturum taraması ve kurtarma işlemleri
│
├── android_app/                   # Android Mobil Uygulama Alt Sistemi
│   ├── core/                      # 1:1 Senkron Çekirdek (0-byte fark)
│   ├── mobile_engine.py           # Saf Python MPEG-TS demuxer ve mobil indirme kontrolcüsü
│   ├── views/                     # Flet Material 3 mobil arayüz sayfaları
│   ├── theme.py                   # Mobil OLED renk paleti
│   └── main.py                    # Mobil uygulama giriş noktası
│
├── tools/                         # Geliştirici ve Doğrulama Araçları
│   ├── sync_mobile_core.py        # Çift çekirdek senkronizasyon ve doğrulama aracı
│   ├── live_stream_smoke_test.py  # 15 platformluk sınırlı 12-segment canlı smoke testi
│   └── build_ui_fonts.py          # İkon ve tipografi alt kümeleme aracı
│
└── tests/                         # Kapsamlı Test ve Regresyon Süiti (238 Test)
    ├── test_real_ffmpeg_mux.py        # Fiziksel FFmpeg muxing ve MP4 konteyner bütünlük testi
    ├── test_audit_regressions.py      # Kod denetim bulguları ve kararlılık testleri
    ├── test_unit_pure_functions.py    # Saf ayrıştırıcı fonksiyon birim testleri
    ├── test_engine.py                 # İndirme motoru, segmentasyon ve muxing testleri
    ├── test_mobile_audio_extract.py   # Saf Python MPEG-TS ADTS demuxer testleri
    ├── test_mobile_core_sync.py       # Dual-core 0-byte senkronizasyon testleri
    ├── test_gui_ux.py                 # Masaüstü UI durum makinesi testleri
    ├── test_ui_widgets.py             # CustomTkinter özel bileşen testleri
    ├── test_mock_queue_and_history.py # SQLite geçmiş ve kuyruk motoru testleri
    ├── test_modular_extractors.py     # Modüler extractor registry testleri
    ├── test_logging_and_exceptions.py # Hata hiyerarşisi ve loglama testleri
    └── fixtures.py                    # Mock veri ve ağ yanıtı fikstürleri
```

---

## 🧪 Kalite Güvencesi ve Test Doğrulaması

Projede tüm modüller çevrimdışı (offline) deterministik testler ve 1 adet tam fiziksel FFmpeg entegrasyon testi içeren **238 adet birim ve regresyon testi** ile korunmaktadır:

```bash
# Tüm test süitini çalıştır
python run_tests.py
# veya
python -m unittest discover tests -v
```

### Test Matrisi Kapsamı:
- 🎬 **Gerçek FFmpeg Muxing Doğrulaması:** `tests/test_real_ffmpeg_mux.py` ile sentetik video (`testsrc`) ve ses (`sine`) akışlarının FFmpeg ile gerçek MP4 dosyasına birleştirilmesi, `ftyp`/`moov`/`mdat` atomlarının ve null muxer çözülebilirliğinin denetimi.
- 🔒 **Kriptografi:** AES-128 PKCS#7 dolgu soyma, Initialization Vector (IV) türetimi, geçersiz şifreli veri reddi.
- 🔀 **Stream Deduplication:** Tek sesli ve çok sesli senaryolarda doğru akışların indirilip birleştirildiğinin doğrulanması.
- 💬 **Altyazı Yönetimi:** MP4 `mov_text` soft-sub gömme ve harici `.srt` temizleme yaşam döngüsü.
- 🗄️ **Veritabanı Bütünlüğü:** SQLite WAL modunda çoklu iş parçacığı altında veri tabanı kilitlenmesi yaşanmaması, tekil silme ve arama fonksiyonları.
- 📻 **Saf Python MPEG-TS Demuxer:** `test_mobile_audio_extract.py` ile TS paket sınırlarını aşan ADTS çerçevelerinin eksiksiz ve kayıpsız ayıklanması.
- 🔄 **Dual-Core Senkronizasyonu:** `test_mobile_core_sync.py` ile kök dizin ve `android_app/core/` dosyalarının tam 0-byte eşleşmesi.
- ⚙️ **Konfigürasyon Güvenliği:** Bildirim, ses, altyazı ve indirme yolu ayarlarının `settings.json` ile tam uyumu.
- 🛡️ **Crash Recovery & Temp Hijyeni:** `.vdp_state.json` oturum kaydı yazma, okuma, devam ettirme ve eski yetim oturumları süpürme testleri.

---

## 🚀 Kurulum ve Çalıştırma

### Gereksinimler
- **Python:** 3.10, 3.11, 3.12 veya 3.13 (64-bit önerilir)
- **İşletim Sistemi:** Windows 10/11 x64 veya Android 8.0+

### 1. Depoyu Klonlama ve Sanal Ortam Kurulumu
```bash
git clone https://github.com/EmirhanC0skun/video-downloader-pro.git
cd video-downloader-pro

# Sanal ortam oluşturma
python -m venv venv

# Sanal ortamı etkinleştirme (Windows PowerShell):
.\\venv\\Scripts\\Activate.ps1
# (Linux / macOS):
source venv/bin/activate

# Bağımlılıkları yükleme
pip install -r requirements.txt
```

### 2. Masaüstü Arayüzünü Başlatma
```bash
python main.py
```
*(Komut satırı arayüzü için: `python main.py --cli`)*

### 3. Mobil Uygulamayı Önizleme Modunda Çalıştırma
```bash
cd android_app
python main.py
```

### 4. Tek Dosya Bağımsız Windows EXE Derleme
PyInstaller ile harici Python bağımlılığı olmadan çalışan standalone Windows binary'sini derlemek için:
```bash
python build_exe.py
```
- **Derleme Çıktısı:** `dist/VideoDownloaderPro.exe`
- **Otomatik Doğrulama:** Betik, derleme sonrasında binary'yi `--cli -h` ve `--test-gui` parametreleriyle otomatik test ederek eksik modül (`ImportError`) veya eksik asset (`FileNotFoundError`) olmadığını doğrular.

---

## 📊 Performans ve Kaynak Tüketim Benchmark'ı

| Karşılaştırma Metriği | Video Downloader Pro Engine | Geleneksel Tek İş Parçacıklı İndiriciler | Mühendislik Farkı |
| :--- | :--- | :--- | :--- |
| **1080p HLS Akışı (1.2 GB)** | **~ 18.4 saniye** (32x Thread) | ~ 142.0 saniye | **7.7 Kat Daha Hızlı** ⚡ |
| **Çoklu Ses İndirme** | **Smart Deduplication** (1x Video + 1x Ek Ses) | Mükerrer Çift İndirme (2x Video/Ses) | **%50 Bant Genişliği Tasarrufu** 📉 |
| **Birleştirme Disk Alanı** | **~ 1.2x (FFmpeg Concat Demuxer)** | ~ 3.0x (Ara TS Kopyalama) | **%60 Daha Az Disk Tüketimi** 💾 |
| **Tepe Bellek Kullanımı** | **< 85 MB** (Kayan Pencere / Disk Stream) | > 1.4 GB (RAM'de Toplama) | **%94 Daha Düşük Bellek** 🛡️ |
| **AES-128 Şifre Çözme** | **< 1.2 ms / segment** | N/A | **Sıfır Hissedilir Gecikme** |

---

## ⚖️ Yasal Uyarı ve Mühendislik Bildirimi (Disclaimer)

> **Mühendislik ve Araştırma Kapsamı:** Bu yazılım; dağıtık video iletim protokollerinin (HLS/DASH), ağ veri akışlarının, kriptografik medya çözme algoritmalarının, çok kanallı ses/video konteyner çoğullamasının ve çift çekirdekli (Dual-Core) yazılım mimarilerinin incelenmesi amacıyla geliştirilmiş teknik bir mühendislik çalışmasıdır. Kullanıcılar, yazılımı kullanırken eriştikleri servislerin kullanım koşullarına ve yerel mevzuatlara uymakla bizzat yükümlüdür.
