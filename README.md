# Attendance Android test app

Built from source commit `fabf65661e0bb471d0ba03e3e40fc5ef91b9866d` using `flutter build apk --debug --split-per-abi`. Android 8.0 or newer is required.

Download the APK matching your phone. Most modern Android phones use ARM64:

- [ARM64 APK — most modern phones](https://github.com/Kaneskarl/Cgpt/raw/refs/heads/android-test-downloads/app-arm64-v8a-debug.apk)
- [32-bit ARM APK — older ARM phones](https://github.com/Kaneskarl/Cgpt/raw/refs/heads/android-test-downloads/app-armeabi-v7a-debug.apk)
- [x86-64 APK — compatible Intel devices/emulators](https://github.com/Kaneskarl/Cgpt/raw/refs/heads/android-test-downloads/app-x86_64-debug.apk)

Transfer the matching APK to the designated phone and open it to install. Sign in with an operator account, enter your running office server address, and enroll the phone using the admin dashboard's Scanner device page. The phone and server need network access to each other.

These are debug-signed test builds. Use disposable records over HTTP; configure HTTPS before real employee use. Windows, physical phone/camera/Keystore, and printer acceptance checks remain.

[Windows setup guide](https://github.com/Kaneskarl/Cgpt/blob/main/docs/WINDOWS_SETUP.md) · [Application source](https://github.com/Kaneskarl/Cgpt/tree/main)

This branch contains downloads only. Source is maintained on `main`. Checksums are listed in `SHA256SUMS`.
