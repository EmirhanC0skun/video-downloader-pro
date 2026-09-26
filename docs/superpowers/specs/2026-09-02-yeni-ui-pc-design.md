# Yeni PC Arayüzü — Tasarım Spesifikasyonu

**Tarih:** 2026-09-02
**Kapsam:** Masaüstü (`gui.py`, CustomTkinter). Android (Flet) ayrı bir çalışmada ele alınacak.
**Kaynak tasarım:** Claude Design projesi `51905517-45db-4316-bab6-3eab06863f99`, dosya `Yeni Tasarım.dc.html`
**Durum:** Onaylandı

---

## 1. Amaç

Mevcut 6 sekmeli `CTkTabview` arayüzünün yerine, tasarımda belirtilen **sol
sidebar + durum makineli içerik** düzenini kurmak. Motor, çözücü ve mobil
katmanlara dokunulmaz; yalnızca sunum katmanı değişir.

Tasarımın getirdiği üç yapısal fark:

1. **Navigasyon.** Üst sekmeler yerine 216px sol sidebar (6 öğe + canlı durum kartı).
2. **Durum makinesi.** İndirme sayfaları artık her şeyi aynı anda göstermez;
   `boş → çözümlendi → indiriliyor` olmak üzere üç ayrık duruma sahiptir.
3. **Sadeleştirme.** Uzman kontrolleri katlanabilir "Gelişmiş" panellerine iner.
   Hiçbir özellik kaldırılmaz.

## 2. Tasarım belirteçleri (token)

Doğrudan tasarım dosyasından alınmıştır.

### Renkler

| Rol | Değer | Kullanım |
|---|---|---|
| `BG_APP` | `#0A0D14` | Pencere zemini, input dolgusu, stat kutusu |
| `BG_SIDEBAR` | `#0D1119` | Sidebar, dropzone zemini |
| `BG_CARD` | `#11151F` | Kartlar, liste satırları |
| `BG_ELEVATED` | `#181D2A` | İkincil butonlar, rozetler, seçili segment |
| `BG_HOVER` | `#1F2536` | `BG_ELEVATED` üzerine hover |
| `BG_NAV_ACTIVE` | `#161C2B` | Sidebar'da seçili öğe |
| `BORDER` | `#1F232C` | `rgba(255,255,255,.06)`'nın `#11151F` üzerindeki katı karşılığı |
| `BORDER_STRONG` | `#1F242F` | `rgba(255,255,255,.08)` — input kenarlığı |
| `TEXT` | `#F1F5F9` | Birincil metin |
| `TEXT_MUTED` | `#8A94A8` | İkincil metin |
| `TEXT_DIM` | `#5B6478` | Üçüncül / pasif metin |
| `TEXT_CHIP` | `#B6BECD` | Seçili olmayan pill metni |
| `PRIMARY` | `#3B82F6` | Ana eylem, progress, aktif ikon |
| `PRIMARY_HOVER` | `#2F74EA` | |
| `PRIMARY_LIGHT` | `#60A5FA` | Link, aktif nav ikonu |
| `PRIMARY_TINT` | `#93C5FD` | Seçili pill metni, rozet metni |
| `SUCCESS` | `#22C55E` | İndir butonu, tamamlandı |
| `SUCCESS_HOVER` | `#2BD46B` | |
| `SUCCESS_INK` | `#052E16` | Yeşil buton üzerindeki metin |
| `DANGER` | `#F87171` | İptal, temizle |
| `WARNING` | `#FBBF24` | Hız göstergesi, pil uyarısı |
| `PURPLE` | `#8B5CF6` | Dönüştürücü |
| `PURPLE_LIGHT` | `#A78BFA` | |

**Alfa notu.** Tkinter alfa kanalı desteklemez. Tasarımdaki
`rgba(255,255,255,.06)` gibi değerler, üzerine bindikleri zemine göre
düzleştirilir. Bu değerler elle yazılmaz; `theme.over(katman, zemin, alfa)`
hesaplar. Zemin rengi değişirse türetilmiş her renk onunla birlikte kayar ve
elle güncellenmesi gereken bir liste kalmaz.

### Tipografi

- **Manrope** — 500 / 600 / 700 / 800. Tüm arayüz metni.
- **JetBrains Mono** — 500 / 600. Rakamlar: yüzde, hız, süre, boyut, rozet, saat.
- Boyut merdiveni: 11 / 11.5 / 12 / 12.5 / 13 / 13.5 / 14 / 15 / 16 / 17 / 40.

### Yarıçap ve boşluk

`RADIUS`: kart 16, kart-küçük 12/14, input 12, buton 12, pill 17 (999px
karşılığı), rozet 6-10. `GAP`: 6 / 8 / 10 / 12 / 14 / 16 / 20 / 22 / 28.

## 3. Mimari

Seçilen yaklaşım: **hibrit**. Sunum primitifleri yeni modüllere çıkar, iş
mantığı `gui.py` içinde yerinde kalır.

```
ui/
  theme.py    — renk, boyut, yarıçap, font adı sabitleri
  fonts.py    — TTF'leri Tk açılmadan önce süreç-özel yükler, fallback yönetir
  icons.py    — mantıksal ikon adı → glyph eşlemesi
  widgets.py  — Card, Pill, PrimaryBtn, GhostBtn, DangerBtn, StatTile,
                ListRow, Segmented, Toggle, SidebarItem, Progress, Collapsible
gui.py        — VideoDownloaderGUI: shell + sayfalar + tüm mevcut iş mantığı
```

**Neden bu sınır.** `ui/` altındaki her şey saf sunumdur: motor bilmez, iş
parçacığı başlatmaz, ağ görmez. Bu sayede bağımsız test edilebilir ve
`gui.py`'nin şişmesini engeller. Sayfa kurulumu `gui.py`'de kalır çünkü her
sayfa kendi handler'larına ve widget referanslarına sıkı bağlıdır; oraya
taşımak `self.` referanslarını dolaylı hale getirir ve mevcut 3278 satırlık iş
mantığını kırma riski doğurur.

### Font yükleme

`ui/fonts.py`, `AddFontResourceExW(path, FR_PRIVATE, 0)` ile TTF'leri **Tk
kökü oluşturulmadan önce** sürece kaydeder — sisteme kurulum gerekmez. Tk
font tablosunu başlangıçta oluşturduğu için sıralama zorunludur.

Yüklenemezse (dosya yok, API başarısız, Windows dışı) `ui/theme.py`
fallback'e düşer: `Segoe UI Variable Display` → `Segoe UI`, `Consolas`,
ikonlar için metin etiketi. Arayüz çalışmaya devam eder.

### İkonlar

Tasarımın SVG path'leri Tk'de çizilemez. Yerine **Material Symbols Rounded**
TTF gömülür; `ui/icons.py` mantıksal adları glyph'lere eşler:

`film · play · list · folder · convert · settings · music · link · paste ·
download · pause · cancel · check · search · bell · battery · image ·
chevron · dots · folder_open · plus`

Glyph çözünürlükten bağımsız keskin kalır ve `text_color` ile renklenir.

## 4. Ekran düzeni

```
┌──────────────┬────────────────────────────────────────────┐
│ ⚡ Video      │  Film & Web                    📁 Masaüstü │  64px başlık
│    Downloader│  Film ve dizi sitelerinden indir           │
│    Pro · v3  ├────────────────────────────────────────────┤
│              │                                            │
│ ▸ Film & Web │   ┌──────────────────────────────────┐     │
│   Sosyal M.  │   │  Film veya dizi linki            │     │  içerik
│   Kuyruk  ③  │   │  [ 🔗 …          ] [Yapıştır][Çöz]│     │  max 800px
│   İndirilen. │   │  ① Yapıştır › ② Çözümle › ③ İndir │     │
│   Dönüştürü. │   └──────────────────────────────────┘     │
│   Ayarlar    │                                            │
│              │   SON İNDİRİLENLER          Tümünü gör     │
│ ┌──────────┐ │   ┌──────────────────────────────────┐     │
│ │● Hazır   │ │   │ 🎬 Interstellar…  Oynat  Tekrar  │     │
│ │ Ağ kor.. │ │   └──────────────────────────────────┘     │
│ └──────────┘ │                                            │
└──────────────┴────────────────────────────────────────────┘
   216px
```

Pencere 1100×700, minimum 980×640. İçerik sütunu 800px'te sabitlenir,
pencere genişlerse sola yaslı kalır (tasarımdaki `max-width:800px`).

### Sidebar durum kartı

Alt köşedeki kart uygulamanın canlı nabzıdır ve hangi sayfada olursanız olun
görünür:

| Durum | Nokta | Başlık | Alt satır |
|---|---|---|---|
| Boşta | `SUCCESS` | `Hazır` | `Ağ koruması aktif` |
| İndiriliyor | `PRIMARY` | `İndiriliyor · %46` | `24.6 MB/s · 01:02 kaldı` |
| Hata | `DANGER` | `Hata` | kısaltılmış mesaj |

Mevcut `_set_status()` ve `_tick_progress_ui()` bu kartı besleyecek şekilde
yeniden bağlanır.

## 5. Sayfalar

| # | Sidebar | Mevcut kaynak | Not |
|---|---|---|---|
| 0 | Film & Web | `_build_film_tab` | 3 durumlu |
| 1 | Sosyal Medya | `_build_youtube_tab` | 3 durumlu, KALİTE yerine BİÇİM |
| 2 | Kuyruk | `_build_queue_tab` | rozet = bekleyen öğe sayısı |
| 3 | İndirilenler | `_build_history_tab` | yeniden tasarlandı, aşağıya bak |
| 4 | Dönüştürücü | `_build_converter_tab` | dropzone + mor pill'ler |
| 5 | Ayarlar | `_build_settings_tab` | satır listesi + toggle + segment |

### 5.1 Film & Web / Sosyal Medya — durum makinesi

Üç durum aynı anda kurulur, `grid_remove()` / `grid()` ile değiştirilir.
Yeniden kurulum yapılmaz; widget referansları sabit kalır, böylece arka plan
iş parçacıklarından gelen `after(0, …)` güncellemeleri hedefini şaşırmaz.

**`boş`** — link kartı (etiket, input, Yapıştır, Çözümle), `① › ② › ③` adım
göstergesi, sağda "Gelişmiş" açar; altında SON İNDİRİLENLER listesi
(`history.py`'den son 3 kayıt).

**`çözümlendi`** — çözülen URL şeridi (✓ + kısaltılmış URL + "Değiştir"),
medya kartı: küçük önizleme kutusu, başlık, mono meta rozetleri
(`1080p · 2 ses kanalı · 1042 parça · ~1.9 GB`), KALİTE pill'leri,
SES/BİÇİM pill'leri, ayırıcı, yeşil **İndir** + **Sıraya ekle** + kayıt yeri.

**`indiriliyor`** — başlık + alt satır, sağda 40px mono yüzde; 8px progress;
dört stat kutusu (HIZ `WARNING` renkli, KALAN, GEÇEN, BOYUT); Duraklat +
İptal + bildirim notu; altında katlanabilir **İşlem günlüğü** (mevcut log
metin kutusu, satır sayısı rozetiyle).

Durum geçişleri mevcut akışa bağlanır: `_resolve_*_threaded` başarısı →
`çözümlendi`; `_begin_download_ui` → `indiriliyor`; `_reset_ui` / `_cancel_*`
→ `boş`.

### 5.2 İndirilenler

Eski "Geçmiş" sekmesinin yerini alır. Arama kutusu + `Tümü / Video / Ses`
segment filtresi + `N dosya · X GB` özeti + satırlar
(tür ikonu, başlık, `boyut · tarih · tür`, **Oynat** / **Tekrar indir** /
**Konum**). `history.py` API'si değişmez; filtreleme ve toplam boyut
hesabı sunum katmanında yapılır.

### 5.3 Gelişmiş panelleri

`Collapsible` widget'ı, varsayılan kapalı. Mevcut kontrollerin tamamı korunur:

| Sayfa | Gelişmiş içeriği |
|---|---|
| Film & Web | cURL içe aktar, kanal sayısı slider'ı, alt yazı seçimi, ses kanalı seçimi, DPI/ağ koruması durumu |
| Sosyal Medya | tarayıcı çerezleri, çerez dosyası, biçim/kalite detayları, hedef klasör |
| Kuyruk | bölüm aralığı ile ekleme, tüm bölümleri tara |
| Ayarlar | hız ön ayarı, bitince kapat, bildirim sesi, kayıt yolu |

## 6. Etkilenen dosyalar

```
YENİ    ui/__init__.py, ui/theme.py, ui/fonts.py, ui/icons.py, ui/widgets.py
YENİ    assets/fonts/*.ttf
YENİ    tests/test_ui_widgets.py
DEĞİŞ   gui.py                     sunum katmanı; handler'lar yerinde
DEĞİŞ   VideoDownloaderPro.spec    hiddenimports: ui.*  ·  datas: assets
DEĞİŞ   tests/test_gui_ux.py       tabview → sidebar router
DEĞİŞ   README.md
SABİT   engine.py, extractor.py, extractors/, sniffer.py, history.py,
        logger.py, exceptions.py, downloader.py, android_app/, tools/
```

Çekirdek modüllere dokunulmadığı için `tools/sync_mobile_core.py`
çalıştırılmasına gerek yoktur; `test_C1_mobile_core_is_in_sync_with_desktop`
etkilenmez.

## 7. Test stratejisi

**Yeni — `tests/test_ui_widgets.py`.** `ui/` saf sunum olduğu için doğrudan
test edilir: token bütünlüğü (her rengin geçerli hex olması), ikon
eşlemesinin eksiksizliği, font fallback'inin TTF yokken çökmemesi,
`Segmented`/`Toggle`/`Collapsible` durum geçişleri.

**Güncellenen — `tests/test_gui_ux.py`.** 16 testin tamamı korunur, davranış
iddiaları aynı kalır; yalnızca widget adresleri yeni yapıya taşınır
(`self.app.tabview.set(...)` → `self.app._show_page(i)`). Durum makinesi
için üç yeni iddia eklenir: çözümleme sonrası `çözümlendi`, indirme
başlayınca `indiriliyor`, iptal sonrası `boş`.

**Değişmeyen.** `test_engine`, `test_audit_regressions`, `test_mock_*`,
`test_modular_extractors`, `test_mobile_*` — bu iş onlara dokunmaz ve
geçmeye devam etmelidir.

## 8. Bilinen sınırlar

Tkinter'ın yapamadıkları ve seçilen telafiler:

| Tasarımda | Uygulamada |
|---|---|
| `linear-gradient` progress | Düz `PRIMARY` dolgu |
| `box-shadow` | Yok; hover'da renk açılmasıyla derinlik hissi |
| `rgba()` kenarlık ve tint | Zemine göre önceden hesaplanmış katı renk |
| SVG path ikonlar | Material Symbols Rounded glyph'leri |
| CSS geçiş animasyonları | Anlık durum değişimi |

Bu sapmalar kabul edilmiştir; layout, palet, tipografi hiyerarşisi, durum
akışı ve bileşen yapısı tasarıma sadık kalır.

## 9. Uygulama sırasında ortaya çıkanlar

**`pytest` fd-capture'ı Tk'yi bozuyordu.** Çalışmaya başlarken 16 GUI testinin
tamamı `TclError: Can't find a usable init.tcl` ile hata veriyordu. Neden
eksik bir Tcl kurulumu değil, `pytest`'in varsayılan `--capture=fd` kipiydi:
dosya tanıtıcılarını değiştirmesi Tcl'in `init.tcl` okumasını engelliyor.
`pytest.ini`'ye `--capture=sys` eklendi; testler o düzeltmeden önce zaten
kırıktı, yani gerçek baseline 116/116'ydı.

**Açılır menüler pill'e çevrilirken sözleşme korundu.** Kalite ve ses
seçenekleri `gui.py` içinde 25'ten fazla yerde `CTkOptionMenu` gibi kullanılır
(`configure(values=…)`, `set()`, `get()`, `cget("values")`). Görseli tasarımın
pill'lerine taşımak için `ui.widgets.OptionPills` aynı sözleşmeyi uygular ve
tam değeri saklarken ekranda kısaltılmış etiket gösterir
(`🎬 1080p (1042 Parça)` → `1080p` + `1042 Parça`). Böylece hiçbir çağrı yeri
değişmedi.

**Türkçe büyük harf.** `str.upper()` `i` harfini `I` yapar; bölüm başlıkları
büyük harf olduğu için bu ekranda doğrudan görünüyordu ("SON INDIRILENLER").
`widgets.upper_tr()` doğru dönüşümü yapar.

**Fontlar üretilerek gömülüyor.** Manrope yalnızca değişken font olarak
yayımlanıyor ve GDI değişken fonttan tek örnek çizdiği için istenen dört
ağırlık `fontTools.varLib.instancer` ile statik dosyalara ayrıştırıldı.
Material Symbols 14 MB'lık kaynağından 46 glyph'e indirgendi. Üçü birlikte
`tools/build_ui_fonts.py` ile üretilir; toplam **295 KB**.

## 10. Bitiş akışı

`AGENTS.md`'deki Definition of Done uygulanır: `python -m pytest` →
README güncellemesi → `python build_exe.py` → **tek commit ve tek push**.
