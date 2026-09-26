# 📱 Video Downloader Pro - Android Mobile & Flet App

Google Flutter ve **Flet (Material 3)** mimarisiyle geliştirilmiş, Android mobil cihazlar için optimize edilmiş modern medya indirme uygulaması.

---

## 🌟 Mobil v2.8.0 Özellikleri (Masaüstü ile 1:1 Tam Eşleşme)

1. **Material 3 Tasarım Dili & AppBar (Dark OLED):**
   - Modern Material 3 başlık çubuğu (`v2.8.0` Cyan rozeti, Canlı `● HAZIR` durumu ve `⚙️ Ayarlar` butonu).
   - Dokunmatik odaklı alt gezinme çubuğu (**BottomNavigationBar**).
   - Reaktif ilerleme çubukları, yüksek kontrastlı canlı Kalan Süre (`#38BDF8` Cyan) ve Anlık Hız (`#FBBF24` Amber) sayaçları.
2. **🧠 Akıllı Sihirli Yönlendirici (Smart Magic Router):**
   - Film sekmesine YouTube/Instagram veya Sosyal sekmesine Dizi/Film linki yapıştırıldığında ilgili sekmeye anında otomatik aktarım ve çözümleme.
3. **🎬 Film & Web Medya Çözümleyici:**
   - 🇹🇷 Türkçe Dublaj, 🇬🇧 Altyazılı ve 🌟 Çift Sesli (Tek MP4) akış seçimi.
   - Otomatik altyazı tespiti (`.vtt` ➔ `.srt`) ve video içine soft-sub gömme.
   - İndirme tamamlandığında doğrudan `▶ Videoyu Oynat` kısayolu.
4. **📺 YouTube & Sosyal Medya (Dinamik Çözümleme + Çerezler + Duraklat/Devam):**
   - `🔍 Medyayı Çözümle` butonuyla videoda gerçekten sunulan çözünürlükleri (`4K 2160p`, `2K 1440p`, `1080p FHD`, `720p`, `480p`, `360p`, `MP3 320k`, `M4A`) anlık sorgulama.
   - İndirme anında `⏸️ Duraklat` ve `▶️ Devam Et` kontrolü.
   - Instagram ve kilitli videolar için `cookies.txt` oturum desteği.
   - Evrensel AAC ses dönüştürme (Windows Media Player, VLC ve Mobil oynatıcı uyumlu).
5. **📋 Dizi & Toplu İndirme Kuyruğu (Queue Engine):**
   - `🌟 Tüm Bölümleri Tara & Sıraya Ekle` ile tüm sezonları tek tıkla otomatik ekleme.
   - Akıllı Kuyruk Duraklatma (`⏸️ Duraklat` ➔ `▶️ Devam Et` dinamik toggle).
   - Kuyruktaki her öğe için tekil iptal (`⏹️`), yeniden sıraya alma (`🔄`) ve silme (`🗑️`).
   - Tamamlanan tüm indirmelerin Android Galerisine (`MediaScanner`) ve SQLite Geçmişine anında senkronizasyonu.
6. **🎙️ Medya Dönüştürücü (Converter):**
   - FFmpeg ve Pure-Python hibrit ses ayıklama ve format dönüştürme (MP3 320k, MP4, MKV, WAV).
7. **📁 İndirilenler & Geçmiş Kütüphanesi:**
   - Canlı arama (`txt_search`), tek tıkla oynatma (`▶ Oynat`), silme ve tek tıkla yeniden indirme/çözümleme (`🔄 Tekrar`).
8. **⚙️ Mobil Ayarlar & Hız Profilleri:**
   - Hız profilleri (`⚡ Dengeli 4x`, `⚡ Hızlı 8x`, `⚡ Maksimum 16x`, `⚡ Turbo 32x`), DoH ve TLS parmak izi koruması.

---

## 🚀 Çalıştırma ve Test (Geliştirme Modu)

Mobil uygulamayı bilgisayarınızda önizleme ve test modunda çalıştırmak için:

```bash
cd android_app
python main.py
```
veya
```bash
flet run android_app
```

---

## 📦 Android APK Derleme (Build APK)

Android cihazınızda (`.apk`) olarak kurup kullanmak için Flet build komutunu çalıştırabilirsiniz:

```bash
cd android_app
flet build apk
```

> **Not:** Derleme tamamlandığında üretilen `.apk` dosyası `android_app/build/apk/` klasörü altına yerleştirilir ve doğrudan Android cihazlara yüklenebilir.
