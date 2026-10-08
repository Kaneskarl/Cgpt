import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uuid/uuid.dart';

const attendanceActions = <String, String>{
  'am_in': 'Morning In',
  'am_out': 'Morning Out',
  'pm_in': 'Afternoon In',
  'pm_out': 'Afternoon Out',
};
const deviceChannel = MethodChannel('office_attendance/device');

String canonicalPayload(
  String intent,
  String id,
  int timestamp,
  String qr,
  String action,
) => 'attendance.$intent.v1\n$id\n$timestamp\n$qr\n$action';

String validateServer(String value, {bool allowHttp = kDebugMode}) {
  final uri = Uri.tryParse(value.trim());
  if (uri == null ||
      uri.host.isEmpty ||
      uri.userInfo.isNotEmpty ||
      uri.hasQuery ||
      uri.hasFragment ||
      (uri.path != '' && uri.path != '/') ||
      (uri.scheme != 'https' && !(allowHttp && uri.scheme == 'http'))) {
    throw const FormatException(
      'Enter a server address such as https://attendance.office.local. HTTP is allowed only in debug builds.',
    );
  }
  return uri.replace(path: '').toString();
}

class ApiError implements Exception {
  final int status;
  final String message;
  const ApiError(this.status, this.message);
  @override
  String toString() => message;
}

class AttendanceApi {
  AttendanceApi(this.baseUrl, {http.Client? client})
    : client = client ?? http.Client();
  final String baseUrl;
  final http.Client client;
  String? token, userId;
  String name = '';
  Map<String, String> get headers => {
    'Content-Type': 'application/json',
    if (token != null) 'Authorization': 'Bearer $token',
  };

  Future<Map<String, dynamic>> post(
    String path,
    Map<String, dynamic> body,
  ) async {
    final response = await client
        .post(
          Uri.parse('$baseUrl/api$path'),
          headers: headers,
          body: jsonEncode(body),
        )
        .timeout(const Duration(seconds: 15));
    final dynamic decoded;
    try {
      decoded = jsonDecode(response.body);
    } on FormatException {
      throw ApiError(
        response.statusCode,
        'Unexpected server response. Ask the admin to check the server.',
      );
    }
    if (response.statusCode >= 400) {
      final detail = decoded is Map ? decoded['detail'] : null;
      throw ApiError(
        response.statusCode,
        detail is String
            ? detail
            : 'Request rejected. Check the entered details.',
      );
    }
    return Map<String, dynamic>.from(decoded as Map);
  }

  Future<void> login(String username, String password) async {
    final result = await post('/auth/login', {
      'username': username,
      'password': password,
      'client': 'scanner',
    });
    token = result['token'] as String;
    userId = result['id'] as String;
    name = result['name'] as String;
  }

  Future<Uint8List?> photo(String employeeId) async {
    final response = await client
        .get(
          Uri.parse('$baseUrl/api/employees/$employeeId/photo'),
          headers: headers,
        )
        .timeout(const Duration(seconds: 10));
    return response.statusCode == 200 ? response.bodyBytes : null;
  }

  Future<Map<String, dynamic>> signedPacket(
    String intent,
    String qr,
    String action,
  ) async {
    final deviceId = (await SharedPreferences.getInstance()).getString(
      'device_id',
    );
    if (deviceId == null) {
      throw const ApiError(403, 'Enroll this phone before scanning.');
    }
    final id = const Uuid().v4(),
        timestamp = DateTime.now().millisecondsSinceEpoch;
    final signature = await deviceChannel.invokeMethod<String>('sign', {
      'payload': canonicalPayload(intent, id, timestamp, qr, action),
    });
    if (signature == null) {
      throw const ApiError(
        403,
        'Device key unavailable. Ask the admin to re-enroll this phone.',
      );
    }
    return {
      'request_id': id,
      'timestamp_ms': timestamp,
      'qr_code': qr,
      'action': action,
      'device_id': deviceId,
      'signature': signature,
    };
  }

  Future<Map<String, dynamic>> identify(String qr, String action) async =>
      post('/scanner/identify', await signedPacket('identify', qr, action));

  Future<void> enroll(String code, String name) async {
    final publicKey = await deviceChannel.invokeMethod<String>('publicKey');
    final result = await post('/devices/enroll', {
      'code': code.trim(),
      'name': name.trim(),
      'public_key': publicKey,
    });
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('device_id', result['device_id'] as String);
    await prefs.setString('device_server', baseUrl);
  }

  Future<Map<String, dynamic>?> pending() async {
    final value = (await SharedPreferences.getInstance()).getString(
      'pending_scan',
    );
    return value == null
        ? null
        : Map<String, dynamic>.from(jsonDecode(value) as Map);
  }

  Future<void> storePending(Map<String, dynamic> packet) async {
    final saved = await (await SharedPreferences.getInstance()).setString(
      'pending_scan',
      jsonEncode({'packet': packet, 'user_id': userId, 'server': baseUrl}),
    );
    if (!saved) {
      throw const ApiError(
        500,
        'Could not preserve this scan on the phone. Free storage and try again. No save request was sent.',
      );
    }
  }

  Future<void> clearPending() async {
    final cleared = await (await SharedPreferences.getInstance()).remove(
      'pending_scan',
    );
    if (!cleared) {
      throw const ApiError(
        500,
        'Could not clear the saved retry request. Check phone storage and retry to confirm the existing record safely.',
      );
    }
  }

  void close() {
    token = null;
    client.close();
  }
}
