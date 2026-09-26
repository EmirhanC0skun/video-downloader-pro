# -*- coding: utf-8 -*-
"""Video Downloader Pro — Mobil (Flet) bileşen kitaplığı.

Masaüstündeki `ui/widgets.py` ile aynı sözleşmeyi konuşan Flet karşılıkları.
Aynı adlar, aynı görsel dil: `card()` masaüstündeki `Card` ile aynı zemini,
kenarlığı ve yarıçapı taşır, `pill_group()` aynı seçim davranışını verir.

Görünüm dosyaları artık ham `ft.Container(bgcolor="#131B2E", ...)` kurmaz;
her yüzey buradan gelir. Bir belirteç değiştiğinde altı ekran birlikte kayar.

**Dokunmatik.** Her etkileşimli bileşen en az `theme.H_TOUCH` (48dp) yüksekliğe
oturur ve `ink=True` ile dokunma geri bildirimi verir — Android'de dokunulan
ama tepki vermeyen yüzey, tıklanamaz görünür.
"""

import flet as ft

try:
    import theme as T
except ImportError:  # paket olarak import edildiginde
    from android_app import theme as T


# ---------------------------------------------------------------------------
# Flet surum farklarini yutan yardimcilar
# ---------------------------------------------------------------------------
def border_all(width: int = 1, color: str = None):
    """`ft.border.all` — Flet sürümleri arasında adı değişen API'yi sarar.

    0.8x'te `ft.border.all`, bazı sürümlerde `ft.Border.all` bulunur; hiçbiri
    yoksa `ft.Border` elle kurulur. Altı görünümde ayrı ayrı kopyalanan
    `app_border()` yardımcısının tek kaynağıdır.
    """
    color = T.BORDER if color is None else color
    if hasattr(ft, "border") and hasattr(ft.border, "all"):
        return ft.border.all(width, color)
    if hasattr(ft, "Border") and hasattr(ft.Border, "all"):
        return ft.Border.all(width, color)
    side = ft.BorderSide(width, color)
    return ft.Border(top=side, right=side, bottom=side, left=side)


def padding(left: int, top: int = None, right: int = None, bottom: int = None):
    """Tek değerle simetrik, dört değerle serbest iç boşluk."""
    if top is None:
        return ft.Padding(left, left, left, left)
    if right is None:
        return ft.Padding(left, top, left, top)
    return ft.Padding(left, top, right, bottom)


def _weight(value: int):
    """Sayısal tasarım ağırlığını `ft.FontWeight` değerine çevirir."""
    return {
        400: ft.FontWeight.NORMAL,
        500: ft.FontWeight.W_500,
        600: ft.FontWeight.W_600,
        700: ft.FontWeight.BOLD,
        800: ft.FontWeight.W_800,
    }.get(value, ft.FontWeight.W_600)


def upper_tr(text: str) -> str:
    """Türkçe büyük harf — `i` → `İ`, `ı` → `I`.

    `str.upper()` `i`'yi `I` yapar; `SON İNDİRİLENLER` başlığı bu yüzden
    `SON INDIRILENLER` olarak çıkardı.
    """
    return str(text).replace("i", "İ").replace("ı", "I").upper()


def elide(text: str, limit: int) -> str:
    """Uzun metni `limit` karakterde keser ve `…` ekler."""
    text = str(text)
    return text if len(text) <= limit else text[: max(0, limit - 1)].rstrip() + "…"


# ---------------------------------------------------------------------------
# Metin
# ---------------------------------------------------------------------------
def label(text: str, size: int = T.SIZE_BASE, weight: int = T.W_SEMI,
          color: str = T.TEXT, mono: bool = False, **kwargs) -> ft.Text:
    """Tema fontlarıyla kurulmuş `ft.Text`."""
    kwargs.setdefault("font_family", T.FONT_MONO if mono else T.FONT_UI)
    return ft.Text(text, size=size, weight=_weight(weight), color=color, **kwargs)


def section_label(text: str, **kwargs) -> ft.Text:
    """`SON İNDİRİLENLER` gibi büyük harf bölüm başlığı."""
    return label(upper_tr(text), size=T.SIZE_SM, weight=T.W_EXTRA,
                 color=T.TEXT_MUTED, **kwargs)


def page_title(text: str, icon=None, trailing=None) -> ft.Control:
    """Ekranın üst başlığı: ikon + başlık + sağda isteğe bağlı eylem."""
    controls = []
    if icon is not None:
        controls.append(ft.Icon(icon, color=T.PRIMARY, size=26))
    controls.append(label(text, size=T.SIZE_XL, weight=T.W_EXTRA))
    controls.append(ft.Container(expand=True))
    if trailing is not None:
        controls.extend(trailing if isinstance(trailing, list) else [trailing])
    return ft.Row(controls, spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER)


def link(text: str, on_click=None, color: str = T.PRIMARY_LIGHT,
         size: int = T.SIZE_SM) -> ft.Control:
    """`Değiştir`, `Tümünü gör` gibi satır içi eylem bağlantısı.

    Dokunma hedefi metnin kendisinden büyüktür: 44dp'lik saydam bir kutu
    metni sarar, böylece küçük yazı da rahat vurulur.
    """
    return ft.Container(
        content=label(text, size=size, weight=T.W_BOLD, color=color),
        padding=padding(10, 12),
        border_radius=T.R_CHIP,
        on_click=(lambda e: on_click()) if on_click else None,
        ink=on_click is not None,
    )


def meta_chip(text: str) -> ft.Container:
    """`1080p`, `1042 parça` gibi mono meta rozeti."""
    return ft.Container(
        content=label(text, size=T.SIZE_XS, weight=T.W_MEDIUM,
                      color=T.TEXT_MUTED, mono=True),
        bgcolor=T.BG_ELEVATED,
        border_radius=6,
        padding=padding(8, 3),
    )


def badge(text: str, color: str = T.SUCCESS, ink: str = "#FFFFFF") -> ft.Container:
    """Durum veya bilgi belirteci rozeti."""
    return ft.Container(
        content=label(text, size=T.SIZE_SM, weight=T.W_BOLD, color=ink),
        bgcolor=color,
        border_radius=T.R_CHIP,
        padding=padding(10, 5),
    )


def status_dot(color: str = T.SUCCESS, size: int = 8) -> ft.Container:
    """Renkli durum noktası."""
    return ft.Container(width=size, height=size, bgcolor=color,
                        border_radius=size // 2)


# ---------------------------------------------------------------------------
# Yuzeyler
# ---------------------------------------------------------------------------
def card(content, radius: int = T.R_CARD, fill: str = T.BG_CARD,
         border: str = T.BORDER, pad: int = T.CARD_PAD, **kwargs) -> ft.Container:
    """Tasarımın ana yüzeyi: `#11151F`, 1px kenarlık, 16px yarıçap."""
    return ft.Container(
        content=content,
        bgcolor=fill,
        border_radius=radius,
        border=border_all(1, border) if border else None,
        padding=pad,
        **kwargs,
    )


def tile(content, radius: int = T.R_TILE, fill: str = T.BG_APP,
         pad: int = 12, **kwargs) -> ft.Container:
    """Kart içinde çukur alan: stat kutusu, günlük yatağı."""
    return ft.Container(content=content, bgcolor=fill, border_radius=radius,
                        padding=pad, **kwargs)


def divider(color: str = T.DIVIDER) -> ft.Container:
    """1px yatay ayırıcı.

    `ft.Divider` yerine `Container` kullanılır: `ft.Divider` kendi dikey
    boşluğunu dayatır ve kart içindeki 10px ritmi bozar.
    """
    return ft.Container(height=1, bgcolor=color)


def stat_tile(caption: str, value: str = "—", value_color: str = T.TEXT):
    """`HIZ 24.6 MB/s` gibi ölçüm kutusu.

    `(kapsayıcı, değer_metni)` döndürür — değer metni canlı güncellenir.
    """
    value_text = label(value, size=T.SIZE_MD, weight=T.W_SEMI,
                       color=value_color, mono=True)
    box = tile(
        ft.Column(
            [
                label(upper_tr(caption), size=T.SIZE_XS, weight=T.W_BOLD,
                      color=T.TEXT_DIM),
                value_text,
            ],
            spacing=2,
            tight=True,
        ),
        pad=10,
        expand=True,
    )
    return box, value_text


def step_hint(steps) -> ft.Control:
    """`① Yapıştır › ② Çözümle › ③ İndir` adım şeridi.

    Dar ekranda satır sonuna sığmayan adımlar alta sarılır; yatay kaydırma
    üretmez.
    """
    controls = []
    for position, text in enumerate(steps):
        controls.append(
            ft.Container(
                content=label(str(position + 1), size=T.SIZE_XS, weight=T.W_SEMI,
                              color=T.PRIMARY_TINT, mono=True),
                bgcolor=T.BG_ELEVATED,
                border_radius=9,
                width=18,
                height=18,
                alignment=ft.Alignment(0, 0),
            )
        )
        controls.append(label(text, size=T.SIZE_SM, weight=T.W_BOLD, color=T.TEXT_DIM))
        if position < len(steps) - 1:
            controls.append(label("›", size=T.SIZE_SM, weight=T.W_BOLD,
                                  color=T.BORDER_STRONG))
    return ft.Row(controls, spacing=6, wrap=True, run_spacing=6)


# ---------------------------------------------------------------------------
# Butonlar
# ---------------------------------------------------------------------------
def _button(text, icon, on_click, fill, ink, height, *, border=None,
            size=T.SIZE_BASE, weight=T.W_BOLD, expand=None, disabled=False,
            tooltip=None, radius=T.R_BUTTON):
    row = []
    if icon is not None:
        row.append(ft.Icon(icon, size=18, color=ink))
    row.append(label(text, size=size, weight=weight, color=ink))
    # Duz bir `bgcolor` verildiginde Flet'in devre disi gorunumu ezilir: pasif
    # buton tipki aktif gibi parlar ve kullanici dokunup tepki alamaz. Zemin ve
    # kenarlik bu yuzden duruma gore verilir.
    style = ft.ButtonStyle(
        bgcolor={
            ft.ControlState.DEFAULT: fill,
            ft.ControlState.DISABLED: T.BG_ELEVATED,
        },
        shape=ft.RoundedRectangleBorder(radius=radius),
        padding=padding(16, 0),
        side={
            ft.ControlState.DEFAULT: ft.BorderSide(1, border or fill),
            ft.ControlState.DISABLED: ft.BorderSide(1, T.BORDER),
        },
    )
    return ft.FilledButton(
        content=ft.Row(row, alignment=ft.MainAxisAlignment.CENTER, spacing=8,
                       tight=True),
        style=style,
        height=height,
        expand=expand,
        disabled=disabled,
        tooltip=tooltip,
        on_click=on_click,
    )


def full_width(control) -> ft.Row:
    """Bir kontrolü satır genişliğine yayar.

    Flet'te bir `Column` çocuğuna `expand=True` vermek **dikey** genişleme
    demektir; buton yatayda kendi doğal genişliğinde kalır. Yatayda yaymanın
    yolu onu bir `Row` içine koyup orada `expand` etmektir.
    """
    control.expand = True
    return ft.Row([control], spacing=0)


def primary_button(text, on_click=None, icon=None, height=T.H_BUTTON, **kwargs):
    """Ana mavi eylem: `Çözümle`, `Tüm bölümleri tara`.

    Zemin aksan mavisi degil `PRIMARY_BUTTON`tir; gerekcesi icin bkz.
    `theme.PRIMARY_BUTTON`.
    """
    return _button(text, icon, on_click, T.PRIMARY_BUTTON, "#FFFFFF", height,
                   weight=T.W_EXTRA, **kwargs)


def success_button(text, on_click=None, icon=None, height=T.H_BUTTON, **kwargs):
    """Yeşil indirme eylemi. Metin, tasarımdaki koyu yeşil mürekkeptir."""
    return _button(text, icon, on_click, T.SUCCESS, T.SUCCESS_INK, height,
                   size=T.SIZE_MD, weight=T.W_EXTRA, **kwargs)


def ghost_button(text, on_click=None, icon=None, height=T.H_BUTTON, **kwargs):
    """İkincil eylem: yükseltilmiş zemin + ince kenarlık."""
    return _button(text, icon, on_click, T.BG_ELEVATED, T.TEXT, height,
                   border=T.BORDER, **kwargs)


def danger_button(text, on_click=None, icon=None, height=T.H_BUTTON_SM, **kwargs):
    """`İptal`: kart zemini, kırmızı kenarlık."""
    return _button(text, icon, on_click, T.BG_CARD, T.DANGER, height,
                   border=T.DANGER_BORDER, **kwargs)


def warning_button(text, on_click=None, icon=None, height=T.H_BUTTON_SM, **kwargs):
    """`Duraklat`: kart zemini, sarı kenarlık."""
    return _button(text, icon, on_click, T.BG_CARD, T.WARNING, height,
                   border=T.WARNING_FILL, **kwargs)


def purple_button(text, on_click=None, icon=None, height=T.H_BUTTON_SM, **kwargs):
    """Dönüştürücünün mor eylemi."""
    return _button(text, icon, on_click, T.PURPLE_BUTTON, "#FFFFFF", height,
                   size=T.SIZE_MD, weight=T.W_EXTRA, **kwargs)


def icon_button(icon, on_click=None, color=T.TEXT_MUTED, tooltip=None,
                size=20, **kwargs) -> ft.IconButton:
    """48dp dokunma hedefine oturmuş ikon butonu.

    `ft.IconButton` varsayılanı ikon boyutuna göre küçülebilir; genişlik ve
    yükseklik burada açıkça sabitlenir — ikon buton, dokunulamayacak kadar
    küçük olmamalı.
    """
    return ft.IconButton(
        icon=icon,
        icon_color=color,
        icon_size=size,
        tooltip=tooltip,
        width=T.H_TOUCH,
        height=T.H_TOUCH,
        on_click=on_click,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Girdi
# ---------------------------------------------------------------------------
def text_field(label_text: str = None, hint: str = "", value: str = "",
               icon=None, **kwargs) -> ft.TextField:
    """Tasarımın input kutusu: koyu çukur zemin, ince kenarlık.

    Etiket `label` olarak verilir — yalnızca `hint_text` kullanmak, kullanıcı
    yazmaya başladığında alanın ne olduğunu ekrandan siler.
    """
    kwargs.setdefault("border_radius", T.R_INPUT)
    kwargs.setdefault("bgcolor", T.BG_APP)
    kwargs.setdefault("border_color", T.BORDER_STRONG)
    kwargs.setdefault("focused_border_color", T.PRIMARY)
    kwargs.setdefault("color", T.TEXT)
    kwargs.setdefault("hint_style", ft.TextStyle(color=T.TEXT_DIM, size=T.SIZE_BASE))
    kwargs.setdefault("label_style", ft.TextStyle(color=T.TEXT_MUTED, size=T.SIZE_SM))
    kwargs.setdefault("text_size", T.SIZE_BASE)
    kwargs.setdefault("text_style", ft.TextStyle(font_family=T.FONT_UI))
    kwargs.setdefault("content_padding", padding(14, 14))
    if icon is not None:
        kwargs.setdefault("prefix_icon", icon)
    return ft.TextField(label=label_text, hint_text=hint, value=value, **kwargs)


def dropdown(label_text: str = None, options=(), value=None, on_select=None,
             **kwargs) -> ft.Dropdown:
    """Tema renklerine oturmuş `ft.Dropdown`.

    Seçim olayı `on_select`tir. Flet 0.86'da `Dropdown`un `on_change` diye bir
    alanı **yoktur**: `dd.on_change = handler` atamak ölü bir nitelik yaratır
    ve seçim hiçbir zaman işlenmez.
    """
    kwargs.setdefault("border_radius", T.R_INPUT)
    kwargs.setdefault("bgcolor", T.BG_APP)
    kwargs.setdefault("border_color", T.BORDER_STRONG)
    kwargs.setdefault("focused_border_color", T.PRIMARY)
    kwargs.setdefault("color", T.TEXT)
    kwargs.setdefault("text_size", T.SIZE_BASE)
    kwargs.setdefault("label_style", ft.TextStyle(color=T.TEXT_MUTED, size=T.SIZE_SM))
    kwargs.setdefault("content_padding", padding(14, 12))
    return ft.Dropdown(label=label_text, options=list(options), value=value,
                       on_select=on_select, **kwargs)


def progress_bar(value: float = 0.0, height: int = 8, **kwargs) -> ft.ProgressBar:
    """İnce ilerleme çubuğu."""
    kwargs.setdefault("color", T.PRIMARY)
    kwargs.setdefault("bgcolor", T.BG_APP)
    kwargs.setdefault("border_radius", height // 2)
    return ft.ProgressBar(value=value, height=height, **kwargs)


def toggle(value: bool = False, on_change=None, **kwargs) -> ft.Switch:
    """Ayarlar satırlarındaki aç/kapa anahtarı."""
    kwargs.setdefault("active_color", T.PRIMARY)
    kwargs.setdefault("inactive_track_color", T.BG_ELEVATED)
    kwargs.setdefault("inactive_thumb_color", T.TEXT_DIM)
    return ft.Switch(value=value, on_change=on_change, **kwargs)


# ---------------------------------------------------------------------------
# Secim kontrolleri
# ---------------------------------------------------------------------------
class PillGroup(ft.Column):
    """Tek seçimli pill kümesi — masaüstündeki `OptionPills`in Flet karşılığı.

    Radyo listesinin yerini alır: seçenekler satıra sarılır, seçili olan mavi
    tint zemin alır. Değerler tam haliyle saklanır (`get()` motorun beklediği
    dizeyi aynen döndürür) ama pill üstünde kısaltılmış hali gösterilir:
    `🎬 1080p (1042 Parça)` -> etiket `1080p`, alt metin `1042 Parça`.

    `on_select(value)` seçim değiştiğinde tam değerle çağrılır.

    **Ad çakışması uyarısı.** Flet her kontrol örneğinde `_c`, `_i`,
    `_dirty`, `_internals` ve `_values` adlarını kendi iç depolaması için
    kullanır. Bir kontrol alt sınıfında bu adlardan birine yazmak Flet'in
    özellik erişimini bozar ve hata, sayfa çizilirken alakasız bir yerde
    `AttributeError` olarak patlar. Seçenek listesi bu yüzden `_options`
    adını taşır.
    """

    def __init__(self, values=(), on_select=None, accent: str = T.PRIMARY,
                 fill: str = T.PRIMARY_FILL, ink: str = T.PRIMARY_TINT,
                 max_label: int = 26, empty_text: str = "Seçenek yok"):
        super().__init__(spacing=0, tight=True)
        self._on_select = on_select
        self._accent = accent
        self._fill = fill
        self._ink = ink
        self._max_label = max_label
        self._empty_text = empty_text
        self._options = []
        self._index = -1
        self._row = ft.Row(spacing=T.GAP_TOUCH, run_spacing=T.GAP_TOUCH, wrap=True)
        self.controls = [self._row]
        self.set_values(values)

    # -- gorunum -----------------------------------------------------------
    @staticmethod
    def _split(value: str):
        """Tam değeri (etiket, alt metin) olarak ikiye ayırır.

        Baştaki emoji atılır: tasarımda tür bilgisini ikon taşır, metnin
        içindeki emoji ekran okuyucuda gürültüye dönüşür.
        """
        text = str(value).strip()
        while text and not (text[0].isalnum() or text[0] in "+-"):
            text = text[1:].lstrip()
        sub = ""
        if "(" in text and text.rstrip().endswith(")"):
            head, _, tail = text.rpartition("(")
            sub = tail.rstrip(")").strip()
            text = head.strip()
        elif " - " in text:
            text, _, sub = text.partition(" - ")
            text, sub = text.strip(), sub.strip()
        return text or str(value), sub

    def _make_pill(self, position: int, value: str) -> ft.Container:
        text, sub = self._split(value)
        selected = position == self._index
        row = [label(elide(text, self._max_label), size=T.SIZE_SM, weight=T.W_BOLD,
                     color=self._ink if selected else T.TEXT_CHIP)]
        if sub:
            row.append(label(elide(sub, 18), size=T.SIZE_XS, weight=T.W_MEDIUM,
                             color=T.TEXT_DIM, mono=True))
        return ft.Container(
            content=ft.Row(row, spacing=6, tight=True),
            bgcolor=self._fill if selected else T.BG_ELEVATED,
            border=border_all(1, self._accent if selected else T.BORDER),
            border_radius=T.R_PILL,
            padding=padding(14, 0),
            height=T.H_PILL,
            alignment=ft.Alignment(0, 0),
            on_click=lambda e, i=position: self._pick(i),
            ink=True,
        )

    def _rebuild(self):
        if not self._options:
            self._row.controls = [
                label(self._empty_text, size=T.SIZE_SM, color=T.TEXT_DIM)
            ]
        else:
            self._row.controls = [
                self._make_pill(position, value)
                for position, value in enumerate(self._options)
            ]
        self._safe_update()

    def _safe_update(self):
        """Sayfaya eklenmemiş kontrolde `update()` hata verir; sessizce geç."""
        try:
            self.update()
        except Exception:
            pass

    def _pick(self, index: int):
        self._index = index
        self._rebuild()
        if self._on_select:
            self._on_select(self._options[index])

    # -- sozlesme ----------------------------------------------------------
    def set_values(self, values) -> None:
        self._options = [str(v) for v in values]
        self._index = 0 if self._options else -1
        self._rebuild()

    def set(self, value) -> None:
        """Seçimi ayarlar. Bilinmeyen değer listeye eklenir."""
        value = str(value)
        if value not in self._options:
            self._options.append(value)
        self._index = self._options.index(value)
        self._rebuild()

    def get(self) -> str:
        if 0 <= self._index < len(self._options):
            return self._options[self._index]
        return ""

    @property
    def index(self) -> int:
        return self._index

    @property
    def values(self) -> list:
        return list(self._options)


class Collapsible(ft.Container):
    """Katlanabilir bölüm — tasarımın `Gelişmiş` ve `İşlem günlüğü` panelleri.

    Gövde `.body` ile erişilir. Kapalıyken `visible=False` olur: yer kaplamaz
    ama kontrolleri canlı kalır, arka plan iş parçacığından gelen güncelleme
    hedefini şaşırmaz.
    """

    def __init__(self, title: str, hint: str = "", expanded: bool = False,
                 body_controls=None):
        self._expanded = bool(expanded)
        self._chevron = ft.Icon(ft.Icons.CHEVRON_RIGHT_ROUNDED, size=18,
                                color=T.TEXT_MUTED)
        self._hint = label(hint, size=T.SIZE_XS, weight=T.W_MEDIUM,
                           color=T.TEXT_MUTED, mono=True)
        header = ft.Container(
            content=ft.Row(
                [
                    self._chevron,
                    label(title, size=T.SIZE_SM, weight=T.W_BOLD, color=T.TEXT_MUTED,
                          expand=True),
                    self._hint,
                ],
                spacing=8,
            ),
            padding=padding(T.CARD_PAD, 0),
            height=T.H_TOUCH,
            on_click=lambda e: self.toggle(),
            ink=True,
            border_radius=T.R_CARD_SM,
        )
        self.body = ft.Column(body_controls or [], spacing=10, tight=True,
                              visible=self._expanded)
        body_box = ft.Container(content=self.body,
                                padding=ft.Padding(T.CARD_PAD, 0, T.CARD_PAD, 14),
                                visible=self._expanded)
        self._body_box = body_box
        super().__init__(
            content=ft.Column([header, body_box], spacing=0, tight=True),
            bgcolor=T.BG_CARD,
            border_radius=T.R_CARD_SM,
            border=border_all(1, T.BORDER),
        )
        self._apply()

    def _apply(self):
        self._chevron.icon = (ft.Icons.KEYBOARD_ARROW_DOWN_ROUNDED if self._expanded
                              else ft.Icons.CHEVRON_RIGHT_ROUNDED)
        self.body.visible = self._expanded
        self._body_box.visible = self._expanded
        try:
            self.update()
        except Exception:
            pass

    def toggle(self) -> None:
        self._expanded = not self._expanded
        self._apply()

    def set_expanded(self, value: bool) -> None:
        self._expanded = bool(value)
        self._apply()

    @property
    def expanded(self) -> bool:
        return self._expanded

    def set_hint(self, text: str) -> None:
        self._hint.value = str(text)
        try:
            self._hint.update()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Bilesikler
# ---------------------------------------------------------------------------
def list_row(title: str, meta: str = "", icon=ft.Icons.MOVIE_ROUNDED,
             icon_fill: str = T.ICON_FILL_VIDEO, icon_color: str = T.PRIMARY_LIGHT,
             actions=(), on_click=None) -> ft.Container:
    """`Son İndirilenler` / `İndirilenler` satırı.

    `actions` `(ikon, ipucu, komut, renk)` dörtlülerinden oluşur; her biri
    48dp dokunma hedefi alır.
    """
    action_controls = [
        icon_button(action_icon, on_click=lambda e, c=command: c(), color=color,
                    tooltip=tip, size=18)
        for action_icon, tip, command, color in actions
    ]
    return ft.Container(
        content=ft.Row(
            [
                ft.Container(
                    content=ft.Icon(icon, size=18, color=icon_color),
                    bgcolor=icon_fill,
                    border_radius=9,
                    width=36,
                    height=36,
                    alignment=ft.Alignment(0, 0),
                ),
                ft.Column(
                    [
                        label(title, size=T.SIZE_BASE, weight=T.W_BOLD,
                              max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                        label(meta, size=T.SIZE_XS, weight=T.W_SEMI,
                              color=T.TEXT_MUTED, max_lines=1,
                              overflow=ft.TextOverflow.ELLIPSIS),
                    ],
                    spacing=2,
                    tight=True,
                    expand=True,
                ),
                ft.Row(action_controls, spacing=0, tight=True),
            ],
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        bgcolor=T.BG_CARD,
        border_radius=T.R_TILE,
        border=border_all(1, T.BORDER),
        padding=ft.Padding(10, 8, 4, 8),
        on_click=(lambda e: on_click()) if on_click else None,
        ink=on_click is not None,
    )


def setting_row(title: str, subtitle: str = "", control=None,
                last: bool = False) -> ft.Column:
    """Ayarlar listesindeki satır: başlık + açıklama + sağda kontrol."""
    row = ft.Row(
        [
            ft.Column(
                [
                    label(title, size=T.SIZE_BASE, weight=T.W_BOLD),
                    label(subtitle, size=T.SIZE_SM, weight=T.W_SEMI,
                          color=T.TEXT_MUTED),
                ],
                spacing=2,
                tight=True,
                expand=True,
            ),
        ],
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=12,
    )
    if control is not None:
        row.controls.append(control)
    controls = [ft.Container(content=row, padding=padding(0, 12))]
    if not last:
        controls.append(divider())
    return ft.Column(controls, spacing=0, tight=True)


def empty_state(icon, title: str, hint: str = "") -> ft.Container:
    """Boş liste durumu — ne olduğunu ve sıradaki adımı söyler."""
    return ft.Container(
        padding=padding(20, 40),
        alignment=ft.Alignment(0, 0),
        content=ft.Column(
            [
                ft.Icon(icon, size=44, color=T.TEXT_DIM),
                label(title, size=T.SIZE_BASE, weight=T.W_BOLD,
                      color=T.TEXT_MUTED, text_align=ft.TextAlign.CENTER),
                label(hint, size=T.SIZE_SM, color=T.TEXT_DIM,
                      text_align=ft.TextAlign.CENTER),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=8,
            tight=True,
        ),
    )


def log_strip(text_control) -> ft.Container:
    """Ekranın altındaki tek satırlık işlem günlüğü şeridi."""
    return tile(
        ft.Row(
            [
                ft.Icon(ft.Icons.TERMINAL_ROUNDED, color=T.TEXT_DIM, size=16),
                ft.Container(content=text_control, expand=True),
            ],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.START,
        ),
        pad=12,
    )


def show(page, dialog) -> bool:
    """Bir `SnackBar` / `AlertDialog` gösterir; Flet sürüm farkını yutar.

    Flet 0.86'da `page.snack_bar = …` ve `page.dialog = …` **sessizce hiçbir
    şey yapmaz** — bunlar artık `Page` alanı değil, atama yalnızca ölü bir
    Python niteliği yaratır. Doğru çağrı `page.show_dialog(...)`. Eski
    sürümlerde ise `show_dialog` yoktur; ikisi de denenir.

    Bir bildirimi gösterememek uygulamayı düşürmemeli, bu yüzden son çare
    sessizce vazgeçmektir.
    """
    try:
        page.show_dialog(dialog)
        return True
    except Exception:
        pass
    try:  # Flet < 0.8x
        dialog.open = True
        if isinstance(dialog, ft.SnackBar):
            page.snack_bar = dialog
        else:
            page.dialog = dialog
        page.update()
        return True
    except Exception:
        return False


def snack(page, message: str, color: str = None) -> None:
    """Tek satırlık geri bildirim."""
    show(page, ft.SnackBar(
        content=label(message, size=T.SIZE_BASE, color=T.TEXT),
        bgcolor=color or T.BG_ELEVATED,
        behavior=ft.SnackBarBehavior.FLOATING,
        shape=ft.RoundedRectangleBorder(radius=T.R_BADGE),
    ))


def dismiss(page, dialog=None) -> None:
    """Açık pencereyi kapatır."""
    try:
        page.pop_dialog()
        return
    except Exception:
        pass
    try:
        if dialog is not None:
            dialog.open = False
        page.update()
    except Exception:
        pass


def confirm_dialog(page, title: str, message: str, on_confirm,
                   confirm_text: str = "Sil", danger: bool = True) -> None:
    """Geri alınamayan eylem için onay penceresi.

    Dosya silme gibi kalıcı işlemler tek dokunuşla gerçekleşmemeli; mobilde
    yanlış hedefe dokunmak masaüstünden çok daha kolaydır.
    """
    def close(e=None):
        dismiss(page, dialog)

    def confirm(e=None):
        dismiss(page, dialog)
        on_confirm()

    dialog = ft.AlertDialog(
        modal=True,
        bgcolor=T.BG_CARD,
        shape=ft.RoundedRectangleBorder(radius=T.R_CARD),
        title=ft.Row(
            [
                ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED,
                        color=T.DANGER if danger else T.WARNING, size=22),
                label(title, size=T.SIZE_MD, weight=T.W_EXTRA),
            ],
            spacing=8,
        ),
        content=label(message, size=T.SIZE_BASE, color=T.TEXT_MUTED),
        actions=[
            ghost_button("Vazgeç", close, height=T.H_BUTTON_SM),
            danger_button(confirm_text, confirm, icon=ft.Icons.DELETE_OUTLINE_ROUNDED)
            if danger else primary_button(confirm_text, confirm, height=T.H_BUTTON_SM),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    show(page, dialog)


def screen(controls, scroll: bool = True) -> ft.Container:
    """Bir ekranın dış kabı: sayfa kenar boşluğu + dikey ritim + kaydırma.

    Alt boşluk gezinme çubuğunun yüksekliği kadar bırakılır; son kart, alt
    çubuğun altında kalıp erişilemez olmamalı.
    """
    return ft.Container(
        padding=ft.Padding(T.PAGE_PAD, T.PAGE_PAD, T.PAGE_PAD, T.PAGE_PAD + 8),
        expand=True,
        bgcolor=T.BG_APP,
        content=ft.Column(
            controls,
            scroll=ft.ScrollMode.ADAPTIVE if scroll else None,
            spacing=T.SECTION_GAP,
        ),
    )
