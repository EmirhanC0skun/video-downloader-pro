# -*- coding: utf-8 -*-
"""
Video Downloader Pro — Windows Executable Build & Verification Script.

CustomTkinter tabanlı masaüstü uygulamasını PyInstaller ile bağımsız bir Windows
.exe dosyasına paketler ve derleme sonrası bütünlük testlerini (Smoke Test) çalıştırır.

Tek doğruluk kaynağı `VideoDownloaderPro.spec` dosyasıdır.

Kullanım:
    python build_exe.py             # tek dosya (onefile) → dist/VideoDownloaderPro.exe
    python build_exe.py --onedir    # klasör          → dist/VideoDownloaderPro/
    python build_exe.py --no-verify # derleme sonrası testi atla
"""

import os
import sys
import time
import subprocess

# Ensure UTF-8 stdout
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SPEC_FILE = os.path.join(PROJECT_ROOT, "VideoDownloaderPro.spec")
APP_NAME = "VideoDownloaderPro"


def verify_executable(exe_path):
    """
    Derlenen .exe dosyasının modül eksikliği (ImportError), veri dosyası eksikliği
    (FileNotFoundError) veya başlatma çökmesi olmadan çalışabildiğini test eder.
    """
    print("\n" + "-" * 80)
    print("🔍 DERLEME SONRASI BÜTÜNLÜK & BAŞLATMA DOĞRULAMASI (SMOKE TEST)")
    print("-" * 80)

    if not os.path.exists(exe_path):
        print(f"❌ Test başarısız: Hedef çalıştırılabilir dosya bulunamadı: {exe_path}")
        return False

    size_mb = os.path.getsize(exe_path) / (1024 * 1024)
    print(f"📦 Dosya Boyutu: {size_mb:.2f} MB")
    if size_mb < 5.0:
        print("❌ Uyarı: Çıktı dosyası şüpheli derecede küçük (< 5MB)!")
        return False

    # Test 1: CLI Yardım Çağrısı (Python çekirdeği, stdlib, engine, downloader ve argparser yükleme testi)
    print("⏳ Test 1/2: Çekirdek modüllerin yüklenmesi (--cli -h)...")
    try:
        res = subprocess.run(
            [exe_path, "--cli", "-h"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=25
        )
        combined_output = (res.stdout or "") + (res.stderr or "")
        if "Traceback (most recent call last):" in combined_output:
            print("❌ Test 1 Başarısız: Başlatma sırasında Python Traceback oluştu:")
            print(combined_output)
            return False
        if res.returncode != 0:
            print(f"❌ Test 1 Başarısız: Çıkış kodu {res.returncode}")
            print(combined_output)
            return False
        print("✅ Test 1 Başarılı: Çekirdek bağımlılıklar ve CLI yardımcısı hatasız yüklendi.")
    except subprocess.TimeoutExpired:
        print("❌ Test 1 Başarısız: Zaman aşımı (25s).")
        return False
    except Exception as e:
        print(f"❌ Test 1 Başarısız: {e}")
        return False

    # Test 2: GUI ortamı ve pencere başlatma testi (--test-gui)
    # Tüm sayfaları ve widget'ları inşa eder, update() çağırır ve hatasız kapanır.
    print("⏳ Test 2/2: GUI ortamı ve pencere başlatma testi (--test-gui)...")
    try:
        res2 = subprocess.run(
            [exe_path, "--test-gui"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=25
        )
        combined_output2 = (res2.stdout or "") + (res2.stderr or "")
        if "Traceback (most recent call last):" in combined_output2:
            print("❌ Test 2 Başarısız: GUI başlatma sırasında Python Traceback oluştu:")
            print(combined_output2)
            return False
        if res2.returncode != 0:
            print(f"❌ Test 2 Başarısız: GUI başlatma çıkış kodu {res2.returncode}")
            print(combined_output2)
            return False
        print("✅ Test 2 Başarılı: GUI, temalar ve CustomTkinter tüm sayfalarla hatasız başlatıldı.")
    except subprocess.TimeoutExpired:
        print("❌ Test 2 Başarısız: GUI başlatma zaman aşımına uğradı (25s).")
        return False
    except Exception as e:
        print(f"❌ Test 2 Başarısız: {e}")
        return False

    print("-" * 80)
    print("🎉 TÜM DOĞRULAMA TESTLERİ GEÇTİ: Binary bağımsız çalışmaya hazır!")
    print("-" * 80)
    return True


def build_windows_exe(onedir=False, verify=True):
    print("=" * 80)
    print("📦 VIDEO DOWNLOADER PRO — WINDOWS EXE DERLEME ARACI")
    print("=" * 80)

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("❌ PyInstaller kütüphanesi bulunamadı.")
        print("💡 Yüklemek için: pip install -r requirements.txt")
        return False

    if not os.path.exists(SPEC_FILE):
        print(f"❌ Spec dosyası bulunamadı: {SPEC_FILE}")
        return False

    env = os.environ.copy()
    if onedir:
        env["VDP_BUILD_ONEDIR"] = "1"

    # Önceki derlenmiş VideoDownloaderPro.exe açık kalmışsa [WinError 5] Erişim engellendi
    # hatasını önlemek için arka planda çalışan örnekleri sonlandır
    if sys.platform == "win32":
        try:
            subprocess.run(["taskkill", "/F", "/IM", f"{APP_NAME}.exe"], capture_output=True, check=False)
            time.sleep(0.3)
        except Exception:
            pass

    cmd = [sys.executable, "-m", "PyInstaller", SPEC_FILE, "--noconfirm", "--clean"]

    print(f"🚀 Derleme başlatılıyor: {APP_NAME} ({'onedir' if onedir else 'onefile'})")
    print(f"⚙️  Komut: {' '.join(cmd)}\n")

    try:
        subprocess.run(cmd, check=True, cwd=PROJECT_ROOT, env=env)
    except subprocess.CalledProcessError as e:
        print(f"❌ Derleme hatası oluştu (çıkış kodu {e.returncode}).")
        return False
    except Exception as e:
        print(f"❌ Beklenmeyen hata: {e}")
        return False

    dist_dir = os.path.join(PROJECT_ROOT, "dist")
    exe_target = os.path.join(dist_dir, APP_NAME, APP_NAME + ".exe") if onedir else os.path.join(dist_dir, APP_NAME + ".exe")

    if not os.path.exists(exe_target):
        print(f"❌ Derleme bitti ancak beklenen çıktı yok: {exe_target}")
        return False

    print("\n" + "=" * 80)
    print("🎉 Windows EXE başarıyla derlendi!")
    print(f"📂 Çıktı: {exe_target}")
    print("=" * 80)

    if verify:
        if not verify_executable(exe_target):
            return False

    return True


if __name__ == "__main__":
    onedir_mode = "--onedir" in sys.argv
    skip_verify = "--no-verify" in sys.argv
    ok = build_windows_exe(onedir=onedir_mode, verify=not skip_verify)
    sys.exit(0 if ok else 1)
