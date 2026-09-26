"""Tasarımdaki bileşen primitifleri.

Buradaki her sınıf saf sunumdur: motoru tanımaz, iş parçacığı başlatmaz.
`gui.py` bunları birleştirerek sayfaları kurar.

Tkinter'ın iki eksiği tekrar tekrar karşımıza çıktığı için burada bir kez
çözülür:

* **Bileşik widget'larda tıklama.** Bir kartın üstündeki etikete tıklamak
  kartın olayını tetiklemez; `bind_click()` olayı tüm alt ağaca bağlar.
* **Bileşik widget'larda hover.** Aynı sebeple `bind_hover()` fare kartın
  herhangi bir parçasındayken zemini değiştirir.
"""

import customtkinter as ctk

from . import fonts, icons, theme
from logger import get_logger

logger = get_logger("ui.widgets")


# ---------------------------------------------------------------------------
# Yardimcilar
# ---------------------------------------------------------------------------
def icon_text(name: str) -> str:
    """İkon glyph'i — font yoksa ASCII karşılığı."""
    return icons.text(name, fonts.has_icon_font())


def upper_tr(text: str) -> str:
    """Türkçe'ye uygun büyük harf.

    Python'un `str.upper()` metodu `i` harfini `I` yapar; Türkçe'de doğrusu
    `İ`'dir. Bölüm başlıkları büyük harfle yazıldığı için bu fark ekranda
    doğrudan görünür ("SON INDIRILENLER" yerine "SON İNDİRİLENLER").
    """
    return str(text).replace("i", "İ").replace("ı", "I").upper()


def elide(text: str, limit: int) -> str:
    """Tkinter etiketleri kendiliğinden kısaltmaz; `limit` karakterde keser."""
    text = str(text)
    if len(text) <= limit:
        return text
    return text[: max(limit - 1, 1)].rstrip() + "…"


def _descendants(widget):
    yield widget
    for child in widget.winfo_children():
        yield from _descendants(child)


def bind_click(widget, command) -> None:
    """Tıklamayı widget'a ve tüm alt ağacına bağlar, imleci el yapar.

    Tkinter iç içe bileşenlerinde (CTkLabel içindeki Label ve Canvas) aynı tıklamanın
    birden fazla kez tetiklenmesini (bubbling / double toggle) 250ms debounce
    ve `return 'break'` ile engeller; böylece tek tıkta kararlı çalışır.
    """
    if command is None:
        return

    last_click_time = [0.0]

    def handler(_event=None):
        import time
        now = time.time()
        if now - last_click_time[0] < 0.25:
            return "break"
        last_click_time[0] = now
        try:
            command()
        except Exception:
            logger.debug("Composite widget click callback failed", exc_info=True)
        return "break"

    bound_nodes = set()
    for node in _descendants(widget):
        if node in bound_nodes:
            continue
        bound_nodes.add(node)
        try:
            node.bind("<Button-1>", handler, add=False)
            node.configure(cursor="hand2")
        except Exception:
            try:
                node.bind("<Button-1>", handler)
            except Exception:
                logger.debug("Composite widget click binding failed", exc_info=True)


def bind_hover(widget, normal: str, hover: str, targets=None) -> None:
    """Fare alt ağacın herhangi bir yerindeyken `targets`'ın zeminini değiştirir."""
    targets = targets or [widget]

    def paint(color):
        for target in targets:
            try:
                target.configure(fg_color=color)
            except Exception:
                logger.debug("Composite widget hover update failed", exc_info=True)

    for node in _descendants(widget):
        node.bind("<Enter>", lambda _e: paint(hover), add="+")
        node.bind("<Leave>", lambda _e: paint(normal), add="+")


# ---------------------------------------------------------------------------
# Yuzeyler
# ---------------------------------------------------------------------------
class Card(ctk.CTkFrame):
    """Tasarımın ana yüzeyi: `#11151F`, 1px kenarlık, 16px yarıçap."""

    def __init__(self, parent, radius: int = theme.R_CARD, fill: str = theme.BG_CARD,
                 border: str = theme.BORDER, **kwargs):
        super().__init__(
            parent,
            fg_color=fill,
            corner_radius=radius,
            border_width=1,
            border_color=border,
            **kwargs,
        )


class Tile(ctk.CTkFrame):
    """Kart içinde çukur alan: stat kutusu, input zemini, progress yatağı."""

    def __init__(self, parent, radius: int = theme.R_TILE, fill: str = theme.BG_APP, **kwargs):
        super().__init__(parent, fg_color=fill, corner_radius=radius, **kwargs)


class Divider(ctk.CTkFrame):
    """1px yatay ayırıcı."""

    def __init__(self, parent, color: str = theme.DIVIDER, **kwargs):
        super().__init__(parent, fg_color=color, height=1, corner_radius=0, **kwargs)


# ---------------------------------------------------------------------------
# Metin
# ---------------------------------------------------------------------------
def label(parent, text: str, size: int = theme.SIZE_BASE, weight: int = 600,
          color: str = theme.TEXT, mono: bool = False, **kwargs):
    """Tema fontlarıyla kurulmuş `CTkLabel`."""
    font = fonts.mono(size, min(weight, 600)) if mono else fonts.ui(size, weight)
    kwargs.setdefault("anchor", "w")
    return ctk.CTkLabel(parent, text=text, font=font, text_color=color, **kwargs)


def section_label(parent, text: str, **kwargs):
    """`SON İNDİRİLENLER` gibi büyük harf bölüm başlığı.

    Tasarım `letter-spacing:.04em` uygular; Tk harf aralığı ayarlayamaz.
    Harf aralarına boşluk sokmak bu incelikli değeri fazlasıyla abartacağı
    için taklit edilmez, yalnızca büyük harf ve ağırlık korunur.
    """
    return label(parent, upper_tr(text), size=theme.SIZE_SM, weight=800,
                 color=theme.TEXT_MUTED, **kwargs)


def icon_label(parent, name: str, size: int = 18, color: str = theme.TEXT_MUTED, **kwargs):
    """Tek bir ikon glyph'i."""
    return ctk.CTkLabel(parent, text=icon_text(name), font=fonts.icon(size),
                        text_color=color, **kwargs)


def link(parent, text: str, command=None, color: str = theme.PRIMARY_LIGHT,
         size: int = theme.SIZE_SM, **kwargs):
    """`Değiştir`, `Tümünü gör` gibi satır içi eylem bağlantısı."""
    widget = label(parent, text, size=size, weight=700, color=color, **kwargs)
    bind_click(widget, command)
    return widget


class MetaChip(ctk.CTkLabel):
    """`1080p`, `1042 parça` gibi mono meta rozeti."""

    def __init__(self, parent, text: str, **kwargs):
        super().__init__(
            parent,
            text=f" {text} ",
            font=fonts.mono(theme.SIZE_XS, 500),
            text_color=theme.TEXT_MUTED,
            fg_color=theme.BG_ELEVATED,
            corner_radius=6,
            **kwargs,
        )


def badge(parent, text: str, color: str = theme.SUCCESS, text_color: str = "#FFFFFF", **kwargs):
    """Durum veya bilgi belirteci rozeti."""
    return ctk.CTkLabel(
        parent,
        text=f"  {text}  ",
        font=fonts.ui(theme.SIZE_SM, 700),
        text_color=text_color,
        fg_color=color,
        corner_radius=theme.R_CHIP,
        height=28,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Butonlar
# ---------------------------------------------------------------------------
def _button(parent, text, icon_name, command, fill, hover, ink, height, width,
            border=None, size=theme.SIZE_BASE, weight=700, **kwargs):
    caption = f"{icon_text(icon_name)}  {text}" if icon_name else text
    return ctk.CTkButton(
        parent,
        text=caption,
        command=command,
        height=height,
        width=width or 0,
        corner_radius=theme.R_BUTTON,
        fg_color=fill,
        hover_color=hover,
        text_color=ink,
        border_width=1 if border else 0,
        border_color=border or fill,
        font=fonts.ui(size, weight),
        **kwargs,
    )


def primary_button(parent, text, command=None, icon=None, height=theme.H_BUTTON,
                   width=None, **kwargs):
    """Ana mavi eylem: `Çözümle`, `Tüm bölümleri tara`.

    Zemin aksan mavisi değil `PRIMARY_BUTTON`dır; gerekçesi için bkz.
    `theme.PRIMARY_BUTTON`.
    """
    return _button(parent, text, icon, command, theme.PRIMARY_BUTTON,
                   theme.PRIMARY_BUTTON_HOVER, "#FFFFFF", height, width,
                   weight=800, **kwargs)


def success_button(parent, text, command=None, icon=None, height=theme.H_BUTTON,
                   width=None, **kwargs):
    """Yeşil indirme eylemi. Metin rengi tasarımdaki koyu yeşil mürekkeptir."""
    return _button(parent, text, icon, command, theme.SUCCESS, theme.SUCCESS_HOVER,
                   theme.SUCCESS_INK, height, width, size=theme.SIZE_MD, weight=800, **kwargs)


def ghost_button(parent, text, command=None, icon=None, height=theme.H_BUTTON,
                 width=None, **kwargs):
    """İkincil eylem: yükseltilmiş zemin + ince kenarlık."""
    return _button(parent, text, icon, command, theme.BG_ELEVATED, theme.BG_HOVER,
                   theme.TEXT, height, width, border=theme.BORDER, **kwargs)


def danger_button(parent, text, command=None, icon=None, height=theme.H_BUTTON_SM,
                  width=None, **kwargs):
    """`İptal`: saydam zemin, kırmızı kenarlık."""
    return _button(parent, text, icon, command, theme.BG_CARD, theme.DANGER_FILL,
                   theme.DANGER, height, width, border=theme.DANGER_BORDER, **kwargs)


def purple_button(parent, text, command=None, icon=None, height=theme.H_BUTTON_SM,
                  width=None, **kwargs):
    """Dönüştürücünün mor eylemi."""
    return _button(parent, text, icon, command, theme.PURPLE_BUTTON,
                   theme.PURPLE_BUTTON_HOVER, "#FFFFFF", height, width,
                   size=theme.SIZE_MD, weight=800, **kwargs)


def entry(parent, placeholder: str = "", height: int = theme.H_INPUT, **kwargs):
    """Tasarımın input kutusu: koyu çukur zemin, ince kenarlık."""
    return ctk.CTkEntry(
        parent,
        placeholder_text=placeholder,
        height=height,
        corner_radius=theme.R_INPUT,
        fg_color=theme.BG_APP,
        border_color=theme.BORDER_STRONG,
        border_width=1,
        text_color=theme.TEXT,
        placeholder_text_color=theme.TEXT_DIM,
        font=fonts.ui(theme.SIZE_BASE, 600),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Secim kontrolleri
# ---------------------------------------------------------------------------
class Pill(ctk.CTkFrame):
    """Yuvarlak seçim etiketi: `1080p 1.9 GB`, `Türkçe dublaj`.

    Seçili durumda mavi tint zemin + mavi kenarlık, değilse yükseltilmiş
    zemin alır.
    """

    def __init__(self, parent, text: str, sub: str = "", command=None,
                 accent: str = theme.PRIMARY, fill: str = theme.PRIMARY_FILL,
                 ink: str = theme.PRIMARY_TINT, **kwargs):
        super().__init__(parent, fg_color=theme.BG_ELEVATED, corner_radius=theme.R_PILL,
                         border_width=1, border_color=theme.BORDER,
                         **kwargs)
        self._accent = accent
        self._fill = fill
        self._ink = ink
        self._selected = False
        self._command = command

        self._label = label(self, text, size=theme.SIZE_SM, weight=700,
                            color=theme.TEXT_CHIP, fg_color="transparent")
        self._label.grid(row=0, column=0, padx=(13, 0), pady=8)
        self._sub = None
        if sub:
            self._sub = label(self, sub, size=theme.SIZE_XS, weight=500,
                              color=theme.TEXT_DIM, mono=True, fg_color="transparent")
            self._sub.grid(row=0, column=1, padx=(6, 13), pady=8)
        else:
            self._label.grid_configure(padx=13)

        bind_click(self, self._on_click)

    def _on_click(self):
        if self._command:
            self._command()

    @property
    def selected(self) -> bool:
        return self._selected

    def set_selected(self, value: bool) -> None:
        self._selected = bool(value)
        if self._selected:
            self.configure(fg_color=self._fill, border_color=self._accent)
            self._label.configure(text_color=self._ink)
        else:
            self.configure(fg_color=theme.BG_ELEVATED, border_color=theme.BORDER)
            self._label.configure(text_color=theme.TEXT_CHIP)

    def text(self) -> str:
        return self._label.cget("text")


class PillGroup(ctk.CTkFrame):
    """Tek seçimli `Pill` kümesi.

    `values` her biri `str` ya da `(etiket, alt_metin)` olabilir. Seçim
    değiştiğinde `command(index, etiket)` çağrılır.
    """

    def __init__(self, parent, values=(), command=None, accent: str = theme.PRIMARY,
                 fill: str = theme.PRIMARY_FILL, ink: str = theme.PRIMARY_TINT, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._command = command
        self._accent = accent
        self._fill = fill
        self._ink = ink
        self._pills = []
        self._index = -1
        self.set_values(values)

    def set_values(self, values, selected: int = 0) -> None:
        """Pill'leri yeniden kurar. Çözümleme sonrası kalite listesi değişir."""
        for pill in self._pills:
            pill.destroy()
        self._pills = []
        self._index = -1

        for position, item in enumerate(values):
            text, sub = item if isinstance(item, (tuple, list)) else (item, "")
            pill = Pill(self, text, sub, accent=self._accent, fill=self._fill,
                        ink=self._ink, command=lambda i=position: self.select(i))
            pill.grid(row=0, column=position, padx=(0, 6), sticky="w")
            self._pills.append(pill)

        if self._pills:
            self.select(min(selected, len(self._pills) - 1), notify=False)

    def select(self, index: int, notify: bool = True) -> None:
        if not 0 <= index < len(self._pills):
            return
        self._index = index
        for position, pill in enumerate(self._pills):
            pill.set_selected(position == index)
        if notify and self._command:
            self._command(index, self._pills[index].text())

    @property
    def index(self) -> int:
        return self._index

    def value(self) -> str:
        if 0 <= self._index < len(self._pills):
            return self._pills[self._index].text()
        return ""

    def values(self) -> list:
        return [pill.text() for pill in self._pills]


class Segmented(ctk.CTkFrame):
    """`Dengeli / Otomatik / Turbo` tarzı segment kontrolü.

    CTk'nin `CTkSegmentedButton`'ı yerine elle kurulur çünkü tasarım seçili
    segmente düz `#181D2A` verir, CTk ise mavi vurgu uygular.
    """

    def __init__(self, parent, options, command=None, selected: int = 0,
                 fill: str = theme.BG_APP, **kwargs):
        super().__init__(parent, fg_color=fill, corner_radius=theme.R_BADGE, **kwargs)
        self._command = command
        self._cells = []
        self._index = selected

        for position, text in enumerate(options):
            cell = label(self, text, size=theme.SIZE_SM, weight=700,
                         color=theme.TEXT_MUTED, corner_radius=9,
                         fg_color="transparent", anchor="center", width=0)
            cell.grid(row=0, column=position, padx=3, pady=3, sticky="ew")
            cell.configure(padx=12, pady=6)
            bind_click(cell, lambda i=position: self.select(i))
            self._cells.append(cell)

        self._paint()

    def _paint(self):
        for position, cell in enumerate(self._cells):
            if position == self._index:
                cell.configure(fg_color=theme.BG_ELEVATED, text_color=theme.TEXT)
            else:
                cell.configure(fg_color="transparent", text_color=theme.TEXT_MUTED)

    def select(self, index: int, notify: bool = True) -> None:
        if not 0 <= index < len(self._cells):
            return
        self._index = index
        self._paint()
        if notify and self._command:
            self._command(index, self._cells[index].cget("text"))

    @property
    def index(self) -> int:
        return self._index

    def value(self) -> str:
        return self._cells[self._index].cget("text") if self._cells else ""


class Toggle(ctk.CTkSwitch):
    """Ayarlar satırlarındaki aç/kapa anahtarı."""

    def __init__(self, parent, value: bool = False, command=None, **kwargs):
        super().__init__(
            parent,
            text="",
            width=44,
            switch_width=40,
            switch_height=22,
            corner_radius=12,
            progress_color=theme.PRIMARY,
            fg_color=theme.BG_ELEVATED,
            button_color=theme.TEXT_DIM,
            button_hover_color=theme.TEXT_MUTED,
            command=command,
            **kwargs,
        )
        self.set_value(value)

    def set_value(self, value: bool) -> None:
        self.select() if value else self.deselect()
        # Kapalıyken gri, açıkken beyaz topuz — tasarımdaki davranış.
        self.configure(button_color="#FFFFFF" if value else theme.TEXT_DIM)

    def value(self) -> bool:
        return bool(self.get())


# ---------------------------------------------------------------------------
# Gostergeler
# ---------------------------------------------------------------------------
class ProgressBar(ctk.CTkProgressBar):
    """İnce ilerleme çubuğu.

    Tasarım `linear-gradient(90deg,#3B82F6,#60A5FA)` kullanır; Tk gradient
    çizemediği için düz `PRIMARY` dolgu uygulanır.
    """

    def __init__(self, parent, height: int = 8, **kwargs):
        super().__init__(
            parent,
            height=height,
            corner_radius=height // 2,
            fg_color=theme.BG_APP,
            progress_color=theme.PRIMARY,
            border_width=0,
            **kwargs,
        )
        self.set(0)


class StatTile(Tile):
    """`HIZ 24.6 MB/s` gibi ölçüm kutusu."""

    def __init__(self, parent, caption: str, value: str = "—",
                 value_color: str = theme.TEXT, **kwargs):
        super().__init__(parent, **kwargs)
        self.grid_columnconfigure(0, weight=1)
        self._caption = label(self, upper_tr(caption), size=theme.SIZE_XS,
                              weight=700, color=theme.TEXT_DIM, fg_color="transparent")
        self._caption.grid(row=0, column=0, sticky="w", padx=12, pady=(10, 0))
        self._value = label(self, value, size=theme.SIZE_LG, weight=600,
                            color=value_color, mono=True, fg_color="transparent")
        self._value.grid(row=1, column=0, sticky="w", padx=12, pady=(2, 10))

    def set_value(self, value: str) -> None:
        self._value.configure(text=value)


class StatusDot(ctk.CTkFrame):
    """Renkli durum noktası.

    `CTkLabel` yerine `CTkFrame` kullanılır: etiket, gridlendiği hücreyi
    doldurup daireyi dikey bir çubuğa çeker. Çerçeve boyut yayılımı
    kapatıldığında istenen ölçüde kalır.
    """

    def __init__(self, parent, color: str = theme.SUCCESS, size: int = 8, **kwargs):
        super().__init__(parent, width=size, height=size, corner_radius=size // 2,
                         fg_color=color, border_width=0, **kwargs)
        self.grid_propagate(False)
        self.pack_propagate(False)

    def set_color(self, color: str) -> None:
        self.configure(fg_color=color)


class StepHint(ctk.CTkFrame):
    """`① Yapıştır › ② Çözümle › ③ İndir` adım şeridi."""

    def __init__(self, parent, steps, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        column = 0
        for position, text in enumerate(steps):
            bullet = label(self, str(position + 1), size=theme.SIZE_XS, weight=600,
                           color=theme.PRIMARY_TINT, mono=True, fg_color=theme.BG_ELEVATED,
                           corner_radius=9, width=18, height=18, anchor="center")
            bullet.grid(row=0, column=column, padx=(0, 6))
            column += 1
            label(self, text, size=theme.SIZE_SM, weight=700,
                  color=theme.TEXT_DIM).grid(row=0, column=column)
            column += 1
            if position < len(steps) - 1:
                label(self, "›", size=theme.SIZE_SM, weight=700,
                      color=theme.BORDER_STRONG).grid(row=0, column=column, padx=10)
                column += 1


# ---------------------------------------------------------------------------
# Bilesikler
# ---------------------------------------------------------------------------
class SidebarItem(ctk.CTkFrame):
    """Sol menü satırı: ikon + etiket + isteğe bağlı sayı rozeti."""

    def __init__(self, parent, icon_name: str, text: str, command=None, **kwargs):
        super().__init__(parent, fg_color="transparent", corner_radius=theme.R_BADGE,
                         height=theme.H_NAV, **kwargs)
        self.grid_propagate(False)
        self.grid_columnconfigure(1, weight=1)
        self._active = False

        self._icon = icon_label(self, icon_name, size=18, color=theme.TEXT_DIM,
                                fg_color="transparent", width=18)
        self._icon.grid(row=0, column=0, padx=(12, 11), pady=11)
        self._label = label(self, text, size=theme.SIZE_BASE, weight=700,
                            color=theme.TEXT_MUTED, fg_color="transparent")
        self._label.grid(row=0, column=1, sticky="w")

        self._badge = label(self, "", size=theme.SIZE_XS, weight=600,
                            color=theme.PRIMARY_TINT, mono=True,
                            fg_color=theme.PRIMARY_BADGE, corner_radius=theme.R_BADGE,
                            anchor="center", width=22, height=20)
        self._badge.grid(row=0, column=2, padx=(0, 12))
        self._badge.grid_remove()

        bind_click(self, command)
        self._bind_hover()

    def _bind_hover(self):
        def enter(_event=None):
            if not self._active:
                self.configure(fg_color=theme.BG_NAV_HOVER)

        def leave(_event=None):
            if not self._active:
                self.configure(fg_color="transparent")

        for node in _descendants(self):
            node.bind("<Enter>", enter, add="+")
            node.bind("<Leave>", leave, add="+")

    def set_active(self, value: bool) -> None:
        self._active = bool(value)
        if self._active:
            self.configure(fg_color=theme.BG_NAV_ACTIVE)
            self._icon.configure(text_color=theme.PRIMARY_LIGHT)
            self._label.configure(text_color=theme.TEXT)
        else:
            self.configure(fg_color="transparent")
            self._icon.configure(text_color=theme.TEXT_DIM)
            self._label.configure(text_color=theme.TEXT_MUTED)

    def set_badge(self, count) -> None:
        """Sayı 0/None ise rozeti gizler."""
        if not count:
            self._badge.grid_remove()
            return
        self._badge.configure(text=str(count))
        self._badge.grid()


class StatusCard(Card):
    """Sidebar altındaki canlı durum kartı."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, radius=theme.R_TILE, fill="#11151F",
                         border=theme.BORDER_SIDEBAR, **kwargs)
        self.grid_columnconfigure(1, weight=1)
        self._dot = StatusDot(self, theme.SUCCESS)
        self._dot.grid(row=0, column=0, rowspan=2, padx=(12, 10), pady=10, sticky="")
        self._title = label(self, "Hazır", size=theme.SIZE_SM, weight=800,
                            color=theme.TEXT, fg_color="transparent")
        self._title.grid(row=0, column=1, sticky="w", pady=(10, 0), padx=(0, 10))
        self._sub = label(self, "Ağ koruması aktif", size=theme.SIZE_XS, weight=600,
                          color=theme.TEXT_MUTED, fg_color="transparent")
        self._sub.grid(row=1, column=1, sticky="w", pady=(0, 10), padx=(0, 10))

    def set_status(self, title: str, subtitle: str = "", color: str = theme.SUCCESS) -> None:
        self._title.configure(text=elide(title, 22))
        self._sub.configure(text=elide(subtitle, 26))
        self._dot.set_color(color)


class ListRow(Card):
    """`Son İndirilenler` / `İndirilenler` satırı.

    `actions` `(etiket, komut)` çiftlerinden oluşur; ilki dolgulu, sonrakiler
    sade bağlantı olarak çizilir.
    """

    def __init__(self, parent, title: str, meta: str = "", icon_name: str = "film",
                 icon_fill: str = theme.ICON_FILL_VIDEO,
                 icon_color: str = theme.PRIMARY_LIGHT, actions=(), **kwargs):
        super().__init__(parent, radius=theme.R_TILE, **kwargs)
        self.grid_columnconfigure(1, weight=1)

        badge = ctk.CTkLabel(self, text=icon_text(icon_name), font=fonts.icon(17),
                             text_color=icon_color, fg_color=icon_fill,
                             corner_radius=9, width=34, height=34)
        badge.grid(row=0, column=0, rowspan=2, padx=(12, 12), pady=11)

        self._title = label(self, elide(title, 52), size=theme.SIZE_BASE, weight=700,
                            color=theme.TEXT, fg_color="transparent")
        self._title.grid(row=0, column=1, sticky="w", pady=(11, 0))
        self._meta = label(self, meta, size=theme.SIZE_XS, weight=600,
                           color=theme.TEXT_MUTED, fg_color="transparent")
        self._meta.grid(row=1, column=1, sticky="w", pady=(1, 11))

        for position, (text, command) in enumerate(actions):
            if position == 0:
                widget = label(self, f" {text} ", size=theme.SIZE_SM, weight=700,
                               color=theme.TEXT_MUTED, fg_color=theme.BG_ELEVATED,
                               corner_radius=theme.R_CHIP, anchor="center")
            else:
                widget = label(self, f" {text} ", size=theme.SIZE_SM, weight=700,
                               color=theme.TEXT_MUTED, fg_color="transparent",
                               anchor="center")
            widget.grid(row=0, column=2 + position, rowspan=2, padx=(0, 8))
            bind_click(widget, command)


class Collapsible(ctk.CTkFrame):
    """Katlanabilir bölüm — tasarımın `Gelişmiş` ve `İşlem günlüğü` panelleri.

    Gövde `.body` ile erişilir ve panel kapalıyken `grid_remove()` edilir;
    bu sayede kapalı panel yer kaplamaz ama widget'ları canlı kalır, arka
    plan iş parçacıklarından gelen güncellemeler hedefini şaşırmaz.
    """

    def __init__(self, parent, title: str, hint: str = "", expanded: bool = False,
                 **kwargs):
        super().__init__(parent, fg_color=theme.BG_CARD, corner_radius=theme.R_CARD_SM,
                         border_width=1, border_color=theme.BORDER, **kwargs)
        self.grid_columnconfigure(0, weight=1)
        self._expanded = bool(expanded)

        header = ctk.CTkFrame(self, fg_color="transparent", height=42)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(1, weight=1)
        header.grid_propagate(False)

        self._chevron = icon_label(header, "chevron", size=14, color=theme.TEXT_MUTED,
                                   fg_color="transparent", width=14)
        self._chevron.grid(row=0, column=0, padx=(16, 10), pady=12)
        label(header, title, size=theme.SIZE_SM, weight=700, color=theme.TEXT_MUTED,
              fg_color="transparent").grid(row=0, column=1, sticky="w")
        self._hint = label(header, hint, size=theme.SIZE_XS, weight=500,
                           color=theme.TEXT_MUTED, mono=True, fg_color="transparent")
        self._hint.grid(row=0, column=2, padx=(0, 16))

        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 14))
        self.body.grid_columnconfigure(0, weight=1)

        bind_click(header, self.toggle)
        self._apply()

    def _apply(self):
        self._chevron.configure(text=icon_text("chevron_down" if self._expanded else "chevron"))
        if self._expanded:
            self.body.grid()
        else:
            self.body.grid_remove()

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
        self._hint.configure(text=text)


class SettingRow(ctk.CTkFrame):
    """Ayarlar listesindeki satır: başlık + açıklama + sağda kontrol.

    Kontrol `control_factory(row)` ile kurulur; satır yerleşimi bilir, kontrolün
    ne olduğunu bilmez.
    """

    def __init__(self, parent, title: str, subtitle: str = "", control_factory=None,
                 last: bool = False, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.grid_columnconfigure(0, weight=1)

        # Baslik ve alt baslik tek bir kutuda tutulur; aksi halde sagdaki
        # kontrolun yuksekligi iki satiri birbirinden ayirir.
        text_box = ctk.CTkFrame(self, fg_color="transparent")
        text_box.grid(row=0, column=0, sticky="w", padx=18, pady=14)
        label(text_box, title, size=theme.SIZE_BASE, weight=700, color=theme.TEXT,
              fg_color="transparent").grid(row=0, column=0, sticky="w")
        label(text_box, subtitle, size=theme.SIZE_SM, weight=600, color=theme.TEXT_MUTED,
              fg_color="transparent").grid(row=1, column=0, sticky="w", pady=(2, 0))

        self.control = None
        if control_factory is not None:
            self.control = control_factory(self)
            if self.control is not None:
                self.control.grid(row=0, column=1, sticky="e", padx=(12, 18))

        if not last:
            Divider(self).grid(row=1, column=0, columnspan=2, sticky="ew")


class OptionPills(ctk.CTkFrame):
    """`CTkOptionMenu` sözleşmesini konuşan, tasarımın pill'leri olarak çizilen kontrol.

    Kalite ve ses seçenekleri çözümleme sonrası çalışma zamanında dolar ve
    `gui.py` bunlara açılır menü gibi davranır: `configure(values=…)`,
    `set(…)`, `get()`, `cget("values")`. Aynı sözleşmeyi burada uygulamak,
    görseli açılır menüden pill'e taşırken 25'ten fazla çağrı yerinde
    korumamızı sağlar.

    Değerler tam haliyle saklanır — `get()` motorun beklediği dizeyi aynen
    döndürür — ama pill üstünde kısaltılmış hali gösterilir:
    `🎬 1080p (1042 Parça)` -> etiket `1080p`, alt metin `1042 Parça`.
    """

    def __init__(self, parent, values=(), command=None, accent: str = theme.PRIMARY,
                 fill: str = theme.PRIMARY_FILL, ink: str = theme.PRIMARY_TINT,
                 max_label: int = 22, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._command = command
        self._accent = accent
        self._fill = fill
        self._ink = ink
        self._max_label = max_label
        self._values = []
        self._pills = []
        self._index = -1
        if values:
            self.configure(values=list(values))

    # -- gorunum -----------------------------------------------------------
    @staticmethod
    def _split(value: str):
        """Tam değeri (etiket, alt metin) olarak ikiye ayırır."""
        text = str(value).strip()
        # Bastaki emoji / bayrak gibi metin disi karakterleri at.
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

    def _rebuild(self):
        for pill in self._pills:
            pill.destroy()
        self._pills = []

        for position, value in enumerate(self._values):
            text, sub = self._split(value)
            pill = Pill(self, elide(text, self._max_label), elide(sub, 18),
                        accent=self._accent, fill=self._fill, ink=self._ink,
                        command=lambda i=position: self._pick(i))
            pill.grid(row=position // 4, column=position % 4, padx=(0, 6), pady=(0, 6),
                      sticky="w")
            self._pills.append(pill)
        self._paint()

    def _paint(self):
        for position, pill in enumerate(self._pills):
            pill.set_selected(position == self._index)

    def _pick(self, index: int):
        self._index = index
        self._paint()
        if self._command:
            self._command(self._values[index])

    # -- CTkOptionMenu sozlesmesi -----------------------------------------
    def configure(self, require_redraw=False, **kwargs):
        """`values` ve `command` seçeneklerini CTkOptionMenu gibi kabul eder."""
        if "values" in kwargs:
            self._values = [str(v) for v in kwargs.pop("values")]
            self._index = 0 if self._values else -1
            self._rebuild()
        if "command" in kwargs:
            self._command = kwargs.pop("command")
        if kwargs:
            super().configure(require_redraw=require_redraw, **kwargs)

    def cget(self, attribute_name):
        if attribute_name == "values":
            return list(self._values)
        return super().cget(attribute_name)

    def set(self, value) -> None:
        """Seçimi ayarlar. Bilinmeyen değer listeye eklenir (menü davranışı)."""
        value = str(value)
        if value not in self._values:
            self._values.append(value)
            self._rebuild()
        self._index = self._values.index(value)
        self._paint()

    def get(self) -> str:
        if 0 <= self._index < len(self._values):
            return self._values[self._index]
        return ""
