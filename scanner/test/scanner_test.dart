import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:office_scanner/api.dart';
import 'package:office_scanner/main.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });
  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(deviceChannel, null);
  });

  test('server validation rejects credentials, paths, and release HTTP', () {
    expect(
      validateServer('https://attendance.office.internal/'),
      'https://attendance.office.internal',
    );
    for (final value in [
      'http://server',
      'https://user:password@server',
      'https://server/api',
      'https://server?token=x',
      'not a URL',
    ]) {
      expect(
        () => validateServer(value, allowHttp: false),
        throwsFormatException,
      );
    }
    expect(
      validateServer('http://192.168.1.10:8000', allowHttp: true),
      'http://192.168.1.10:8000',
    );
  });
  test(
    'signature payload includes intent and all mutable attendance fields',
    () {
      expect(
        canonicalPayload('scan', '123', 1000, 'dtr:v1:abc', 'am_in'),
        'attendance.scan.v1\n123\n1000\ndtr:v1:abc\nam_in',
      );
      expect(
        canonicalPayload('identify', '123', 1000, 'dtr:v1:abc', 'am_in'),
        isNot(canonicalPayload('scan', '123', 1000, 'dtr:v1:abc', 'am_in')),
      );
    },
  );
  test(
    'login keeps operator token in memory and sends scanner client',
    () async {
      final api = AttendanceApi(
        'https://office',
        client: MockClient((request) async {
          expect(request.url.path, '/api/auth/login');
          expect(jsonDecode(request.body)['client'], 'scanner');
          return http.Response(
            jsonEncode({
              'token': 'test-token',
              'id': 'operator-id',
              'name': 'Operator',
            }),
            200,
          );
        }),
      );
      await api.login('operator', 'password');
      expect(api.token, 'test-token');
      expect(api.userId, 'operator-id');
      expect((await SharedPreferences.getInstance()).getKeys(), isEmpty);
      api.close();
      expect(api.token, isNull);
    },
  );
  test(
    'enrollment stores public binding and signing uses native device key',
    () async {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(deviceChannel, (call) async {
            if (call.method == 'publicKey') return 'PUBLIC KEY';
            expect(call.method, 'sign');
            expect(
              (call.arguments as Map)['payload'],
              startsWith('attendance.scan.v1\n'),
            );
            return 'SIGNED';
          });
      final api = AttendanceApi(
        'https://office',
        client: MockClient((request) async {
          expect(request.url.path, '/api/devices/enroll');
          expect(jsonDecode(request.body)['public_key'], 'PUBLIC KEY');
          return http.Response('{"device_id":"approved-phone"}', 201);
        }),
      );
      await api.enroll('one-time-code', 'Office phone');
      final packet = await api.signedPacket('scan', 'dtr:v1:abc', 'am_in');
      expect(packet['device_id'], 'approved-phone');
      expect(packet['signature'], 'SIGNED');
      expect(packet['request_id'], isNotEmpty);
      api.close();
    },
  );
  test(
    'pending requests survive a new client without changing request ID',
    () async {
      final api = AttendanceApi('https://office');
      api.userId = 'operator-id';
      final packet = {
        'request_id': 'original-id',
        'action': 'am_in',
        'signature': 'signed-payload',
      };
      await api.storePending(packet);
      final replacement = AttendanceApi('https://office');
      final saved = await replacement.pending();
      expect(saved!['packet'], packet);
      expect(saved['user_id'], 'operator-id');
      await replacement.clearPending();
      expect(await api.pending(), isNull);
      api.close();
      replacement.close();
    },
  );
  test('API errors preserve duplicate rejection messages', () async {
    final api = AttendanceApi(
      'https://office',
      client: MockClient(
        (_) async => http.Response(
          '{"detail":"Already recorded. No new entry saved."}',
          409,
        ),
      ),
    );
    await expectLater(
      api.post('/scans', {}),
      throwsA(
        isA<ApiError>()
            .having((e) => e.status, 'status', 409)
            .having((e) => e.message, 'message', contains('No new entry')),
      ),
    );
    api.close();
  });
  test('office times respect Manila dates across UTC midnight', () {
    expect(officeTime('2026-01-01T00:00:00Z'), '8:00 AM');
    expect(officeTime('2026-01-01T17:30:00Z'), '1:30 AM');
  });
  testWidgets('operator login screen validates the server before connecting', (
    tester,
  ) async {
    await tester.pumpWidget(const ScannerApp());
    await tester.pumpAndSettle();
    expect(find.text('Office Attendance'), findsOneWidget);
    await tester.tap(find.text('Sign in'));
    await tester.pumpAndSettle();
    expect(find.text('Enter your username'), findsOneWidget);
    expect(find.text('Enter your password'), findsOneWidget);
    expect(find.textContaining('Enter a server address'), findsOneWidget);
  });
}
