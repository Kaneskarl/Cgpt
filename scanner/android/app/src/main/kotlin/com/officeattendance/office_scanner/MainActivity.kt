package com.officeattendance.office_scanner

import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.Signature

class MainActivity : FlutterActivity() {
    private val alias = "office_attendance_scanner_v1"
    private fun store(): KeyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "office_attendance/device")
            .setMethodCallHandler { call, result ->
                try {
                    when (call.method) {
                        "publicKey" -> {
                            if (!store().containsAlias(alias)) {
                                val generator = KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_RSA, "AndroidKeyStore")
                                generator.initialize(KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_SIGN)
                                    .setKeySize(2048)
                                    .setDigests(KeyProperties.DIGEST_SHA256)
                                    .setSignaturePaddings(KeyProperties.SIGNATURE_PADDING_RSA_PKCS1)
                                    .build())
                                generator.generateKeyPair()
                            }
                            val publicKey = store().getCertificate(alias).publicKey.encoded
                            val encoded = Base64.encodeToString(publicKey, Base64.NO_WRAP)
                            result.success("-----BEGIN PUBLIC KEY-----\n" + encoded.chunked(64).joinToString("\n") + "\n-----END PUBLIC KEY-----\n")
                        }
                        "sign" -> {
                            val payload = call.argument<String>("payload") ?: error("Missing payload")
                            val key = store().getKey(alias, null) as? java.security.PrivateKey ?: error("Device key missing")
                            val signature = Signature.getInstance("SHA256withRSA")
                            signature.initSign(key)
                            signature.update(payload.toByteArray(Charsets.UTF_8))
                            result.success(Base64.encodeToString(signature.sign(), Base64.NO_WRAP))
                        }
                        else -> result.notImplemented()
                    }
                } catch (error: Exception) {
                    result.error("DEVICE_KEY", "Device key unavailable; ask the admin to re-enroll this phone.", null)
                }
            }
    }
}
