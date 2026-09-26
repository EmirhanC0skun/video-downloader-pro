# Video Downloader Pro - Proje Kuralları (PROJECT_RULES)

Bu kurallar projenin yüksek performans, ağ stabilitesi, bellek güvenliği ve otonom mühendislik kalitesini korumak için zorunludur.

---

## ⚡ 4 Çekirdek Otonom Beceri (Universal Core Operating System)

Herhangi bir kullanıcı prompt'u veya hatırlatması gerekmeden otomatik olarak aktif olan 4 temel beceri:

1. **`supervisor`**: İşi parçalara bölme, alt-ajanları koordine etme ve büyük resmi/mimariyi koruma.
2. **`codebase-summary`**: Dosyaları ezbere okuyup token yakmak yerine dosya ve modül hiyerarşisini akıllıca özetleme.
3. **`systematic-debugging`**: Hata çıktığında ezbere kod değiştirmek yerine kök nedene (root cause) inerek hipotez-test döngüsüyle çözme.
4. **`verification-before-completion`**: Taze test ve derleme çıktısı görmeden "kod bitti / çözüldü" dememe (Iron Law: Evidence before claims).

---

## High-Throughput & Async Engine Rules (Video Downloader)

1. **ASYNC EVENT LOOP INTEGRATION:**
   - Never run blocking I/O (disk writes, network calls, CPU-heavy decodes) on the main asyncio event loop.
   - Offload file chunk writes and ffmpeg processes strictly to `concurrent.futures.ThreadPoolExecutor` or worker processes.
   - Reuse `aiohttp.ClientSession` / persistent HTTP keep-alive connections; never recreate sessions per chunk.

2. **MEMORY & STREAMING BUFFERS:**
   - Stream media chunks directly to disk using memory-bounded chunk buffers (e.g., 64KB - 1MB generators). Never buffer full video payloads in RAM.
   - Explicitly close abandoned stream responses to prevent socket descriptor leaks.

3. **PLAYWRIGHT SNIFFER INTEGRATION:**
   - Run network listeners (`page.on('response', ...)`) asynchronously without blocking navigation.
   - Isolate sniffer contexts; extract playlist/stream URLs (M3U8/MPD) immediately and tear down browser pages to conserve memory.
