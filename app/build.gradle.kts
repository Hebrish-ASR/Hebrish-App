import java.net.URI

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// sherpa-onnx ships its Kotlin API and native libs as one AAR on GitHub releases (not Maven).
// It is downloaded at build time rather than committed (50 MB).
val sherpaVersion = "1.13.8"
val sherpaAar = layout.projectDirectory.file("libs/sherpa-onnx-$sherpaVersion.aar")

val fetchSherpaAar by tasks.registering {
    outputs.file(sherpaAar)
    doLast {
        val f = sherpaAar.asFile
        if (!f.exists()) {
            f.parentFile.mkdirs()
            val url = "https://github.com/k2-fsa/sherpa-onnx/releases/download/v$sherpaVersion/sherpa-onnx-$sherpaVersion.aar"
            logger.lifecycle("Downloading $url")
            URI(url).toURL().openStream().use { input -> f.outputStream().use { input.copyTo(it) } }
        }
    }
}
tasks.matching { it.name == "preBuild" }.configureEach { dependsOn(fetchSherpaAar) }

android {
    namespace = "com.danielrosehill.codeswitchvoice"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.danielrosehill.codeswitchvoice"
        minSdk = 28
        targetSdk = 35
        versionCode = 2
        versionName = "0.2.0"
        // Phones only: x86 libs would add ~25 MB for emulator use nobody needs here.
        ndk { abiFilters += "arm64-v8a" }
    }

    signingConfigs {
        create("release") {
            // CI writes the keystore from secrets; locally point these env vars at your own.
            val ks = System.getenv("RELEASE_KEYSTORE")
            if (ks != null) {
                storeFile = file(ks)
                storePassword = System.getenv("RELEASE_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("RELEASE_KEY_ALIAS")
                keyPassword = System.getenv("RELEASE_KEY_PASSWORD")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = if (System.getenv("RELEASE_KEYSTORE") != null)
                signingConfigs.getByName("release") else signingConfigs.getByName("debug")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    packaging { jniLibs { useLegacyPackaging = true } }
}

dependencies {
    implementation(files(sherpaAar))
}
