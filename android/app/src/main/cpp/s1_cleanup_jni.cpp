// JNI bridge for the clean-up model (B-40a): S1-ASR-Cleanup, a fine-tune of S1-mini by
// Superwhisper, run with llama.cpp b11982 in-process. The Android counterpart of the two
// llama-server endpoints desktop/hebrish/cleanup.py uses: /tokenize (count) and /completion
// (greedy, stop at end of turn, n_predict cap). Kotlin side: CleanupModel.kt.
//
// Text crosses as UTF-8 byte arrays, not jstring: JNI's "modified UTF-8" breaks on characters
// outside the BMP. One model and context per handle; calls on a handle must not overlap.
#include <jni.h>
#include <android/log.h>
#include <chrono>
#include <string>
#include <vector>
#include "llama.h"

#define TAG "HebrishCleanup"

namespace {

struct Handle {
    llama_model * model = nullptr;
    llama_context * ctx = nullptr;
    const llama_vocab * vocab = nullptr;
    std::chrono::steady_clock::time_point deadline;
};

void log_cb(ggml_log_level level, const char * text, void *) {
    if (level == GGML_LOG_LEVEL_WARN || level == GGML_LOG_LEVEL_ERROR)
        __android_log_write(level == GGML_LOG_LEVEL_ERROR ? ANDROID_LOG_ERROR : ANDROID_LOG_WARN, TAG, text);
}

bool past_deadline(void * data) {
    return std::chrono::steady_clock::now() > static_cast<Handle *>(data)->deadline;
}

std::string bytes(JNIEnv * env, jbyteArray a) {
    const jsize n = env->GetArrayLength(a);
    std::string s(static_cast<size_t>(n), '\0');
    env->GetByteArrayRegion(a, 0, n, reinterpret_cast<jbyte *>(s.data()));
    return s;
}

void throw_io(JNIEnv * env, const char * msg) {
    env->ThrowNew(env->FindClass("java/io/IOException"), msg);
}

// add_special false: Qwen3 adds no BOS, and the prompt carries its own template tokens.
std::vector<llama_token> tokenize(const llama_vocab * vocab, const std::string & text, bool special) {
    int n = -llama_tokenize(vocab, text.data(), (int32_t) text.size(), nullptr, 0, false, special);
    std::vector<llama_token> out(n > 0 ? n : 0);
    if (n > 0) llama_tokenize(vocab, text.data(), (int32_t) text.size(), out.data(), n, false, special);
    return out;
}

}  // namespace

extern "C" {

JNIEXPORT jlong JNICALL
Java_app_hebrish_dictation_CleanupModel_nativeLoad(JNIEnv * env, jclass, jstring path, jint n_ctx, jint threads) {
    llama_log_set(log_cb, nullptr);
    llama_backend_init();
    const char * p = env->GetStringUTFChars(path, nullptr);
    llama_model_params mp = llama_model_default_params();
    mp.n_gpu_layers = 0;
    llama_model * model = llama_model_load_from_file(p, mp);
    env->ReleaseStringUTFChars(path, p);
    if (!model) { throw_io(env, "the clean-up model did not load"); return 0; }

    auto * h = new Handle();
    llama_context_params cp = llama_context_default_params();
    cp.n_ctx = (uint32_t) n_ctx;
    cp.n_batch = (uint32_t) n_ctx;
    cp.n_threads = threads;
    cp.n_threads_batch = threads;
    cp.abort_callback = past_deadline;
    cp.abort_callback_data = h;
    llama_context * ctx = llama_init_from_model(model, cp);
    if (!ctx) {
        llama_model_free(model);
        delete h;
        throw_io(env, "not enough memory for the clean-up model");
        return 0;
    }
    h->model = model;
    h->ctx = ctx;
    h->vocab = llama_model_get_vocab(model);
    return reinterpret_cast<jlong>(h);
}

JNIEXPORT jint JNICALL
Java_app_hebrish_dictation_CleanupModel_nativeCount(JNIEnv * env, jclass, jlong handle, jbyteArray text) {
    auto * h = reinterpret_cast<Handle *>(handle);
    return (jint) tokenize(h->vocab, bytes(env, text), false).size();
}

/**
 * Greedy completion of [prompt] (special tokens parsed), at most [n_predict] tokens, stopping at
 * an end-of-generation token (<|im_end|> for Qwen3). Returns the reply as UTF-8; limit[0] is set
 * when it stopped at n_predict (llama-server's stop_type "limit"). Throws IOException on a
 * prompt too long for the context, a decode error, or the timeout.
 */
JNIEXPORT jbyteArray JNICALL
Java_app_hebrish_dictation_CleanupModel_nativeComplete(JNIEnv * env, jclass, jlong handle, jbyteArray prompt,
                                                      jint n_predict, jlong timeout_ms, jbooleanArray limit) {
    auto * h = reinterpret_cast<Handle *>(handle);
    h->deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(timeout_ms);
    llama_memory_clear(llama_get_memory(h->ctx), true);

    std::vector<llama_token> toks = tokenize(h->vocab, bytes(env, prompt), true);
    if (toks.empty() || toks.size() + (size_t) n_predict > llama_n_ctx(h->ctx)) {
        throw_io(env, "too long for the clean-up model");
        return nullptr;
    }
    if (llama_decode(h->ctx, llama_batch_get_one(toks.data(), (int32_t) toks.size())) != 0) {
        throw_io(env, past_deadline(h) ? "the clean-up model timed out" : "the clean-up model failed");
        return nullptr;
    }

    llama_sampler * smpl = llama_sampler_chain_init(llama_sampler_chain_default_params());
    llama_sampler_chain_add(smpl, llama_sampler_init_greedy());
    std::string out;
    bool hit_limit = true;
    char piece[256];
    for (int i = 0; i < n_predict; i++) {
        llama_token t = llama_sampler_sample(smpl, h->ctx, -1);
        if (llama_vocab_is_eog(h->vocab, t)) { hit_limit = false; break; }
        // special false: control tokens render as nothing, as llama-server's content does.
        int n = llama_token_to_piece(h->vocab, t, piece, sizeof(piece), 0, false);
        if (n > 0) out.append(piece, (size_t) n);
        if (i + 1 == n_predict) break;
        if (llama_decode(h->ctx, llama_batch_get_one(&t, 1)) != 0) {
            llama_sampler_free(smpl);
            throw_io(env, past_deadline(h) ? "the clean-up model timed out" : "the clean-up model failed");
            return nullptr;
        }
    }
    llama_sampler_free(smpl);

    jboolean lim = hit_limit ? JNI_TRUE : JNI_FALSE;
    env->SetBooleanArrayRegion(limit, 0, 1, &lim);
    jbyteArray r = env->NewByteArray((jsize) out.size());
    env->SetByteArrayRegion(r, 0, (jsize) out.size(), reinterpret_cast<const jbyte *>(out.data()));
    return r;
}

JNIEXPORT void JNICALL
Java_app_hebrish_dictation_CleanupModel_nativeFree(JNIEnv *, jclass, jlong handle) {
    auto * h = reinterpret_cast<Handle *>(handle);
    if (!h) return;
    llama_free(h->ctx);
    llama_model_free(h->model);
    delete h;
}

}  // extern "C"
