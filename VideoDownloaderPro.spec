# -*- mode: python ; coding: utf-8 -*-
"""
Video Downloader Pro — PyInstaller yapılandırması (tek doğruluk kaynağı).

build_exe.py bu dosyayı çağırır; hidden-import ve veri listeleri artık iki ayrı
yerde elle senkronize edilmez (bkz. C8).

Derleme:
    python build_exe.py            # önerilen (onefile)
    python build_exe.py --onedir   # klasör çıktısı
"""
import os
import sys
from PyInstaller.utils.hooks import collect_all, collect_submodules

# Tek dosya (onefile) mı yoksa klasör (onedir) mi üretileceği.
# CI ve yerel derleme aynı çıktıyı vermeli; varsayılan onefile.
ONEFILE = os.environ.get("VDP_BUILD_ONEDIR", "").strip().lower() not in ("1", "true", "yes")

PROJECT_ROOT = os.path.abspath(os.path.dirname(SPEC)) if 'SPEC' in locals() else os.getcwd()

datas = [
    ('extractors', 'extractors'),
    ('engine_core', 'engine_core'),
    ('ui', 'ui'),
    # Gömülü arayüz fontları ve ikonları
    ('assets', 'assets'),
]

binaries = []

hiddenimports = [
    # GUI & Grafik
    'customtkinter', 'tkinter', 'tkinter.ttk', 'tkinter.filedialog', 'tkinter.messagebox',
    'PIL', 'PIL.Image', 'PIL.ImageTk',
    # Ağ & Protokol
    'requests', 'urllib3', 'certifi', 'idna', 'charset_normalizer',
    'curl_cffi', 'curl_cffi.requests',
    'yt_dlp',
    # Şifreleme & Güvenlik
    'Crypto', 'Crypto.Cipher', 'Crypto.Cipher.AES', 'Crypto.Util.Padding',
    # Sistem & Veritabanı
    'sqlite3', 'logging', 'logging.handlers', 'ctypes', 'ctypes.wintypes',
    # Temel Uygulama Modülleri
    'exceptions', 'history', 'logger', 'engine', 'gui', 'downloader', 'sniffer', 'benchmark',
    # Engine Core Modülleri
    'engine_core',
    'engine_core.crypto',
    'engine_core.utils',
    'engine_core.downloader',
    'engine_core.pipeline',
    'engine_core.recovery',
    'engine_core.ffmpeg',
    # Extractor Modülleri
    'extractors',
    'extractors.base',
    'extractors.registry',
    'extractors.generic',
    'extractors.direct',
    'extractors.dailymotion',
    'extractors.generic_hls',
    'extractors.series_film',
    'extractors.universal',
    'extractors.episodes',
    'extractors.subtitles',
    'extractors.variants',
    # Embed Çözücüleri
    'extractors.embeds',
    'extractors.embeds.closeload',
    'extractors.embeds.dplayer',
    'extractors.embeds.mailru',
    'extractors.embeds.players',
    'extractors.embeds.sibnet',
    'extractors.embeds.streamwish',
    'extractors.embeds.vidmoly',
    'extractors.embeds.voe',
    # Platform Çözücüleri
    'extractors.platforms',
    'extractors.platforms.anime',
    'extractors.platforms.dizibox',
    'extractors.platforms.dizilla',
    'extractors.platforms.dizipal',
    'extractors.platforms.dizitime',
    'extractors.platforms.diziyou',
    'extractors.platforms.filmmodu',
    'extractors.platforms.fullhd',
    'extractors.platforms.hdfilmcehennemi',
    'extractors.platforms.jetfilmizle',
    'extractors.platforms.seven20p',
    'extractors.platforms.sezonlukdizi',
    'extractors.platforms.yabancidizi',
    # UI Modüler MVC Katmanı
    'ui',
    'ui.theme',
    'ui.fonts',
    'ui.icons',
    'ui.widgets',
    'ui.constants',
    'ui.config',
    'ui.app',
    'ui.state',
    'ui.state.app_state',
    'ui.views',
    'ui.views.shell',
    'ui.views.film',
    'ui.views.social',
    'ui.views.queue',
    'ui.views.library',
    'ui.views.converter',
    'ui.views.settings',
    'ui.views.modals',
    'ui.controllers',
    'ui.controllers.download',
    'ui.controllers.resolve',
    'ui.controllers.social',
    'ui.controllers.queue',
    'ui.controllers.history',
    'ui.controllers.converter',
    'ui.controllers.dpi',
    'ui.controllers.recovery',
    'ui.controllers.system',
]

# Dinamik alt modül taraması (Strategy Pattern & Plugin modülleri için tam güvence)
for dynamic_pkg in ('ui', 'engine_core', 'extractors', 'extractors.embeds', 'extractors.platforms'):
    try:
        sub_mods = collect_submodules(dynamic_pkg)
        hiddenimports.extend(sub_mods)
    except Exception as exc:
        print(f"[spec] Bilgi: collect_submodules('{dynamic_pkg}') -> {exc}")

# Üçüncü taraf karmaşık paketlerin tüm veri ve binary'lerini topla
for pkg in ('customtkinter', 'curl_cffi', 'yt_dlp', 'requests'):
    try:
        _d, _b, _h = collect_all(pkg)
        datas += _d
        binaries += _b
        hiddenimports += _h
    except Exception as exc:
        print(f"[spec] UYARI: collect_all('{pkg}') başarısız: {exc}")

# Yinelenen hiddenimports temizle
hiddenimports = sorted(list(set(hiddenimports)))

EXCLUDES = ['torch', 'tensorflow', 'scipy', 'sklearn', 'pandas',
            'matplotlib', 'cupy', 'transformers', 'notebook', 'scipy']

app_icon = os.path.join('assets', 'app_icon.ico')
icon_opt = app_icon if os.path.exists(app_icon) else None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

_UPX = False

if ONEFILE:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name='VideoDownloaderPro',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=_UPX,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=icon_opt,
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name='VideoDownloaderPro',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=_UPX,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=icon_opt,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=_UPX,
        upx_exclude=[],
        name='VideoDownloaderPro',
    )
