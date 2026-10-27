plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// sherpa-onnx is built from source (app/src/main/cpp/CMakeLists.txt, submodules in
// ../third_party) since 1.000: F-Droid refuses the prebuilt GitHub release AAR used before
// (docs/fdroid-main.md). Its Kotlin API is vendored in src/main/java/com/k2fsa/sherpa/onnx.
// Bump all three together: the submodule, the vendored .kt files and this string.
val sherpaVersion = "1.13.8"
// ONNX Runtime from Maven Central only. One version feeds both the runtime dependency (the
// libonnxruntime.so in the APK) and the headers and .so the JNI library is linked against.
// sherpa-onnx 1.13.8 is tested upstream with 1.28.x; Marmalade STT ships 1.28.0.
val onnxRuntimeVersion = "1.28.0"

// The model catalogue (shared/catalogue.json, schema 2 since 0.7.0) is shared with the desktop app. It is copied into the
// APK's assets at build time, never edited or hand-copied here. So is shared/updates.json, the What's new list
// (UpdatesActivity) baked from hebrish.app/changelog by scripts/bake_updates.py before each release.
val catalogueDir = layout.buildDirectory.dir("generated/catalogue")
val copyCatalogue by tasks.registering(Copy::class) {
    from(rootProject.file("../shared/catalogue.json"))
    from(rootProject.file("../shared/updates.json"))
    into(catalogueDir)
}
tasks.matching { it.name == "preBuild" }.configureEach { dependsOn(copyCatalogue) }

android {
    namespace = "app.hebrish.dictation"
    compileSdk = 36

    defaultConfig {
        applicationId = "app.hebrish.dictation"
        minSdk = 28
        // 36 since 0.8.0: Google Play refuses new apps and updates below it from 2026-08-31.
        targetSdk = 36
        versionCode = 29
        versionName = "1.005"
        // Phones only: x86 libs would add ~25 MB for emulator use nobody needs here.
        ndk { abiFilters += "arm64-v8a" }

        externalNativeBuild {
            cmake {
                // Reproducible builds (as Marmalade STT): -ffile-prefix-map keeps the checkout
                // path out of __FILE__ strings, --build-id=none drops the path-sensitive note.
                val prefixMapRoot = rootProject.layout.projectDirectory.asFile.absolutePath
                cFlags += listOf("-ffile-prefix-map=$prefixMapRoot=.")
                cppFlags += listOf("-ffile-prefix-map=$prefixMapRoot=.")
                arguments += listOf(
                    "-DTHIRD_PARTY_DIR=${rootProject.file("third_party").absolutePath}",
                    "-DORT_DIR=${layout.buildDirectory.dir("onnxruntime").get().asFile.absolutePath}",
                    // Same C++ runtime model as the ORT AAR (no libc++_shared.so).
                    "-DANDROID_STL=c++_static",
                    // Optimised native code in debug builds too, or dictation is too slow to judge.
                    "-DCMAKE_BUILD_TYPE=Release",
                    // 16 KB page alignment (Play requirement for targetSdk 35+).
                    "-DCMAKE_SHARED_LINKER_FLAGS=-Wl,-z,max-page-size=16384 -Wl,--build-id=none",
                )
                targets += listOf("sherpa-onnx-jni")
            }
        }
    }

    externalNativeBuild {
        cmake {
            path = file("src/main/cpp/CMakeLists.txt")
            version = "3.22.1"
        }
    }
    // Pinned for reproducible builds; F-Droid's metadata says `ndk: r26d` to match.
    ndkVersion = "26.3.11579264"

    // F-Droid's scanner rejects the Google-encrypted dependency blob in the APK signing block.
    dependenciesInfo {
        includeInApk = false
        includeInBundle = true
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
    // Recorded per take in the history export (History.kt, `engine`).
    defaultConfig { buildConfigField("String", "SHERPA_VERSION", "\"$sherpaVersion\"") }

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
            // Reproducible builds: META-INF/version-control-info differs between a clone and a
            // worktree of the same commit.
            vcsInfo { include = false }
            // Unsigned without the RELEASE_* env vars (1.000; was the debug key). F-Droid's build
            // server strips `signingConfigs { }` and needs an unsigned APK to compare with ours,
            // so keep this on one line and never fall back to another key (docs/fdroid-main.md).
            if (System.getenv("RELEASE_KEYSTORE") != null) signingConfig = signingConfigs.getByName("release")
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
    packaging {
        jniLibs {
            useLegacyPackaging = true
            // libonnxruntime.so arrives twice: from the ORT AAR (the copy that ships) and as an
            // IMPORTED library of the sherpa-onnx CMake project. Same file, same Maven artifact.
            pickFirsts += "lib/*/libonnxruntime.so"
        }
    }
}

// Reproducible builds: AGP's compiled ART baseline profile is not deterministic (it varies with
// the build machine's core count), so the fdroid release APK leaves it out.
tasks.matching { it.name.contains("FdroidRelease") && it.name.contains("ArtProfile") }
    .configureEach { enabled = false }

dependencies {
    implementation("com.microsoft.onnxruntime:onnxruntime-android:$onnxRuntimeVersion")
}

// The ORT AAR's headers/ and jni/<abi>/libonnxruntime.so, unpacked to build/onnxruntime (the
// ORT_DIR CMake argument) before any CMake task, so the native build never downloads ORT.
val onnxRuntimeAar = configurations.create("onnxRuntimeAar") {
    isCanBeConsumed = false
    isTransitive = false
}
dependencies.add(onnxRuntimeAar.name, "com.microsoft.onnxruntime:onnxruntime-android:$onnxRuntimeVersion@aar")
val extractOnnxRuntime by tasks.registering(Sync::class) {
    from({ zipTree(onnxRuntimeAar.singleFile) }) { include("headers/**", "jni/*/libonnxruntime.so") }
    into(layout.buildDirectory.dir("onnxruntime"))
}
tasks.matching { it.name.startsWith("configureCMake") || it.name.startsWith("buildCMake") }
    .configureEach { dependsOn(extractOnnxRuntime) }
