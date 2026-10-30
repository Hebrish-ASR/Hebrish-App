# Native build: sherpa-onnx v1.13.8 from source, so the APK holds no prebuilt binary that
# F-Droid's inclusion policy rejects (docs/fdroid-main.md). Replaces the GitHub release AAR
# used up to Android 0.10.0. Recipe from Marmalade STT (app.marmalade.stt, in F-Droid since
# 2026-10-15), without its patches: Hebrish runs upstream sherpa-onnx unchanged.
#
# Produces libsherpa-onnx-jni.so (offline ASR only). Every dependency is compiled in
# statically except ONNX Runtime, linked against libonnxruntime.so from the Maven Central AAR
# com.microsoft.onnxruntime:onnxruntime-android; app/build.gradle.kts unpacks it to ORT_DIR.
#
# Fully offline: sherpa-onnx fetches its dependencies with FetchContent. Each is a git
# submodule under android/third_party/, pinned to the tag sherpa-onnx v1.13.8's cmake/*.cmake
# asks for. FETCHCONTENT_FULLY_DISCONNECTED makes a missed one fail configure, not download.
cmake_minimum_required(VERSION 3.22.1)
project(hebrish_native C CXX)

if(NOT DEFINED THIRD_PARTY_DIR OR NOT DEFINED ORT_DIR)
  message(FATAL_ERROR "THIRD_PARTY_DIR and ORT_DIR must be passed in by app/build.gradle.kts")
endif()
if(NOT EXISTS "${THIRD_PARTY_DIR}/sherpa-onnx/CMakeLists.txt")
  message(FATAL_ERROR "Submodules missing. Run: git submodule update --init")
endif()

# sherpa-onnx's cmake/onnxruntime.cmake reads these at configure time and then skips its
# ONNX Runtime download.
set(ENV{SHERPA_ONNXRUNTIME_INCLUDE_DIR} "${ORT_DIR}/headers")
set(ENV{SHERPA_ONNXRUNTIME_LIB_DIR} "${ORT_DIR}/jni/${ANDROID_ABI}")

set(FETCHCONTENT_FULLY_DISCONNECTED ON CACHE BOOL "" FORCE)
# FetchContent name (as passed to FetchContent_Declare, upper-cased) -> submodule.
foreach(pair
    KISSFFT=kissfft
    KALDI_NATIVE_FBANK=kaldi-native-fbank
    KALDI_DECODER=kaldi-decoder
    KALDIFST=kaldifst
    OPENFST=openfst
    EIGEN=eigen
    JSON=json)
  string(REPLACE "=" ";" kv "${pair}")
  list(GET kv 0 name)
  list(GET kv 1 dir)
  set(FETCHCONTENT_SOURCE_DIR_${name} "${THIRD_PARTY_DIR}/${dir}" CACHE PATH "" FORCE)
endforeach()

# On Android, sherpa-onnx's cmake/simple-sentencepiece.cmake rewrites three of its sources in
# place. Give it a copy in the build tree so the submodule stays clean.
set(_ssp_copy "${CMAKE_BINARY_DIR}/simple-sentencepiece-src")
file(REMOVE_RECURSE "${_ssp_copy}")
file(COPY "${THIRD_PARTY_DIR}/simple-sentencepiece/" DESTINATION "${_ssp_copy}" PATTERN ".git" EXCLUDE)
set(FETCHCONTENT_SOURCE_DIR_SIMPLE-SENTENCEPIECE "${_ssp_copy}" CACHE PATH "" FORCE)
# Reproducible builds: the copy's path holds an AGP hash of the absolute configure arguments,
# so map its __FILE__ strings back to the repo-relative path (wins over Gradle's shorter map).
add_compile_options("-ffile-prefix-map=${_ssp_copy}=third_party/simple-sentencepiece")

# Static sherpa-onnx and dependencies inside one JNI library. TTS off drops espeak-ng (GPL-3.0)
# and piper-phonemize; the rest are features and tools the app does not use.
set(BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)
foreach(opt TTS SPEAKER_DIARIZATION C_API BINARY WEBSOCKET PORTAUDIO PYTHON TESTS CHECK)
  set(SHERPA_ONNX_ENABLE_${opt} OFF CACHE BOOL "" FORCE)
endforeach()
set(SHERPA_ONNX_ENABLE_JNI ON CACHE BOOL "" FORCE)

add_subdirectory("${THIRD_PARTY_DIR}/sherpa-onnx" sherpa-onnx)

# -- Clean-up model (B-40a): llama.cpp for S1-ASR-Cleanup ------------------------------------
# libhebrish-llama-jni.so: llama.cpp b11982 (submodule third_party/llama.cpp, the build the
# desktop app's llama-server is pinned to) compiled in statically, with a small JNI bridge
# (s1_cleanup_jni.cpp). Its own library, loaded only when Clean up runs, so a phone that never
# downloads the model never maps it. Upstream's Android example is the reference, minus
# KleidiAI (fetched at configure time: not allowed offline) and OpenMP (ggml's own thread pool;
# no libomp to package). armv8.2-a with dot product and fp16: the Q4 matmul kernels need dotprod
# to be usable on a phone; CleanupModel.supported() checks the CPU for it before loading.
if(NOT EXISTS "${THIRD_PARTY_DIR}/llama.cpp/CMakeLists.txt")
  message(FATAL_ERROR "llama.cpp submodule missing. Run: git submodule update --init")
endif()
set(GGML_NATIVE OFF CACHE BOOL "" FORCE)
set(GGML_OPENMP OFF CACHE BOOL "" FORCE)
set(GGML_CPU_KLEIDIAI OFF CACHE BOOL "" FORCE)
set(GGML_LLAMAFILE ON CACHE BOOL "" FORCE)
set(GGML_CPU_ARM_ARCH "armv8.2-a+dotprod+fp16" CACHE STRING "" FORCE)
foreach(opt COMMON TESTS TOOLS EXAMPLES SERVER APP)
  set(LLAMA_BUILD_${opt} OFF CACHE BOOL "" FORCE)
endforeach()
set(LLAMA_OPENSSL OFF CACHE BOOL "" FORCE)
add_subdirectory("${THIRD_PARTY_DIR}/llama.cpp" llama.cpp EXCLUDE_FROM_ALL)

add_library(hebrish-llama-jni SHARED s1_cleanup_jni.cpp)
target_link_libraries(hebrish-llama-jni PRIVATE llama log)
