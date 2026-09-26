# -*- coding: utf-8 -*-
"""
Video Downloader Pro — Fast & Offline Test Runner.
Zero internet quota used. Runs pure unit & mocked integration test suites.
"""

import unittest
import sys
import os
import time

# Ensure stdout supports UTF-8 on Windows
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Add project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)


def run_all_tests():
    print("=" * 75)
    print("🧪 VIDEO DOWNLOADER PRO — TEST ALTYAPISI & REGRESSION GÜVENLİK AĞI")
    print("   [Mod: %100 Çevrimdışı / Sıfır İnternet / Mock Altyapısı]")
    print("=" * 75)
    
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=os.path.join(PROJECT_ROOT, "tests"), pattern="test_*.py")
    
    start_time = time.perf_counter()
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    duration = time.perf_counter() - start_time
    
    print("\n" + "=" * 75)
    print(f"📊 TEST ÖZETİ: {result.testsRun} Test Çalıştırıldı | Süre: {duration:.3f} saniye")
    
    if result.wasSuccessful():
        print(f"🎉 %100 BAŞARILI: {result.testsRun} / {result.testsRun} TEST SORUNSUZ GEÇTİ! ✅")
        print("=" * 75)
        return 0
    else:
        print(f"❌ BAŞARISIZ: {len(result.failures)} Hata, {len(result.errors)} İstisna tespit edildi.")
        print("=" * 75)
        return 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
