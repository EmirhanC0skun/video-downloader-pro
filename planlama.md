# Video Downloader Pro — Teknik Geliştirme Planı

> **Durum:** Eleştirel teknik değerlendirme ve yol haritası  
> **Amaç:** Mevcut çalışan sistemi bozmak yerine; test edilebilirlik, sürdürülebilirlik, ölçülebilir performans, güvenlik ve profesyonel yazılım mimarisi açısından bir üst seviyeye taşımak.

---

## 1. Genel Teknik Değerlendirme

### Mevcut seviye

Bu proje basit bir `URL → yt-dlp → dosya` downloader değildir. Mevcut yapı; doğrudan medya dosyaları, yt-dlp tabanlı platformlar, özel extractor'lar, HLS/M3U8 akışları, Playwright tabanlı ağ dinleme, FFmpeg mux/dönüşüm, altyazı, çoklu ses, kuyruk, GUI, CLI ve Android taraflarını bir araya getiren hibrit bir medya indirme sistemi oluşturmaktadır.

### Genel değerlendirme

| Alan | Değerlendirme |
|---|---:|
| Mimari fikir | 9/10 |
| Kod organizasyonu | 7.5/10 |
| Downloader engine | 8.5/10 |
| Extractor sistemi | 8.5/10 |
| GUI/UX | 8.5/10 |
| Hata yönetimi | 6.5/10 |
| Test altyapısı | 5/10 |
| Güvenlik | 6.5/10 |
| Performans | 8/10 |
| Dokümantasyon | 8/10 |
| Maintainability | 6.5/10 |
| Portföy değeri | 9/10 |

**Genel teknik seviye: yaklaşık 7.8–8.0/10.**

Bu puan mevcut kapsamı ve öğrenci projesi bağlamını dikkate alır. Production-ready değerlendirmesinde puan daha düşüktür; çünkü sistemin karmaşıklığı ile test, gözlemlenebilirlik ve mimari disiplin henüz aynı seviyede değildir.

---

# 2. Güçlü Yönler

## 2.1. Hibrit çözüm/fallback yaklaşımı

Projenin en güçlü mimari fikri tek bir indirme yöntemine bağımlı olmamasıdır.

Kabaca:

```text
URL
 │
 ├── Direct media
 ├── Known platform / yt-dlp
 ├── Custom extractor
 ├── HLS / M3U8
 └── Browser / network sniffer
          │
          ▼
      Download Engine
          │
          ▼
        FFmpeg
```

Bir yöntem başarısız olduğunda başka bir yönteme geçilebilmesi, gerçek dünya web medyası için mantıklı bir tasarımdır.

**Korunmalı.** Bu yaklaşım projenin ayırt edici tarafıdır.

## 2.2. Downloader engine

Segment tabanlı indirme, paralel çalışma, retry, `.part` dosyası, cancellation ve progress callback gibi mekanizmalar ciddi mühendislik düşüncesi gösteriyor.

Özellikle geçici dosya → tamamlanınca final dosyasına geçiş yaklaşımı yarım indirme durumlarında faydalıdır.

## 2.3. GUI

GUI yalnızca bir input ve Download butonundan oluşmuyor. Queue, progress, hız, boyut, history, converter ve farklı medya akışları gibi kullanıcı açısından anlamlı bileşenler bulunuyor.

## 2.4. CLI + GUI

Aynı sistemin GUI ve CLI üzerinden kullanılabilmesi iyi bir ayrım yönüdür. UI'nin downloader motorunun kendisi olmaması ileride daha temiz bir application/service katmanına geçişi kolaylaştırabilir.

## 2.5. Çoklu ses ve altyazı

HLS audio tracks, VTT/SRT ve player metadata gibi ayrıntıların ele alınması projeyi sıradan downloader scriptlerinden ayırıyor.

## 2.6. FFmpeg fallback yaklaşımı

Sistemde FFmpeg'in bulunması ve gerektiğinde Python paketinden gelen FFmpeg binary'sine fallback yapılması kullanıcı kurulum deneyimini iyileştiriyor.

## 2.7. Cross-platform hedef

Windows masaüstü yanında Android/Flet tarafının düşünülmesi projenin portföy değerini artırıyor.

## 2.8. Repository hygiene

`.gitignore` içerisinde virtual environment, build çıktıları, medya dosyaları ve geçici indirme dosyalarının düşünülmüş olması olumlu.

---

# 3. Kritik Eksikler

## 3.1. Extractor katmanı fazla büyüyor

`extractor.py` çok fazla sorumluluğu tek dosyada toplamaya müsait:

- şifre çözme
- platform tespiti
- özel site çözümleme
- HLS çözümleme
- Dailymotion
- yt-dlp
- iframe/player çözümleme
- Playwright fallback

Bu yapı kısa vadede hızlı geliştirme sağlar; uzun vadede ise dosyanın büyümesine ve değişikliklerin birbirini etkilemesine neden olur.

### Hedef

İleride:

```text
extractors/
├── youtube.py
├── dailymotion.py
├── rapidvid.py
├── generic_hls.py
├── film_sites.py
└── registry.py
```

gibi bir extractor registry yaklaşımı değerlendirilmelidir.

**Öncelik: Yüksek.**

---

## 3.2. Regex ile HTML/JavaScript ayrıştırma kırılgan

Birçok extractor regex ile HTML/JS yapısını tanıyor. Bu hızlı ve pratik; fakat hedef sitelerin frontend kodu değiştiğinde kolayca kırılabilir.

Özellikle:

```text
HTML
JavaScript
JWPlayer config
M3U8 metadata
```

için parser/structured data yaklaşımı mümkün olduğunda tercih edilmelidir.

Regex tamamen kaldırılmak zorunda değildir; ancak kritik extraction yollarında fallback stratejisi bulunmalıdır.

**Öncelik: Orta-Yüksek.**

---

## 3.3. Test altyapısı en büyük eksiklerden biri

Projenin kapsamı büyümüş olmasına rağmen otomatik testlerin kapsamı bu büyüklüğü henüz karşılamıyor.

Öncelikle pure function'lar test edilmelidir:

```text
parse_segment_url()
build_segment_url()
parse_curl_command()
vtt_to_srt()
decrypt_cryptojs_aes()
extract_playlist()
```

Daha sonra mocked HTTP responses ile extractor testleri ve integration testleri eklenmelidir.

### Hedef test katmanları

```text
Unit Tests
   ↓
Extractor Tests
   ↓
Downloader Integration Tests
   ↓
End-to-End Tests
```

**Öncelik: Çok yüksek.**

---

## 3.4. 16/32 paralel indirme için benchmark gerekli

"16 kanal" veya yüksek concurrency desteği tek başına performans kanıtı değildir.

Ölçülmesi gerekenler:

- 1 thread
- 2 thread
- 4 thread
- 8 thread
- 16 thread
- 32 thread

ve her seviyede:

- MB/s
- toplam süre
- CPU kullanımı
- RAM kullanımı
- disk kullanımı
- hata/timeout oranı

ölçülmelidir.

Özellikle daha fazla thread'in her zaman daha hızlı olmadığı unutulmamalıdır. Sunucu throttling'i, network congestion ve disk I/O darboğaz olabilir.

### Hedef

Benchmark sonucu README'ye tablo olarak eklenmelidir.

**Öncelik: Yüksek.**

---

## 3.5. Adaptive concurrency değerlendirilmeli

Sabit concurrency yerine ileride basit bir adaptive sistem düşünülebilir:

```text
başlangıç
   ↓
ölçülen throughput
   ↓
concurrency artır/azalt
   ↓
429 / timeout artarsa azalt
```

Bu, "32 thread destekliyor" yaklaşımından daha mühendislik odaklıdır.

**Öncelik: Orta.**

---

## 3.6. `except Exception: pass` kullanımı azaltılmalı

Beklenmeyen hataların tamamen yutulması debug ve bakım maliyetini artırır.

Daha doğru yaklaşım:

```text
Beklenen hata
    ↓
kontrollü handling

Beklenmeyen hata
    ↓
log + context + gerektiğinde propagate
```

Özellikle extractor ve sniffer tarafında hangi fallback'in neden devreye girdiğinin loglanması önemlidir.

**Öncelik: Yüksek.**

---

## 3.7. Logging sistemi güçlendirilmeli

`print()` ve callback tabanlı loglama yerine standart Python `logging` altyapısı değerlendirilmeli.

Örnek:

```text
DEBUG
INFO
WARNING
ERROR
CRITICAL
```

Ayrıca component bazlı logger kullanılabilir:

```text
video_downloader.extractor
video_downloader.sniffer
video_downloader.engine
video_downloader.gui
```

Böylece kullanıcı log seviyesi ile geliştirici debug logları ayrılabilir.

**Öncelik: Yüksek.**

---

## 3.8. History yazımı concurrency açısından güçlendirilmeli

JSON history dosyası küçük bir uygulama için yeterlidir; ancak birden fazla downloader thread'i aynı anda history yazarsa lost update ihtimali oluşabilir.

İleride:

- lock
- atomic write
- SQLite

gibi çözümler değerlendirilebilir.

SQLite özellikle history büyüdüğünde daha sağlam bir çözüm olacaktır.

**Öncelik: Orta.**

---

## 3.9. Dependency locking eksik

`requirements.txt` içinde çoğunlukla minimum sürümler kullanılması gelecekte reproducibility problemi yaratabilir.

Örneğin yt-dlp'nin yeni bir sürümü davranış değiştirebilir.

### Hedef

En azından production/release ortamı için kilitlenmiş dependency seti tutulmalı.

Alternatifler:

- pip-tools
- uv
- Poetry
- lock file yaklaşımı

**Öncelik: Orta-Yüksek.**

---

## 3.10. README'deki "doğrulandı" ifadeleri tarihli hale getirilmeli

Platform desteği web sitelerinin değişmesine bağlıdır. Bu nedenle sadece:

```text
Doğrulandı
```

demek yerine:

```text
Platform | Last Tested | Quality | Status
```

gibi bir tablo daha profesyoneldir.

Örnek:

```text
YouTube      | 2026-08-20 | 1080p | PASS
Dailymotion  | 2026-08-20 | 1080p | PASS
```

Bu aynı zamanda gelecekte regression takibini kolaylaştırır.

**Öncelik: Orta.**

---

## 3.11. Cookie/Header güvenliği açıkça belgelenmeli

Cookie, Authorization, Referer ve Origin gibi bilgileri desteklemek güçlü bir özelliktir; fakat bunlar hassas kimlik doğrulama verileri olabilir.

README'de açık uyarı bulunmalıdır:

> Cookie, Authorization veya kişisel oturum bilgilerini GitHub'a, issue'lara veya başkalarına göndermeyin.

Ayrıca cookie dosyaları için `.gitignore` kuralları açıkça kontrol edilmelidir.

**Öncelik: Yüksek.**

---

# 4. Mimari Borç

Mevcut sistem işlevsel olarak güçlü fakat bazı katmanlar birbirine fazla bağlı.

Uzun vadeli hedef mimari:

```text
                 GUI / CLI / Android
                         │
                         ▼
                Application Service
                         │
             ┌───────────┴───────────┐
             ▼                       ▼
       Extractor Registry       Download Queue
             │                       │
             ▼                       ▼
       Media Resolver          Download Engine
                                     │
                                     ▼
                                  FFmpeg
                                     │
                                     ▼
                              Output / History
```

Burada UI'nin doğrudan implementation detaylarını bilmesi azaltılır.

Amaç "daha fazla abstraction" yapmak değil; değişen bir parçanın diğer parçaları mümkün olduğunca az etkilemesini sağlamaktır.

---

# 5. Önerilen Geliştirme Sırası

## Faz 0 — Koruma ve ölçüm

- [ ] Mevcut çalışan sürümü baseline olarak işaretle
- [ ] Mevcut davranışları belgeleyerek regression listesi oluştur
- [ ] Platform test matrisi oluştur
- [ ] Benchmark metodolojisi belirle

**Amaç:** Çalışan sistemi refactor sırasında kaybetmemek.

---

## Faz 1 — Test altyapısı

- [ ] `tests/` yapısını oluştur
- [ ] Pure function unit testleri
- [ ] Extractor parsing testleri
- [ ] Mock HTTP response testleri
- [ ] Downloader integration testleri
- [ ] Kritik edge-case testleri

**Başarı kriteri:** Kritik resolver/downloader fonksiyonları regression testleri ile korunuyor.

---

## Faz 2 — Logging ve hata yönetimi

- [ ] `logging` altyapısı
- [ ] Component bazlı logger
- [ ] Exception sınıfları
- [ ] Fallback nedenlerinin loglanması
- [ ] `except Exception: pass` noktalarının gözden geçirilmesi
- [ ] Kullanıcı hatası ile geliştirici hatasının ayrılması

**Başarı kriteri:** Bir download neden başarısız oldu sorusunun loglardan cevaplanabilmesi.

---

## Faz 3 — Performans benchmark'ı

- [ ] 1/2/4/8/16/32 concurrency testi
- [ ] Throughput ölçümü
- [ ] CPU/RAM ölçümü
- [ ] Disk I/O ölçümü
- [ ] Timeout/retry oranı
- [ ] Sonuçları README'ye ekleme

**Başarı kriteri:** Concurrency iddiaları ölçülebilir verilere dayanıyor.

---

## Faz 4 — Extractor modularizasyonu

- [ ] Büyük extractor dosyasını mantıksal parçalara ayır
- [ ] Ortak interface/protocol tanımla
- [ ] Extractor registry oluştur
- [ ] Platform detection katmanını ayır
- [ ] Generic HLS resolver oluştur

**Başarı kriteri:** Yeni bir extractor eklemek mevcut extractor kodunu değiştirmeyi gerektirmiyor.

---

## Faz 5 — History ve persistence

- [ ] JSON history için atomic write
- [ ] Thread-safe access
- [ ] Gerekirse SQLite'a geçiş
- [ ] Migration stratejisi

**Başarı kriteri:** Paralel indirmelerde history kaybı oluşmuyor.

---

## Faz 6 — Dependency ve release yönetimi

- [ ] Dependency lock
- [ ] Version compatibility matrix
- [ ] Windows build testi
- [ ] Android build testi
- [ ] Clean-machine installation testi
- [ ] Release checklist

**Başarı kriteri:** Temiz bir bilgisayarda dokümantasyondaki adımlarla kurulup çalışıyor.

---

## Faz 7 — Dokümantasyon ve portföy kalitesi

- [ ] Mimari diyagram
- [ ] Architecture Decisions bölümü
- [ ] Test sonuçları
- [ ] Benchmark tablosu
- [ ] Platform compatibility matrix
- [ ] Security notes
- [ ] Known limitations
- [ ] Roadmap
- [ ] Release notes

**Başarı kriteri:** Proje sadece çalışan kod değil, teknik olarak savunulabilir bir mühendislik ürünü olarak sunulabiliyor.

---

# 6. Öncelik Matrisi

| İş | Etki | Zorluk | Öncelik |
|---|---|---|---|
| Unit/integration tests | Çok yüksek | Orta | **P0** |
| Logging sistemi | Yüksek | Düşük-Orta | **P0** |
| Exception handling temizliği | Yüksek | Orta | **P0** |
| Benchmark | Yüksek | Orta | **P0** |
| Cookie/security dokümantasyonu | Yüksek | Düşük | **P0** |
| Extractor modularizasyonu | Çok yüksek | Yüksek | **P1** |
| Dependency locking | Orta-Yüksek | Düşük | **P1** |
| History concurrency | Orta | Düşük-Orta | **P1** |
| Adaptive concurrency | Orta | Yüksek | **P2** |
| Büyük mimari refactor | Yüksek | Çok yüksek | **P2** |

---

# 7. Yapılmaması Gerekenler

Bu proje için bundan sonraki aşamada aşağıdaki yaklaşım tercih edilmemeli:

### 7.1. Sadece yeni platform eklemek

Her yeni platform mevcut mimari borcu büyütebilir.

Önce extractor sisteminin sınırları temizlenmeli.

### 7.2. Daha fazla thread eklemek

32 → 64 → 128 thread yaklaşımı tek başına performans mühendisliği değildir.

Önce benchmark.

### 7.3. Her hatayı `except Exception: pass` ile kapatmak

Çalışıyor gibi görünür fakat sistemin gerçek durumunu gizler.

### 7.4. Büyük refactor'ı testsiz yapmak

Mevcut proje zaten çok sayıda fallback içerdiği için testsiz refactor regression riskini ciddi biçimde artırır.

### 7.5. README'de ölçülmemiş performans iddiaları yapmak

"16 kanal", "çok hızlı", "tüm platformlar desteklenir" gibi ifadeler mümkün olduğunca ölçüm ve tarih ile desteklenmelidir.

---

# 8. Son Hedef

Projenin hedefi sadece:

> "Çok sayıda siteden video indirebilen bir uygulama"

olmamalıdır.

Daha güçlü hedef:

> **Test edilebilir, ölçülebilir, modüler, güvenilir ve cross-platform bir medya indirme altyapısı geliştirmek.**

Bu hedefe ulaşıldığında proje öğrenci projesi olmaktan çıkıp güçlü bir software engineering portfolio project seviyesine yaklaşır.

---

# 9. Son Eleştiri

Projenin en güçlü tarafı **problem çözme kapsamı ve fallback düşüncesidir.**

En büyük zayıflığı ise **sistemin büyüme hızının test, logging, dependency management ve modular architecture disiplininden daha hızlı olmasıdır.**

Başka bir deyişle:

```text
Şu ana kadar:

özellik üretme  ████████████████████
mühendislik     ████████████████

Bir sonraki aşamada:

özellik üretme  ████████████████████
test            ██████████████████
mimari          █████████████████
ölçüm           █████████████████
observability   ████████████████
```

Artık projenin ihtiyacı daha fazla özellikten çok **kontrollü karmaşıklık yönetimidir.**

Bu planın temel amacı da budur.
