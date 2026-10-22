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

// The model catalogue (shared/catalogue.json, schema 2 since 0.7.0) is shared with the desktop app. It is copied into the
// APK's assets at build time, never edited or hand-copied here.
val catalogueDir = layout.buildDirectory.dir("generated/catalogue")
val copyCatalogue by tasks.registering(Copy::class) {
    from(rootProject.file("../shared/catalogue.json"))
    into(catalogueDir)
}
tasks.matching { it.name == "preBuild" }.configureEach { dependsOn(fetchSherpaAar, copyCatalogue) }

android {
    namespace = "app.hebrish.dictation"
    compileSdk = 36

    defaultConfig {
        applicationId = "app.hebrish.dictation"
        minSdk = 28
        // 36 since 0.8.0: Google Play refuses new apps and updates below it from 2026-08-31.
        targetSdk = 36
        versionCode = 14
        versionName = "0.7.3"
        // Phones only: x86 libs would add ~25 MB for emulator use nobody needs here.
        ndk { abiFilters += "arm64-v8a" }
    }

    // Two channels from one codebase (0.8.0, plan: Hebrish-App-Planning google-play.md). Same
    // applicationId, versions and app signing key in both, so a phone can move between them.
    // fdroid: the GitHub release APK (also on the CDN and fdroid.hebrish.app). play: the Google
    // Play AAB, without what Play policy refuses (src/play/AndroidManifest.xml). Code checks [Channel].
    flavorDimensions += "channel"
    productFlavors {
        create("fdroid") { dimension = "channel" }
        create("play") { dimension = "channel" }
    }
    buildFeatures { buildConfig = true }

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

    sourceSets["main"].assets.srcDir(catalogueDir)
    // The engine (catalogue, model store and download, recorder, transcriber) lives in
    // ../core so Hebrish Keyboard (the HeliBoard fork) compiles the same sources; see core/README.md.
    sourceSets["main"].java.srcDir("../core/src/main/java")

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
