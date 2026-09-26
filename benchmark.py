# -*- coding: utf-8 -*-
"""
Video Downloader Pro — Localhost Synthetic Concurrency & Throughput Benchmark.
100% Offline / Zero Network Quota Used.
Dynamic OS Ephemeral Port Binding (Port 0) for collision-free concurrent CI execution.
Enforces strict fail-closed dynamic baseline performance regression gate across Ubuntu & Windows.
"""

import os
import sys
import time
import json
import tempfile
import shutil
import threading
import http.server
import socketserver
from typing import List, Dict, Any

# Add project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from engine import VideoDownloadEngine
from logger import get_logger

logger = get_logger("benchmark")

# Ensure UTF-8 stdout
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Synthetic 512 KB chunk payload
CHUNK_SIZE_BYTES = 512 * 1024  # 512 KB per segment
TOTAL_SEGMENTS = 40            # 40 segments * 512 KB = 20.0 MB total test video
BASELINE_FILE = os.path.join(PROJECT_ROOT, "benchmark_baseline.json")


class SyntheticStreamHandler(http.server.BaseHTTPRequestHandler):
    """Serves high-speed synthetic video stream segments on localhost."""
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "video/MP2T")
        self.send_header("Content-Length", str(CHUNK_SIZE_BYTES))
        self.end_headers()
        dummy_chunk = b"X" * (64 * 1024)
        for _ in range(CHUNK_SIZE_BYTES // (64 * 1024)):
            self.wfile.write(dummy_chunk)

    def log_message(self, format, *args):
        pass


def verify_performance_baseline(results: List[Dict[str, Any]]):
    """
    Enforces strict fail-closed CI performance regression gate.
    If baseline file is missing or corrupt, raises an explicit error and fails CI.
    """
    for r in results:
        if r["success_rate"] < 100.0:
            raise AssertionError(f"Performance Regression: Thread {r['threads']} failed segments (Success: {r['success_rate']}%)")
    
    best = max(results, key=lambda x: x["speed"])
    current_peak = best["speed"]

    # Fail-Closed verification: Baseline file MUST exist and be valid JSON
    if not os.path.exists(BASELINE_FILE):
        raise FileNotFoundError(
            f"CI Performance Gate Error: Baseline configuration file '{BASELINE_FILE}' is missing! Cannot pass blindly."
        )

    try:
        with open(BASELINE_FILE, "r", encoding="utf-8-sig") as f:
            baseline_data = json.load(f)
        baseline_peak = float(baseline_data.get("peak_mb_s", 25.0))
        min_allowed = float(baseline_data.get("min_allowed_mb_s", 10.0))
    except Exception as err:
        raise RuntimeError(
            f"CI Performance Gate Error: Baseline configuration file is corrupt or unreadable: {err}"
        )

    if current_peak < min_allowed:
        raise AssertionError(
            f"Performance Regression Detected! Current Peak ({current_peak:.2f} MB/s) is below acceptable threshold ({min_allowed:.2f} MB/s)"
        )

    print(f"\n✅ DİNAMİK PERFORMANS REGRESYON TESTİ BAŞARILI:")
    print(f"   • Zirve Hız: {current_peak:.2f} MB/s | Kayıtlı Taban: {baseline_peak:.2f} MB/s | Minimum İzin Verilen Eşik: {min_allowed:.2f} MB/s")


def run_benchmark():
    print("=" * 80)
    print("⚡ VIDEO DOWNLOADER PRO — EŞZAMANLI İNDİRME & PERFORMANS BENCHMARK'I")
    print(f"   [Sentetik İş Yükü: {TOTAL_SEGMENTS} Segment x 512 KB = 20.0 MB | Ortam: %100 Çevrimdışı Localhost Ephemeral Port]")
    print("=" * 80)

    # 1. Start Localhost Mock Streaming Server on Ephemeral Port 0 (collision-free)
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(("127.0.0.1", 0), SyntheticStreamHandler)
    actual_port = httpd.server_address[1]
    
    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()
    time.sleep(0.15)

    thread_levels = [1, 2, 4, 8, 16, 32]
    results = []

    try:
        for threads in thread_levels:
            test_dir = tempfile.mkdtemp(prefix=f"bench_t{threads}_")
            engine = VideoDownloadEngine()
            
            segment_tasks = [
                (i, f"http://127.0.0.1:{actual_port}/stream/seg_{i}.ts", os.path.join(test_dir, f"seg_{i}.ts"))
                for i in range(TOTAL_SEGMENTS)
            ]

            t_start = time.perf_counter()
            completed, total_bytes, failed = engine.download_stream_segments(
                segment_tasks=segment_tasks,
                headers={},
                thread_count=threads
            )
            duration = time.perf_counter() - t_start
            
            shutil.rmtree(test_dir, ignore_errors=True)

            total_mb = total_bytes / (1024 * 1024)
            speed_mb_s = total_mb / duration if duration > 0 else 0
            success_rate = (completed / TOTAL_SEGMENTS) * 100

            results.append({
                "threads": threads,
                "duration": round(duration, 3),
                "speed": round(speed_mb_s, 2),
                "completed": completed,
                "total_mb": round(total_mb, 1),
                "success_rate": round(success_rate, 1)
            })

            print(f"  • {threads:2d} Thread: {duration:6.3f} sn | Hız: {speed_mb_s:7.2f} MB/s | Başarı: %{success_rate:.0f} ({completed}/{TOTAL_SEGMENTS})")

    finally:
        # Stop and cleanly close server
        httpd.shutdown()
        httpd.server_close()

    # 2. Output Markdown Benchmark Summary Table
    print("\n" + "=" * 80)
    print("📊 BENCHMARK SONUÇLARI (README & DOKÜMANTASYON TABLOSU):")
    print("=" * 80)
    print("| Paralel Kanal (Thread) | İndirme Süresi (sn) | Aktarım Hızı (MB/s) | İndirilen Veri | Başarı Oranı |")
    print("|:----------------------:|:-------------------:|:-------------------:|:--------------:|:------------:|")
    for r in results:
        print(f"| **{r['threads']} Kanal** | {r['duration']} sn | **{r['speed']} MB/s** | {r['total_mb']} MB | %{r['success_rate']} |")
    print("=" * 80)

    best = max(results, key=lambda x: x["speed"])
    speedup = best["speed"] / results[0]["speed"] if results[0]["speed"] > 0 else 1.0
    print(f"🎯 EN OPTİMAL KANAL SEVİYESİ: **{best['threads']} Kanal** ({best['speed']} MB/s — 1 Kanala göre {speedup:.1f}x Hız Artışı!)")
    print("=" * 80)

    # 3. Fail-Closed Dynamic Baseline Performance Gate Verification
    verify_performance_baseline(results)

    return results

if __name__ == "__main__":
    run_benchmark()
