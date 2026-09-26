import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flet/flet.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:gal/gal.dart';
import 'package:open_filex/open_filex.dart';

@pragma('vm:entry-point')
void vdproForegroundCallback() {
  FlutterForegroundTask.setTaskHandler(_DownloadTaskHandler());
}

class _DownloadTaskHandler extends TaskHandler {
  @override
  Future<void> onStart(DateTime timestamp, TaskStarter starter) async {}

  @override
  void onRepeatEvent(DateTime timestamp) {}

  @override
  Future<void> onDestroy(DateTime timestamp, bool isTimeout) async {}
}

class AndroidMediaServiceControl extends FletService {
  static const int _serviceId = 2107;
  AndroidMediaServiceControl({required super.control});

  @override
  void init() {
    super.init();
    control.addInvokeMethodListener(_invokeMethod);
    FlutterForegroundTask.initCommunicationPort();
    FlutterForegroundTask.init(
      androidNotificationOptions: AndroidNotificationOptions(
        channelId: 'vdpro_downloads',
        channelName: 'Video indirmeleri',
        channelDescription: 'Etkin video indirmelerinin canlı ilerlemesi',
        onlyAlertOnce: true,
      ),
      iosNotificationOptions: const IOSNotificationOptions(
        showNotification: false,
        playSound: false,
      ),
      foregroundTaskOptions: ForegroundTaskOptions(
        eventAction: ForegroundTaskEventAction.nothing(),
        autoRunOnBoot: false,
        autoRunOnMyPackageReplaced: false,
        allowWakeLock: true,
        allowWifiLock: true,
      ),
    );
  }

  String _text(Map<String, dynamic> args, String key, [String fallback = '']) {
    return args[key]?.toString() ?? fallback;
  }

  Future<dynamic> _invokeMethod(String name, dynamic rawArgs) async {
    final args = rawArgs is Map
        ? Map<String, dynamic>.from(rawArgs as Map)
        : <String, dynamic>{};
    switch (name) {
      case 'request_permissions':
        return _requestPermissions();
      case 'http_request':
        return _httpRequest(args);
      case 'start_download':
        return _startDownload(_text(args, 'title', 'Video indiriliyor'));
      case 'update_download':
        return _updateDownload(
          _text(args, 'title', 'Video indiriliyor'),
          (args['progress'] as num?)?.toInt() ?? 0,
          _text(args, 'speed'),
          _text(args, 'eta'),
        );
      case 'finish_download':
        return _finishDownload(
          _text(args, 'title', 'Video'),
          args['success'] == true,
          _text(args, 'message'),
        );
      case 'publish_video':
        return _publishVideo(
          _text(args, 'path'),
          _text(args, 'album', 'VideoDownloaderPro'),
        );
      case 'stop_download':
        await FlutterForegroundTask.stopService();
        return true;
      case 'open_file':
        return _openFile(_text(args, 'path'));
      default:
        throw Exception('Unknown AndroidMediaService method: $name');
    }
  }

  Future<Map<String, bool>> _requestPermissions() async {
    if (!Platform.isAndroid) {
      return const {'notification': true, 'battery_optimization': true};
    }
    var notificationGranted =
        await FlutterForegroundTask.checkNotificationPermission() ==
        NotificationPermission.granted;
    if (!notificationGranted) {
      notificationGranted =
          await FlutterForegroundTask.requestNotificationPermission() ==
          NotificationPermission.granted;
    }
    var ignoresBatteryOptimization =
        await FlutterForegroundTask.isIgnoringBatteryOptimizations;
    if (!ignoresBatteryOptimization) {
      await FlutterForegroundTask.requestIgnoreBatteryOptimization();
      ignoresBatteryOptimization =
          await FlutterForegroundTask.isIgnoringBatteryOptimizations;
    }
    return {
      'notification': notificationGranted,
      'battery_optimization': ignoresBatteryOptimization,
    };
  }

  Future<Map<String, dynamic>> _httpRequest(Map<String, dynamic> args) async {
    final method = _text(args, 'method', 'GET').toUpperCase();
    final url = _text(args, 'url');
    if (url.isEmpty) throw const FormatException('HTTP URL is required');
    final timeoutSeconds =
        ((args['timeout_seconds'] as num?)?.toDouble() ?? 15.0).clamp(
          1.0,
          120.0,
        );
    final maxResponseBytes =
        ((args['max_response_bytes'] as num?)?.toInt() ?? 8 * 1024 * 1024)
            .clamp(1024, 16 * 1024 * 1024);
    final client = HttpClient()
      ..connectionTimeout = Duration(
        milliseconds: (timeoutSeconds * 1000).round(),
      )
      ..autoUncompress = true;
    try {
      final request = await client
          .openUrl(method, Uri.parse(url))
          .timeout(Duration(milliseconds: (timeoutSeconds * 1000).round()));
      request.followRedirects = args['follow_redirects'] != false;
      request.maxRedirects = 8;
      final rawHeaders = args['headers'];
      if (rawHeaders is Map) {
        for (final entry in rawHeaders.entries) {
          final name = entry.key.toString();
          if ({
            'content-length',
            'host',
            'connection',
          }.contains(name.toLowerCase())) {
            continue;
          }
          request.headers.set(name, entry.value.toString());
        }
      }
      final body = _text(args, 'body');
      if (body.isNotEmpty) request.add(utf8.encode(body));
      final response = await request.close().timeout(
        Duration(milliseconds: (timeoutSeconds * 1000).round()),
      );
      final bytes = <int>[];
      await for (final chunk in response.timeout(
        Duration(milliseconds: (timeoutSeconds * 1000).round()),
      )) {
        if (bytes.length + chunk.length > maxResponseBytes) {
          throw HttpException(
            'HTTP response exceeded $maxResponseBytes bytes',
            uri: Uri.parse(url),
          );
        }
        bytes.addAll(chunk);
      }
      final responseHeaders = <String, List<String>>{};
      response.headers.forEach((name, values) {
        responseHeaders[name] = List<String>.from(values);
      });
      final finalUrl = response.redirects.isNotEmpty
          ? response.redirects.last.location.toString()
          : url;
      return {
        'status': response.statusCode,
        'url': finalUrl,
        'headers': responseHeaders,
        'body_base64': base64Encode(bytes),
      };
    } finally {
      client.close(force: true);
    }
  }

  Future<bool> _startDownload(String title) async {
    if (!Platform.isAndroid) return false;
    if (await FlutterForegroundTask.isRunningService) {
      await FlutterForegroundTask.updateService(
        notificationTitle: title,
        notificationText: 'İndirme başlatılıyor…',
      );
      return true;
    }
    final result = await FlutterForegroundTask.startService(
      serviceId: _serviceId,
      serviceTypes: const [ForegroundServiceTypes.dataSync],
      notificationTitle: title,
      notificationText: 'İndirme başlatılıyor…',
      callback: vdproForegroundCallback,
    );
    return result is ServiceRequestSuccess;
  }

  Future<bool> _updateDownload(
    String title,
    int progress,
    String speed,
    String eta,
  ) async {
    if (!Platform.isAndroid) return false;
    final safeProgress = progress.clamp(0, 100);
    final details = <String>['%$safeProgress'];
    if (speed.isNotEmpty) details.add(speed);
    if (eta.isNotEmpty && eta != '--:--') details.add('Kalan: $eta');
    if (!await FlutterForegroundTask.isRunningService) {
      await _startDownload(title);
    }
    await FlutterForegroundTask.updateService(
      notificationTitle: title,
      notificationText: details.join(' • '),
    );
    return true;
  }

  Future<bool> _finishDownload(
    String title,
    bool success,
    String message,
  ) async {
    if (!Platform.isAndroid) return false;
    if (await FlutterForegroundTask.isRunningService) {
      await FlutterForegroundTask.updateService(
        notificationTitle: success
            ? 'İndirme tamamlandı: $title'
            : 'İndirme başarısız: $title',
        notificationText: message.isNotEmpty ? message : title,
      );
      unawaited(
        Future<void>.delayed(const Duration(seconds: 15), () async {
          await FlutterForegroundTask.stopService();
        }),
      );
    }
    return true;
  }

  Future<bool> _publishVideo(String path, String album) async {
    if (!Platform.isAndroid || path.isEmpty) return false;
    try {
      await Gal.putVideo(path, album: album);
      return true;
    } on GalException catch (error) {
      debugPrint('MediaStore publish failed: ${error.type.message}');
      return false;
    }
  }

  Future<bool> _openFile(String path) async {
    if (path.isEmpty) return false;
    final result = await OpenFilex.open(path);
    return result.type == ResultType.done;
  }

  @override
  void dispose() {
    control.removeInvokeMethodListener(_invokeMethod);
    super.dispose();
  }
}
