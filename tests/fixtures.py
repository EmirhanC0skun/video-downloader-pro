# -*- coding: utf-8 -*-
"""
Mock Fixtures and Sample Payloads for 100% Offline Testing.
Zero Internet Quota Used.
"""

SAMPLE_MASTER_M3U8 = """#EXTM3U
#EXT-X-VERSION:3
#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",NAME="Turkish Dubbing",DEFAULT=YES,AUTOSELECT=YES,LANGUAGE="tr",URI="audio_tr.m3u8"
#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",NAME="English Original",DEFAULT=NO,AUTOSELECT=NO,LANGUAGE="en",URI="audio_en.m3u8"
#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="subs",NAME="Turkish",DEFAULT=YES,AUTOSELECT=YES,LANGUAGE="tr",URI="sub_tr.vtt"
#EXT-X-STREAM-INF:BANDWIDTH=5000000,RESOLUTION=1920x1080,AUDIO="audio",SUBTITLES="subs"
video_1080p.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=2500000,RESOLUTION=1280x720,AUDIO="audio",SUBTITLES="subs"
video_720p.m3u8
"""

SAMPLE_MEDIA_M3U8 = """#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:6
#EXT-X-MEDIA-SEQUENCE:0
#EXTINF:6.000,
seg-0.ts
#EXTINF:6.000,
seg-1.ts
#EXTINF:4.500,
seg-2.ts
#EXT-X-ENDLIST
"""

SAMPLE_VTT_SUBTITLE = """WEBVTT

00:00:01.500 --> 00:00:04.000
Video Downloader Pro Test Altyazısı

00:00:04.500 --> 00:00:08.200
İkinci satır altyazı metni (Örnek)
"""

SAMPLE_CURL_COMMAND = """curl 'https://video.example.com/stream/hls/master.m3u8' \
  -H 'authority: video.example.com' \
  -H 'accept: */*' \
  -H 'referer: https://example.com/watch/123' \
  -H 'user-agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36' \
  --compressed"""

SAMPLE_HTML_WITH_IFRAME = """<!DOCTYPE html>
<html>
<head><title>Test Film İzle</title></head>
<body>
<h1>Örnek Test Filmi</h1>
<iframe src="https://player.example.com/embed/vid123" width="100%" height="100%"></iframe>
</body>
</html>
"""

SAMPLE_HTML_WITH_JWPLAYER = """<!DOCTYPE html>
<html>
<head><title>JWPlayer Test</title></head>
<body>
<div id="player"></div>
<script>
jwplayer("player").setup({
    file: "https://stream.example.com/vod/video.m3u8",
    title: "JWPlayer Test Video",
    tracks: [{
        file: "https://stream.example.com/vod/subtitles.vtt",
        label: "Turkish",
        kind: "captions",
        "default": true
    }]
});
</script>
</body>
</html>
"""
