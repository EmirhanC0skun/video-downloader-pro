# -*- coding: utf-8 -*-
"""
Masaüstü çekirdeğini mobil pakete senkronize eder (C1).

`android_app/core/` dizini ÜRETİLMİŞ bir kopyadır — elle düzenlenmemelidir.
Flet APK derlemesi yalnızca `android_app/` ağacını paketlediği için çekirdek
modüllerin orada fiziksel olarak bulunması gerekir; tek doğruluk kaynağı ise
depo kökündeki dosyalardır.

Kullanım:
    python tools/sync_mobile_core.py           # kopyala
    python tools/sync_mobile_core.py --check   # yalnızca doğrula (CI / test)

--check modu, kopya kökten ayrışmışsa 1 ile çıkar.
"""

import filecmp
import os
import shutil
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOBILE_CORE = os.path.join(PROJECT_ROOT, "android_app", "core")

# Mobil çekirdeğe yansıtılan dosyalar. Yeni bir çekirdek modül eklenirse
# buraya da eklenmelidir; tests/test_mobile_core_sync.py bunu doğrular.
SYNCED_FILES = [
    "engine.py",
    os.path.join("engine_core", "__init__.py"),
    os.path.join("engine_core", "crypto.py"),
    os.path.join("engine_core", "utils.py"),
    os.path.join("engine_core", "ffmpeg.py"),
    os.path.join("engine_core", "downloader.py"),
    os.path.join("engine_core", "pipeline.py"),
    os.path.join("engine_core", "recovery.py"),
    "extractor.py",
    "sniffer.py",
    "history.py",
    "logger.py",
    "exceptions.py",
    "downloader.py",
    os.path.join("extractors", "__init__.py"),
    os.path.join("extractors", "base.py"),
    os.path.join("extractors", "registry.py"),
    os.path.join("extractors", "generic.py"),
    os.path.join("extractors", "direct.py"),
    os.path.join("extractors", "dailymotion.py"),
    os.path.join("extractors", "generic_hls.py"),
    os.path.join("extractors", "series_film.py"),
    os.path.join("extractors", "universal.py"),
    os.path.join("extractors", "subtitles.py"),
    os.path.join("extractors", "variants.py"),
    os.path.join("extractors", "episodes.py"),
    # Embeds package
    os.path.join("extractors", "embeds", "__init__.py"),
    os.path.join("extractors", "embeds", "vidmoly.py"),
    os.path.join("extractors", "embeds", "voe.py"),
    os.path.join("extractors", "embeds", "streamwish.py"),
    os.path.join("extractors", "embeds", "sibnet.py"),
    os.path.join("extractors", "embeds", "closeload.py"),
    os.path.join("extractors", "embeds", "dplayer.py"),
    os.path.join("extractors", "embeds", "mailru.py"),
    os.path.join("extractors", "embeds", "players.py"),
    # Platforms package
    os.path.join("extractors", "platforms", "__init__.py"),
    os.path.join("extractors", "platforms", "dizipal.py"),
    os.path.join("extractors", "platforms", "dizitime.py"),
    os.path.join("extractors", "platforms", "filmmodu.py"),
    os.path.join("extractors", "platforms", "dizilla.py"),
    os.path.join("extractors", "platforms", "jetfilmizle.py"),
    os.path.join("extractors", "platforms", "sezonlukdizi.py"),
    os.path.join("extractors", "platforms", "yabancidizi.py"),
    os.path.join("extractors", "platforms", "hdfilmcehennemi.py"),
    os.path.join("extractors", "platforms", "diziyou.py"),
    os.path.join("extractors", "platforms", "dizibox.py"),
    os.path.join("extractors", "platforms", "anime.py"),
    os.path.join("extractors", "platforms", "fullhd.py"),
    os.path.join("extractors", "platforms", "seven20p.py"),
]


def _pairs():
    for rel in SYNCED_FILES:
        yield os.path.join(PROJECT_ROOT, rel), os.path.join(MOBILE_CORE, rel)


def check():
    """Kopyanın kökle birebir aynı olup olmadığını döndürür: (uyumlu_mu, sorunlar)."""
    problems = []
    for src, dst in _pairs():
        rel = os.path.relpath(dst, PROJECT_ROOT)
        if not os.path.exists(src):
            problems.append(f"kaynak eksik: {os.path.relpath(src, PROJECT_ROOT)}")
        elif not os.path.exists(dst):
            problems.append(f"mobil kopya eksik: {rel}")
        elif not filecmp.cmp(src, dst, shallow=False):
            problems.append(f"ayrışmış: {rel}")
    return (not problems), problems


def sync():
    copied = 0
    for src, dst in _pairs():
        if not os.path.exists(src):
            print(f"[!] Kaynak bulunamadı, atlanıyor: {src}")
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.exists(dst) and filecmp.cmp(src, dst, shallow=False):
            continue
        shutil.copy2(src, dst)
        copied += 1
        print(f"  -> {os.path.relpath(dst, PROJECT_ROOT)}")

    init_py = os.path.join(MOBILE_CORE, "__init__.py")
    if not os.path.exists(init_py):
        with open(init_py, "w", encoding="utf-8") as f:
            f.write("# ÜRETİLMİŞ paket — bkz. tools/sync_mobile_core.py\n")
    return copied


def main():
    if "--check" in sys.argv:
        ok, problems = check()
        if ok:
            print("[OK] Mobil cekirdek masaustu cekirdegiyle senkron.")
            return 0
        print("[X] Mobil cekirdek ayrismiş:")
        for p in problems:
            print("   -", p)
        print("\nDuzeltmek icin: python tools/sync_mobile_core.py")
        return 1

    print("Mobil cekirdek senkronize ediliyor (android_app/core)...")
    n = sync()
    print(f"[OK] Tamamlandi: {n} dosya guncellendi, {len(SYNCED_FILES) - n} dosya zaten gunceldi.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
