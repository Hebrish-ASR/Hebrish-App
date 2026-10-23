# sherpa-onnx Kotlin API (vendored)

Unmodified copies of `sherpa-onnx/kotlin-api/{FeatureConfig,HomophoneReplacerConfig,OfflineRecognizer,OfflineStream,QnnConfig}.kt`
from `android/third_party/sherpa-onnx` (v1.13.8, Apache-2.0, © Xiaomi Corporation and the k2-fsa
authors). They used to come inside the prebuilt AAR; since the native library is built from source
(`app/src/main/cpp/CMakeLists.txt`), the Kotlin side is these files.

The JNI code looks fields up by name, so these must match the submodule's version exactly. On a
sherpa-onnx bump, copy the same files again from the new submodule commit; never edit them here.
Add a file only when `android/core` starts using a class from it.

Only this app compiles them. Hebrish Keyboard still links the release AAR, which carries the same
classes, so they must not move into `android/core`.
