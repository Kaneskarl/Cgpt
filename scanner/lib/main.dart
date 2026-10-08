import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:mobile_scanner/mobile_scanner.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'api.dart';

void main() => runApp(const ScannerApp());
const green = Color(0xff176b53);

class ScannerApp extends StatelessWidget {
  const ScannerApp({super.key});
  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'MPM Attendance',
    debugShowCheckedModeBanner: false,
    theme: ThemeData(
      colorScheme: ColorScheme.fromSeed(seedColor: green),
      scaffoldBackgroundColor: const Color(0xfff7f9f5),
      useMaterial3: true,
      inputDecorationTheme: const InputDecorationTheme(
        border: OutlineInputBorder(),
      ),
    ),
    home: const LoginScreen(),
  );
}

String friendlyError(Object error) =>
    error is ApiError || error is FormatException
    ? error.toString().replaceFirst('FormatException: ', '')
    : 'Could not reach the server. Check office Wi-Fi and the server address. Attendance is not confirmed until the server responds.';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});
  @override
  State<LoginScreen> createState() => _LoginState();
}

class _LoginState extends State<LoginScreen> {
  final server = TextEditingController(),
      username = TextEditingController(),
      password = TextEditingController();
  final form = GlobalKey<FormState>();
  bool busy = false;
  String? error;
  @override
  void initState() {
    super.initState();
    loadServer();
  }

  Future<void> loadServer() async {
    final prefs = await SharedPreferences.getInstance();
    if (mounted) server.text = prefs.getString('server') ?? '';
  }

  @override
  void dispose() {
    server.dispose();
    username.dispose();
    password.dispose();
    super.dispose();
  }

  Future<void> login() async {
    if (!form.currentState!.validate()) return;
    setState(() {
      busy = true;
      error = null;
    });
    AttendanceApi? api;
    try {
      final url = validateServer(server.text),
          prefs = await SharedPreferences.getInstance();
      final enrolledServer = prefs.getString('device_server');
      if (enrolledServer != null && enrolledServer != url) {
        throw const ApiError(
          403,
          'This phone is enrolled to another server. Ask the admin to revoke it before resetting app data.',
        );
      }
      api = AttendanceApi(url);
      await api.login(username.text.trim(), password.text);
      await prefs.setString('server', url);
      password.clear();
      if (!mounted) {
        api.close();
        return;
      }
      final activeApi = api;
      await Navigator.of(context).push(
        MaterialPageRoute<void>(builder: (_) => ScannerScreen(api: activeApi)),
      );
      api.close();
    } catch (e) {
      api?.close();
      if (mounted) setState(() => error = friendlyError(e));
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    body: SafeArea(
      child: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(28),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 440),
            child: Form(
              key: form,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Image.asset(
                    'assets/sda-logo.png',
                    width: 112,
                    height: 112,
                    semanticLabel: 'Seventh-day Adventist logo',
                  ),
                  const SizedBox(height: 24),
                  const Text(
                    'MPM Attendance',
                    textAlign: TextAlign.center,
                    style: TextStyle(fontSize: 28, fontWeight: FontWeight.w700),
                  ),
                  const SizedBox(height: 10),
                  const Text(
                    'Sign in as the operator of your authorized scanner.',
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 32),
                  TextFormField(
                    controller: server,
                    keyboardType: TextInputType.url,
                    autocorrect: false,
                    decoration: const InputDecoration(
                      labelText: 'Office server address',
                      hintText: 'https://attendance.office.local',
                    ),
                    validator: (v) {
                      try {
                        validateServer(v ?? '');
                        return null;
                      } catch (e) {
                        return friendlyError(e);
                      }
                    },
                  ),
                  const SizedBox(height: 18),
                  TextFormField(
                    controller: username,
                    autocorrect: false,
                    autofillHints: const [AutofillHints.username],
                    decoration: const InputDecoration(
                      labelText: 'Operator username',
                    ),
                    validator: (v) =>
                        (v ?? '').trim().isEmpty ? 'Enter your username' : null,
                  ),
                  const SizedBox(height: 18),
                  TextFormField(
                    controller: password,
                    obscureText: true,
                    autofillHints: const [AutofillHints.password],
                    decoration: const InputDecoration(labelText: 'Password'),
                    onFieldSubmitted: (_) {
                      if (!busy) login();
                    },
                    validator: (v) =>
                        (v ?? '').isEmpty ? 'Enter your password' : null,
                  ),
                  if (error != null)
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 16),
                      child: Text(
                        error!,
                        style: const TextStyle(color: Colors.red),
                      ),
                    ),
                  const SizedBox(height: 24),
                  FilledButton(
                    onPressed: busy ? null : login,
                    child: Padding(
                      padding: const EdgeInsets.all(14),
                      child: Text(busy ? 'Connecting…' : 'Sign in'),
                    ),
                  ),
                  const SizedBox(height: 20),
                  const Text(
                    'Connect to office Wi-Fi. Employees present their printed IDs; they do not need app accounts.',
                    textAlign: TextAlign.center,
                    style: TextStyle(fontSize: 12, color: Colors.black54),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    ),
  );
}

class ScannerScreen extends StatefulWidget {
  const ScannerScreen({super.key, required this.api});
  final AttendanceApi api;
  @override
  State<ScannerScreen> createState() => _ScannerState();
}

class _ScannerState extends State<ScannerScreen> with WidgetsBindingObserver {
  final camera = MobileScannerController(
    autoStart: false,
    formats: const [BarcodeFormat.qrCode],
    detectionTimeoutMs: 1500,
  );
  String action = 'am_in';
  String? deviceId, error, success;
  Map<String, dynamic>? pending;
  bool busy = true, background = false;
  String? lastQr;
  DateTime lastSeen = DateTime.fromMillisecondsSinceEpoch(0);
  final code = TextEditingController(),
      deviceName = TextEditingController(text: 'Office scanning phone');
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    initialize();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    camera.dispose();
    code.dispose();
    deviceName.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    background = state != AppLifecycleState.resumed;
    if (background) {
      camera.stop();
    } else if (!busy && pending == null && deviceId != null) {
      resumeCamera();
    }
  }

  Future<void> initialize() async {
    final prefs = await SharedPreferences.getInstance(),
        saved = await widget.api.pending();
    if (!mounted) return;
    setState(() {
      deviceId = prefs.getString('device_id');
      pending = saved;
      busy = false;
    });
    if (deviceId != null && pending == null) await resumeCamera();
  }

  Future<void> resumeCamera() async {
    if (!mounted || background || busy || pending != null) return;
    try {
      await camera.start();
    } catch (e) {
      if (mounted) {
        setState(
          () => error = 'Camera unavailable. Grant camera permission in Android settings, then tap Resume camera.',
        );
      }
    }
  }

  Future<void> enroll() async {
    if (code.text.trim().isEmpty || deviceName.text.trim().isEmpty) {
      setState(() => error = 'Enter the enrollment code and phone name.');
      return;
    }
    setState(() {
      busy = true;
      error = null;
    });
    try {
      await widget.api.enroll(code.text, deviceName.text);
      code.clear();
      await initialize();
    } catch (e) {
      if (mounted) setState(() => error = friendlyError(e));
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> changeMode(String? value) async {
    if (value == null || value == action || busy || pending != null) return;
    setState(() => busy = true);
    await camera.stop();
    if (!mounted) return;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Switch attendance action?'),
        content: Text(
          'The next scans will record ${attendanceActions[value]}. Make sure this is the correct action.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Switch'),
          ),
        ],
      ),
    );
    if (!mounted) return;
    setState(() {
      if (confirmed == true) action = value;
      busy = false;
    });
    await resumeCamera();
  }

  Future<void> detected(BarcodeCapture capture) async {
    if (busy || pending != null) return;
    final qr = capture.barcodes
        .map((b) => b.rawValue)
        .whereType<String>()
        .firstOrNull;
    if (qr == null) return;
    if (qr == lastQr && DateTime.now().difference(lastSeen).inSeconds < 5) {
      return;
    }
    lastQr = qr;
    lastSeen = DateTime.now();
    setState(() {
      busy = true;
      error = null;
      success = null;
    });
    await camera.stop();
    try {
      if (!qr.startsWith('dtr:v1:')) {
        throw const ApiError(422, 'This is not an employee attendance ID.');
      }
      final result = await widget.api.identify(qr, action),
          emp = Map<String, dynamic>.from(result['employee'] as Map);
      if (result['existing'] != null) {
        final existing = Map<String, dynamic>.from(result['existing'] as Map);
        throw ApiError(
          409,
          '${emp['name']}: ${attendanceActions[action]} already recorded at ${officeTime(existing['recorded_at'] as String)}.',
        );
      }
      Uint8List? photo;
      if (emp['has_photo'] == true) {
        photo = await widget.api.photo(emp['id'] as String);
      }
      if (!mounted) return;
      final confirmed = await showDialog<bool>(
        context: context,
        barrierDismissible: false,
        builder: (ctx) => AlertDialog(
          title: Text(attendanceActions[action]!),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (photo != null)
                ClipRRect(
                  borderRadius: BorderRadius.circular(16),
                  child: Image.memory(
                    photo,
                    width: 150,
                    height: 150,
                    fit: BoxFit.cover,
                  ),
                )
              else
                const Icon(Icons.person_outline, size: 80, color: green),
              const SizedBox(height: 16),
              Text(
                emp['name'] as String,
                textAlign: TextAlign.center,
                style: const TextStyle(
                  fontSize: 22,
                  fontWeight: FontWeight.bold,
                ),
              ),
              Text(emp['employee_no'] as String),
              const SizedBox(height: 14),
              Text(
                photo == null
                    ? 'No profile photo available. Verify the person against their printed ID before recording.'
                    : 'Verify that the person presenting the ID matches this photo.',
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 10),
              const Text(
                'No attendance has been saved yet.',
                style: TextStyle(fontSize: 12, color: Colors.black54),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Confirm & record'),
            ),
          ],
        ),
      );
      if (confirmed != true) return;
      final packet = await widget.api.signedPacket('scan', qr, action);
      await widget.api.storePending(packet);
      pending = await widget.api.pending();
      await submitPending();
    } catch (e) {
      if (mounted) setState(() => error = friendlyError(e));
    } finally {
      if (mounted) {
        setState(() => busy = false);
        await resumeCamera();
      }
    }
  }

  Future<void> submitPending() async {
    if (pending == null) return;
    if (pending!['user_id'] != widget.api.userId ||
        pending!['server'] != widget.api.baseUrl) {
      throw const ApiError(
        403,
        'An unresolved scan belongs to another operator or server. Sign in with the original operator account to retry.',
      );
    }
    try {
      final result = await widget.api.post(
        '/scans',
        Map<String, dynamic>.from(pending!['packet'] as Map),
      );
      await widget.api.clearPending();
      pending = null;
      final emp = Map<String, dynamic>.from(result['employee'] as Map),
          record = Map<String, dynamic>.from(result['attendance'] as Map);
      await HapticFeedback.mediumImpact();
      await SystemSound.play(SystemSoundType.click);
      if (mounted) {
        setState(() {
          error = null;
          success =
              '${emp['name']} · ${attendanceActions[record['action']]} saved at ${officeTime(record['recorded_at'] as String)}';
        });
      }
    } on ApiError catch (e) {
      if ([404, 409, 422].contains(e.status)) {
        await widget.api.clearPending();
        pending = null;
      }
      rethrow;
    }
  }

  Future<void> retry() async {
    setState(() {
      busy = true;
      error = null;
    });
    try {
      await submitPending();
    } catch (e) {
      if (mounted) setState(() => error = friendlyError(e));
    } finally {
      if (mounted) {
        setState(() => busy = false);
        await resumeCamera();
      }
    }
  }

  Future<void> resolveManually() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Admin review completed?'),
        content: const Text(
          'The scan may already be saved. Ask the admin to check the employee’s record first. Clear this request only after the admin has resolved it. Do not blindly scan again.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Admin resolved it'),
          ),
        ],
      ),
    );
    if (confirmed == true) {
      await widget.api.clearPending();
      if (mounted) {
        setState(() {
          pending = null;
          error = null;
        });
      }
      await resumeCamera();
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: Row(
        children: [
          Image.asset(
            'assets/sda-logo.png',
            width: 40,
            height: 40,
            semanticLabel: 'Seventh-day Adventist logo',
          ),
          const SizedBox(width: 8),
          const Flexible(child: Text('MPM Attendance')),
        ],
      ),
      actions: [
        IconButton(
          tooltip: 'Sign out',
          onPressed: busy ? null : () => Navigator.of(context).pop(),
          icon: const Icon(Icons.logout),
        ),
      ],
    ),
    body: SafeArea(
      child: deviceId == null
          ? enrollmentView()
          : Column(
              children: [
                Padding(
                  padding: const EdgeInsets.all(18),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Text(
                        'Operator: ${widget.api.name}',
                        style: const TextStyle(
                          fontSize: 12,
                          color: Colors.black54,
                        ),
                      ),
                      const SizedBox(height: 10),
                      DropdownButtonFormField<String>(
                        key: ValueKey(action),
                        initialValue: action,
                        decoration: const InputDecoration(
                          labelText: 'Attendance action',
                          filled: true,
                          fillColor: Color(0xffe6f1e8),
                        ),
                        items: attendanceActions.entries
                            .map(
                              (e) => DropdownMenuItem(
                                value: e.key,
                                child: Text(
                                  e.value,
                                  style: const TextStyle(
                                    fontSize: 20,
                                    fontWeight: FontWeight.bold,
                                  ),
                                ),
                              ),
                            )
                            .toList(),
                        onChanged: busy || pending != null ? null : changeMode,
                      ),
                      const SizedBox(height: 10),
                      const Text(
                        'Ask the employee to present their printed ID. Verify their identity before confirming.',
                        style: TextStyle(fontSize: 12),
                      ),
                    ],
                  ),
                ),
                if (pending != null)
                  Expanded(
                    child: SingleChildScrollView(
                      padding: const EdgeInsets.all(22),
                      child: Column(
                        children: [
                          const Icon(Icons.cloud_sync, size: 64, color: green),
                          const SizedBox(height: 18),
                          const Text(
                            'Save not confirmed',
                            style: TextStyle(
                              fontSize: 24,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                          const SizedBox(height: 12),
                          const Text(
                            'This scan may already be on the server. Retry the same request to confirm it safely. New scans are paused.',
                            textAlign: TextAlign.center,
                          ),
                          const SizedBox(height: 12),
                          Text(
                            'Request: ${(pending!['packet'] as Map)['request_id']}',
                            style: const TextStyle(fontSize: 11),
                          ),
                          const SizedBox(height: 20),
                          FilledButton(
                            onPressed: busy ? null : retry,
                            child: const Text('Retry same request'),
                          ),
                          TextButton(
                            onPressed: busy ? null : resolveManually,
                            child: const Text('Admin reviewed and resolved it'),
                          ),
                        ],
                      ),
                    ),
                  )
                else
                  Expanded(
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 18),
                      child: ClipRRect(
                        borderRadius: BorderRadius.circular(18),
                        child: MobileScanner(
                          controller: camera,
                          onDetect: detected,
                          errorBuilder: (context, e) => Center(
                            child: Padding(
                              padding: const EdgeInsets.all(24),
                              child: Column(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  const Icon(
                                    Icons.no_photography_outlined,
                                    size: 48,
                                  ),
                                  const SizedBox(height: 12),
                                  const Text(
                                    'Camera unavailable. Enable camera permission in Android settings.',
                                  ),
                                  TextButton(
                                    onPressed: resumeCamera,
                                    child: const Text('Resume camera'),
                                  ),
                                ],
                              ),
                            ),
                          ),
                        ),
                      ),
                    ),
                  ),
                if (busy)
                  const Padding(
                    padding: EdgeInsets.all(12),
                    child: LinearProgressIndicator(),
                  ),
                if (success != null) message(success!, false),
                if (error != null) message(error!, true),
                Padding(
                  padding: const EdgeInsets.all(14),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      const Icon(
                        Icons.verified_user_outlined,
                        color: green,
                        size: 16,
                      ),
                      const SizedBox(width: 6),
                      const Text(
                        'Authorized phone · server-recorded time',
                        style: TextStyle(fontSize: 11),
                      ),
                      if (error != null && pending == null)
                        TextButton(
                          onPressed: busy ? null : resumeCamera,
                          child: const Text('Resume camera'),
                        ),
                    ],
                  ),
                ),
              ],
            ),
    ),
  );
  Widget message(String text, bool failure) => Container(
    width: double.infinity,
    margin: const EdgeInsets.fromLTRB(18, 12, 18, 0),
    padding: const EdgeInsets.all(14),
    decoration: BoxDecoration(
      color: failure ? const Color(0xffffebe7) : const Color(0xffe5f3e9),
      borderRadius: BorderRadius.circular(10),
    ),
    child: Text(
      text,
      style: TextStyle(
        color: failure ? Colors.red.shade900 : green,
        fontSize: 13,
      ),
    ),
  );
  Widget enrollmentView() => SingleChildScrollView(
    padding: const EdgeInsets.all(24),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Icon(Icons.phonelink_lock, size: 64, color: green),
        const SizedBox(height: 20),
        const Text(
          'Authorize this phone',
          style: TextStyle(fontSize: 26, fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 12),
        const Text(
          'Ask the admin to generate a one-time code in the dashboard. Only one phone can be enrolled.',
        ),
        const SizedBox(height: 24),
        TextField(
          controller: deviceName,
          decoration: const InputDecoration(labelText: 'Phone name'),
          maxLength: 100,
        ),
        const SizedBox(height: 16),
        TextField(
          controller: code,
          autocorrect: false,
          decoration: const InputDecoration(labelText: 'Enrollment code'),
        ),
        if (error != null) message(error!, true),
        const SizedBox(height: 24),
        FilledButton(
          onPressed: busy ? null : enroll,
          child: Text(busy ? 'Enrolling…' : 'Enroll phone'),
        ),
      ],
    ),
  );
}

String officeTime(String timestamp) {
  final time = DateTime.parse(timestamp).toUtc().add(const Duration(hours: 8));
  return '${time.hour % 12 == 0 ? 12 : time.hour % 12}:${time.minute.toString().padLeft(2, '0')} ${time.hour < 12 ? 'AM' : 'PM'}';
}
