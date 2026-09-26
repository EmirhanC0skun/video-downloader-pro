# Autonomous Core Operating System & Environment Discipline (VideoDownloaderPro Edition)

Daha yuksek oncelikli sistem, guvenlik veya platform talimatlariyla celismedigi surece; bu anayasa VideoDownloaderPro projesindeki TUM oturumlarda OTOMATIK OLARAK DEVREYE GIRER VE VARSAYILAN CALISMA STANDARDI OLARAK UYGULANIR.

---

## 1. 🔄 Dual-Core Sync Protocol (KRITIK ZORUNLULUK)
- Cekirdek motor cift lokasyonda yasar:
  - Masaustu: `engine.py`, `extractor.py` (Kok dizin)
  - Mobil APK: `android_app/core/engine.py`, `android_app/core/extractor.py`
- KURAL: Kok dizindeki `engine.py` veya `extractor.py` uzerinde yapilan her degisiklik, ANINDA `android_app/core/` altindaki karsiligina birebir kopyalanmalidir.
- `pytest tests/test_mobile_core_sync.py` calistirilip basarili oldugu gorulmeden gorev tamamlandi sayilamaz.

## 2. 🎬 FFmpeg Resolution Protocol
- FFmpeg sistem PATH'inde ARANMAZ. Korlemesine `where ffmpeg`, disk taramasi veya kullaniciya yol sorma islemi YAPILMAZ.
- KURAL: FFmpeg yolu yalnizca projenin yerel cozumu olan `engine.get_ffmpeg_path()` fonksiyonundan alinir (bu fonksiyon `imageio_ffmpeg` paketini referans alir).
- Tum subprocess komutlari ve test betikleri bu cagrildiktan sonra elde edilen binary yolunu kullanmalidir.

## 3. ⚡ Environment-Sentinel & Shell Disiplini
- NO BLIND SCANNING: Korlemesine surucu taramasi (`dir /s C:\`, `Get-ChildItem -Recurse C:\`) KESINLIKLE YASAKTIR.
- CONTEXT CONSERVATION: Ayni buyuk dosyalari gereksiz yere tekrar tekrar okumak yasaktir; hedefe yonelik metin aramalari, AST sembolleri ve kucuk kesitlerle calisilir. Gerekli baglam sart ise tam dosya incelenebilir.
- SHELL & ENCODING:
  - Windows PowerShell ortaminda `python -c "..."` ile tirnak/parantez kacis hatasi uretebilecek tek satirlik regex/kontrol betikleri calistirilmaz. Karma sik kontroller izole bir test/scratch `.py` dosyasi uzerinden yurutulur.
  - Test/repro betiklerinde baslangica `sys.stdout.reconfigure(encoding='utf-8')` eklenir. Konsola basilan log callback'lerinde emojiler (🇹🇷, 🎬, 🔄, 🔊) `cp1254` terminal cokmelerini onlemek icin korunur veya `ascii(errors='replace')` uygulanir.
- SECRET & ENV HYGIENE: Secret, token ve `.env` degerleri terminale veya loglara acikca basilamaz.
- ARTIFACT CLEANUP: Gorev bitiminde olusturulan gecici scratch/repro betikleri temizlenir.

## 4. 🔬 Systematic-Debugging & Silent Handlers Yasagi
- KOK NEDENI IZOLASYONLA BULMADAN RASTGELE DUZELTME YAPILAMAZ.
  1. Hata logu ve stack trace eksiksiz okunur.
  2. Problem tutarli sekilde yeniden uretilir (reproduce).
  3. Tek bir test edilebilir hipotez kurulup izole edilir.
- SILENT HANDLERS YASAKTIR: `except Exception: pass` gibi ciplak ve logsuz hata yakalayicilar YASAKTIR. Her exception en azindan `logger.debug(..., exc_info=True)` ile kaydedilmelidir; aksi halde `test_audit_regressions.py` aninda patlar.
- CIRCUIT BREAKER: Ayni kok probleme yonelik en fazla 3 anlamli hipotez denemesi yapilir. Cozulmuyorsa durulur, gecici eklenen denemeler temizlenir ve durum blocker olarak raporlanir.

## 5. 🛡️ Verification-Before-Completion & Headless GUI Siniri
- Degisikligin niteligine UYGUN dogrulama yapilmadan gorev tamamlandi denilemez:
  - Logic degisiklikleri: `pytest tests/` ile dogrulanir.
  - Mobil senkronizasyon: `pytest tests/test_mobile_core_sync.py` ile dogrulanir.
- HEADLESS GUI KURALI: Tkinter masaustu GUI arayuzu headless/CLI oturumlarinda gorsel olarak tiklanamaz. Kullanici "EXE'den indir" dediginde bu durum acikca belirtilerek GUI'nin arkada tetikledigi `engine.run_multi_audio_download(...)` motor fonksiyonu uzerinden tam indirme, muxing ve stream dogrulamasi yapilir.
- NO PLACEHOLDERS / NO TRUNCATION: Kod eksiltme (`...`, `// existing code`, `# rest of code`) KESINLIKLE YASAKTIR.
- NO FAKE-PASS MOCKING: Test edilen asil indirme veya cozumleme mantigi mock'lanamaz.
- INVENTED VALIDATION YASAKTIR: Calistirilmamis test dogrulanmis gibi gosterilemez.

## 6. 🗣️ Operational Transparency (Milestone Protocol)
- NO MICRO-ANNOUNCEMENTS: "Dosyayi okuyorum", "Metin ariyorum" gibi operasyonel adimlari anons etmek YASAKTIR.
- Yalnizca su durumlarda konusulur:
  1. Gorev baslangicinda 1-2 cumlelik yuksek seviye plan.
  2. Gercek blocker / breaking decision durumunda.
  3. Is tamamlandiginda asagidaki Rapor Sablonu ile.
- COMPLETION REPORT SCHEMA:
  - **Degisiklik:** (1–2 madde)
  - **Etkilenen Dosyalar:** (Masaustu ve android_app yollari)
  - **Dogrulama/Test:** (Pytest sonuclari, indirilen dosya boyutu, FFmpeg stream ozeti)
  - **Kalan / Calistirilamayan Dogrulamalar:** (Varsa GUI gorsel kontrolu, yoksa "Yok")

## 7. 🎯 Scope Discipline & Change Attribution
- Kullanici talebi disinda refactoring, paket guncellemesi veya keyfi temizlik yapilmaz.
- CONFLICT PROTOCOL: Calismaya baslamadan once `git status` referans alinir. Kullanici degisiklikleri ezilmez. Ayni satirda cakisma varsa uzerine yazilmaz, blocker olarak bildirilir.
- MINIMAL DIFF SURFACE: Ilgisiz formatlama ve whitespace degisiklikleri ile diff sisirilemez.
- COMMIT DISCIPLINE: Kullanici acikca istemedikce `git commit` veya `git push` yapilmaz.
- Gorev sonunda `git status` ve `git diff` incelenerek amac disi hicbir degisiklik birakilmaz.