#!/usr/bin/env bash
# Checks app/.../Paragraphs.kt and ParagraphModel.kt (B-44a; spec shared/paragraphs.md) on the JVM.
# Same harness idea as check_disfluency.sh: the app has no test setup, so this compiles the files
# with the Kotlin compiler Gradle already downloaded. Neither file imports android.*;
# ParagraphModel.kt uses the ORT Java API (ai.onnxruntime), the same in the desktop jar
# (com.microsoft.onnxruntime:onnxruntime, Maven Central, the app's ORT version) and the Android AAR.
#
# Fails on (exact unless said; shared/paragraphs.md, "Parity test"):
#   windows      from shared/paragraph-cases.json's own word_pieces            always
#   word_pieces  the cases, plus 3000 fuzz words against HF `tokenizers`       needs the CDN (and uv for the fuzz)
#   fp32         probs within 0.001 of probs_fp32; output_fp32 equal unless a
#                score is within 0.001 of the threshold                         needs the CDN and the Hub (model.onnx, 133 MB)
#   int8         output differs from the input only in whitespace; break
#                decisions differ from probs_fp32 on <= max(2, 2%) words/case   needs the CDN
#   same ORT     int8 probs vs the Hub's paragraphs.py on the app's ORT
#                version (|dp| <= 1e-4) and its output (exact)                  needs the CDN, the Hub and uv
# Reports, without failing, the drift from the cases' probs_int8: int8 scores depend on the CPU and
# the ORT version (android/docs/maintaining.md, "Transcription Mode: Paragraphs setting").
#
# Downloads are cached in $HEBRISH_CHECK_CACHE (default ~/.cache/hebrish-checks) and checked
# (SHA-256 from the CDN manifest, SHA-1 from Maven). Offline with an empty cache, the checks that
# need them are skipped, not failed.
set -euo pipefail
here=$(cd "$(dirname "$0")/.." && pwd); repo=$(cd "$here/.." && pwd)
work=$(mktemp -d); trap 'rm -rf "$work"' EXIT
C=~/.gradle/caches/modules-2/files-2.1
kv=$(ls "$C/org.jetbrains.kotlin/kotlin-compiler-embeddable" | sort -V | tail -1)
jar() { find "$C/$1" -name "$2" | head -1; }
cp=""; for a in kotlin-compiler-embeddable kotlin-stdlib kotlin-script-runtime kotlin-reflect kotlin-daemon-embeddable; do
  cp+="$(jar org.jetbrains.kotlin/$a "$a-$kv.jar"):"; done
cp+="$(jar org.jetbrains.intellij.deps 'trove4j*.jar'):$(jar org.jetbrains.kotlinx 'kotlinx-coroutines-core-jvm-*.jar'):$(jar org.jetbrains/annotations 'annotations-13.0.jar')"
std=$(jar org.jetbrains.kotlin/kotlin-stdlib "kotlin-stdlib-$kv.jar")
java=${JAVA_HOME:-/usr/lib/jvm/java-21-openjdk-amd64}/bin/java

ortv=$(sed -n 's/^val onnxRuntimeVersion = "\(.*\)"$/\1/p' "$here/app/build.gradle.kts")
cache=${HEBRISH_CHECK_CACHE:-$HOME/.cache/hebrish-checks}
mkdir -p "$cache"
manifest_url=https://cdn.hebrish.app/models/paragraph-breaks/latest.json

# ONNX Runtime desktop jar (linux-x64 natives inside), the app's version.
ort="$cache/onnxruntime-$ortv.jar"
if [ ! -s "$ort" ]; then
  u=https://repo1.maven.org/maven2/com/microsoft/onnxruntime/onnxruntime/$ortv/onnxruntime-$ortv.jar
  if curl -sfL -o "$work/ort.jar" "$u" && sha1=$(curl -sfL "$u.sha1") \
     && [ "$(sha1sum "$work/ort.jar" | cut -d' ' -f1)" = "${sha1%% *}" ]; then mv "$work/ort.jar" "$ort"
  else echo "ONNX Runtime $ortv jar not available (offline?): model checks skipped"; fi
fi

# Model files of the version the cases were made with, checked against the CDN manifest.
ver=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["version"])' "$repo/shared/paragraph-cases.json")
mdir="$cache/paragraph-breaks/$ver"
if [ ! -s "$mdir/ok" ] || [ ! -s "$mdir/latest.json" ]; then
  if curl -sfL -o "$work/latest.json" "$manifest_url"; then
    python3 - "$work/latest.json" "$ver" > "$work/files.txt" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
if m["version"] != sys.argv[2]:
    sys.exit(f"CDN has {m['version']}, the cases are for {sys.argv[2]}: regenerate them (scripts/paragraph_cases.py)")
for n, f in m["files"].items():
    print(n, f["sha256"], m["base_url"].rstrip("/") + "/" + n)
PY
    mkdir -p "$mdir"
    while read -r n sha u; do
      [ -s "$mdir/$n" ] && [ "$(sha256sum "$mdir/$n" | cut -d' ' -f1)" = "$sha" ] && continue
      curl -sfL -o "$mdir/$n.part" "$u"
      [ "$(sha256sum "$mdir/$n.part" | cut -d' ' -f1)" = "$sha" ] || { echo "SHA-256 mismatch: $n"; exit 1; }
      mv "$mdir/$n.part" "$mdir/$n"
    done < "$work/files.txt"
    cp "$work/latest.json" "$mdir/latest.json"
    echo ok > "$mdir/ok"
  else echo "CDN not reachable (offline?): tokenizer and model checks skipped"; fi
fi
[ -s "$mdir/ok" ] && [ -s "$mdir/latest.json" ] || mdir=""

# The reference (paragraphs.py, tokenizer.json) from the Hub at the commit the CDN files came from.
hub=""
if [ -n "$mdir" ] && command -v uv >/dev/null; then
  rev=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["revision"])' "$mdir/latest.json")
  hub="$cache/paragraph-breaks/hub-$rev"
  mkdir -p "$hub"
  for f in paragraphs.py onnx/tokenizer.json; do
    [ -s "$hub/$(basename $f)" ] || curl -sfL -o "$hub/$(basename $f)" \
      "https://huggingface.co/danielrosehill/MiniLM-L12-ASR-Paragraph-Breaks/resolve/$rev/$f" || { hub=""; break; }
  done
fi
[ -n "$hub" ] || echo "uv, the Hub or the model files not available: fuzz and same-ORT checks skipped"

# The fp32 model (the strict parity target; not on the CDN), at the same Hub commit, SHA-256 from the Hub's tree API.
fp32=""
if [ -n "$mdir" ]; then
  rev=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["revision"])' "$mdir/latest.json")
  if [ -s "$mdir/model.onnx" ]; then fp32=yes
  elif sha=$(curl -sfL "https://huggingface.co/api/models/danielrosehill/MiniLM-L12-ASR-Paragraph-Breaks/tree/$rev/onnx" \
        | python3 -c 'import json,sys; print([f["lfs"]["oid"] for f in json.load(sys.stdin) if f["path"] == "onnx/model.onnx"][0])') \
     && curl -sfL -o "$mdir/model.onnx.part" "https://huggingface.co/danielrosehill/MiniLM-L12-ASR-Paragraph-Breaks/resolve/$rev/onnx/model.onnx" \
     && [ "$(sha256sum "$mdir/model.onnx.part" | cut -d' ' -f1)" = "$sha" ]; then
    mv "$mdir/model.onnx.part" "$mdir/model.onnx"; fp32=yes
  else rm -f "$mdir/model.onnx.part"; echo "fp32 model not available from the Hub: fp32 checks skipped"; fi
fi

# Cases as plain lines (strings as UTF-8 hex), read by the harness: no JSON library needed.
python3 - "$repo/shared/paragraph-cases.json" > "$work/cases.txt" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
print("threshold", d["threshold"])
for c in d["cases"]:
    print("case", c["name"])
    print("input", c["input"].encode().hex() or "-")
    print("pieces", ";".join(",".join(map(str, p)) for p in c["word_pieces"]) or "-")
    print("windows", ";".join(f"{a},{b}" for a, b in c["windows"]) or "-")
    print("probs", ",".join(map(str, c["probs_int8"])) or "-")
    print("output", c["output"].encode().hex() or "-")
    print("probs32", ",".join(map(str, c["probs_fp32"])) or "-")
    print("output32", c["output_fp32"].encode().hex() or "-")
PY

# Reference results on the app's ORT version: probs and output per case, and fuzz words' ids.
touch "$work/ref.txt"
if [ -n "$hub" ]; then
  cat > "$work/ref.py" <<'PY'
import importlib.util, json, random, sys
import onnxruntime as ort
from tokenizers import Tokenizer
cases, mdir, hub = sys.argv[1:4]
spec = importlib.util.spec_from_file_location("paragraphs", hub + "/paragraphs.py")
P = importlib.util.module_from_spec(spec); spec.loader.exec_module(P)
tok = Tokenizer.from_file(hub + "/tokenizer.json")
so = ort.SessionOptions(); so.intra_op_num_threads = 1
sess = ort.InferenceSession(mdir + "/model_int8.onnx", so, providers=["CPUExecutionProvider"])
d = json.load(open(cases))
print("ortversion", ort.__version__)
for c in d["cases"]:
    words = c["input"].split()
    pr = P.word_probs(tok, sess, words) if words else []
    print("refprobs", c["name"], ",".join(repr(float(x)) for x in pr) or "-")
    print("refout", c["name"], P.paragraphs(c["input"], tok, sess, d["threshold"]).encode().hex() or "-")
# Fuzz: words drawn from scripts, marks, controls, symbols and special-token text.
pool = (list("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") * 4
    + list("!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~") + list("éèêëàâäôöûüçñøåæœßÉÀÇÑØİıſ")
    + list("αβγδΣσςΩάέ") + list("абвгдЖЁё") + list("שלוםעבריתְִּ") + list("日本語中文漢字한국어ひらがなカタカナ")
    + list("̧́̈⃝") + list("­​‍⁠﻿\u0001\u0007\u007f\U000f0000͸�\x00")
    + list("₪€£¥©®™°±×÷§¶…–—‘’“”«»„•·") + ["🙂", "👍🏽", "🇮🇱", "ﬁ", "Ⅻ", "½", "²", "ｆｕｌｌ", "[SEP]", "[CLS]", "[UNK]", "[MASK]", "[PAD]", "[sep]"])
rnd = random.Random(44)
words = set()
while len(words) < 3000:
    w = "".join(rnd.choice(pool) for _ in range(rnd.choice([1, 2, 3, 5, 8, 13, 40, 99, 101, 120])))
    if w.split() == [w]:
        words.add(w)
unk = tok.token_to_id("[UNK]")
words = sorted(words)
for w, e in zip(words, tok.encode_batch(words, add_special_tokens=False)):
    print("fuzz", w.encode().hex(), ",".join(map(str, e.ids or [unk])))
PY
  uv run -q --no-project --with "onnxruntime==$ortv" --with "tokenizers>=0.15" --with numpy \
    python -I "$work/ref.py" "$repo/shared/paragraph-cases.json" "$mdir" "$hub" > "$work/ref.txt"
fi

cat > "$work/Harness.kt" <<'KT'
import app.hebrish.dictation.*
import java.io.File

interface Model { fun probs(words: List<String>): DoubleArray; fun apply(text: String): String; fun close() }
const val PER_CASE = 8   // the "case" line and its 7 fields

fun hex(s: String) = if (s == "-") "" else String(s.chunked(2).map { it.toInt(16).toByte() }.toByteArray(), Charsets.UTF_8)
fun ints(s: String, sep: String) = if (s == "-") emptyList() else s.split(sep).map { p -> p.split(",").map { it.toInt() }.toIntArray() }
fun doubles(s: String) = if (s == "-") DoubleArray(0) else s.split(",").map { it.toDouble() }.toDoubleArray()
fun maxDiff(a: DoubleArray, b: DoubleArray) = if (a.size != b.size) Double.MAX_VALUE else a.indices.maxOfOrNull { Math.abs(a[it] - b[it]) } ?: 0.0

fun main(args: Array<String>) {
    val lines = File(args[0]).readLines().map { it.substringBefore(' ') to it.substringAfter(' ') }
    val ref = File(args[1]).readLines().map { it.split(' ') }
    val thr = lines.first { it.first == "threshold" }.second.toDouble()
    val dir = args.getOrNull(2)?.takeIf { it.isNotEmpty() }?.let(::File)
    val tok = dir?.let { WordPiece.load(File(it, "vocab.txt")) }
    val model = dir?.let { makeModel(it, thr, "model_int8.onnx") }
    val model32 = dir?.takeIf { args.getOrNull(3) == "fp32" }?.let { makeModel(it, thr, "model.onnx") }
    val refProbs = ref.filter { it[0] == "refprobs" }.associate { it[1] to doubles(it[2]) }
    val refOut = ref.filter { it[0] == "refout" }.associate { it[1] to hex(it[2]) }
    var bad = 0; var checks = 0
    fun check(ok: Boolean, m: () -> String) { checks++; if (!ok) { bad++; println("FAIL " + m()) } }
    var drift = 0.0; var over = 0; var flips = 0; var sameOrt = 0.0; var outDiff = 0
    var fp32Max = 0.0; var fp32Out = 0; var int8Flips = 0; var nWords = 0
    var i = 0
    while (i < lines.size) {
        if (lines[i].first != "case") { i++; continue }
        val name = lines[i].second
        val f = lines.subList(i + 1, i + PER_CASE).associate { it }
        i += PER_CASE
        val input = hex(f.getValue("input"))
        val pieces = ints(f.getValue("pieces"), ";")
        val windows = ints(f.getValue("windows"), ";")
        val probs = doubles(f.getValue("probs"))
        val output = hex(f.getValue("output"))
        val probs32 = doubles(f.getValue("probs32"))
        val output32 = hex(f.getValue("output32"))
        val words = Paragraphs.words(input)
        check(words.size == pieces.size) { "$name: ${words.size} words, want ${pieces.size}" }
        val w = Paragraphs.windows(pieces).map { it.toList() }
        check(w == windows.map { it.toList() }) { "$name windows: $w want ${windows.map { it.toList() }}" }
        if (tok != null) {
            val got = words.map { tok.word(it).toList() }
            check(got == pieces.map { it.toList() }) {
                val k = got.indices.first { it >= pieces.size || got[it] != pieces[it].toList() }
                "$name word_pieces: word $k [${words.getOrNull(k)}] -> ${got[k]} want ${pieces.getOrNull(k)?.toList()}"
            }
        }
        if (model32 != null) {
            val p = model32.probs(words)
            val d = maxDiff(p, probs32)
            fp32Max = maxOf(fp32Max, d)
            check(d <= 1e-3) { "$name fp32 probs: max |dp| $d" }
            if (probs32.none { Math.abs(it - thr) <= 1e-3 }) {
                fp32Out++
                check(model32.apply(input) == output32) { "$name fp32 output differs from output_fp32" }
            }
            println("  %-20s fp32: max |dp| %.1e".format(name, d))
        }
        if (model == null) continue
        val t = System.nanoTime()
        val p = model.probs(words)
        val ms = (System.nanoTime() - t) / 1e6
        val out = model.apply(input)
        check(Paragraphs.sameWords(out, input) && out.replace("\n\n", " ") == words.joinToString(" ")) { "$name int8 output changed more than whitespace" }
        if (probs32.size == p.size) {
            val k = p.indices.count { (p[it] >= thr) != (probs32[it] >= thr) }
            int8Flips += k; nWords += p.size
            check(k <= maxOf(2, (p.size * 0.02).toInt())) { "$name int8 break decisions differ from fp32 on $k words" }
        }
        // Against the cases (ORT 1.31): reported only.
        val d = maxDiff(p, probs)
        drift = maxOf(drift, d)
        over += p.indices.count { Math.abs(p[it] - probs[it]) > 0.02 }
        flips += p.indices.count { (p[it] >= thr) != (probs[it] >= thr) }
        val near = probs.any { Math.abs(it - thr) <= 0.02 }
        if (!near && out != output) outDiff++
        val outNote = if (near) "output not compared" else if (out == output) "output same" else "output differs"
        // Against the reference on the same ORT version: must match.
        val rp = refProbs[name]
        val sd = rp?.let { maxDiff(p, it) }
        if (rp != null) {
            sameOrt = maxOf(sameOrt, sd!!)
            check(sd <= 1e-4) { "$name probs vs reference on the same ORT: max |dp| $sd" }
            check(out == refOut[name]) { "$name output vs reference on the same ORT differs" }
        }
        println("  %-20s %3d words %d window(s) %5.0f ms | vs cases: max |dp| %.4f, %s | vs same-ORT reference: %s".format(
            name, words.size, windows.size, ms, d, outNote, sd?.let { "max |dp| %.1e".format(it) } ?: "skipped"))
    }
    val fuzz = ref.filter { it[0] == "fuzz" }
    if (tok != null) for (fz in fuzz) {
        val word = hex(fz[1]); val want = fz[2].split(",").map { it.toInt() }
        val got = tok.word(word).toList()
        check(got == want) { "fuzz [$word] (${word.codePoints().toArray().joinToString(" ") { "U+%04X".format(it) }}) -> $got want $want" }
    }
    model?.close()
    model32?.close()
    val ortVersion = ref.firstOrNull { it[0] == "ortversion" }?.getOrNull(1)
    println("${checks - bad}/$checks checks pass. Tokenizer: ${if (tok != null) "cases + ${fuzz.size} fuzz words" else "skipped"}. " +
        (if (model32 == null) "fp32: skipped. " else "fp32: max |dp| %.1e, %d outputs compared. ".format(fp32Max, fp32Out)) +
        (if (model == null) "" else "int8 vs fp32 break decisions: %d of %d words differ. ".format(int8Flips, nWords)) + "int8: " +
        (if (model == null) "skipped" else (if (ortVersion != null) "vs same-ORT reference ($ortVersion) max |dp| %.1e; ".format(sameOrt) else "same-ORT reference skipped; ") +
            "vs the cases' probs_int8 (reported, not failed): max |dp| %.4f, %d word scores off by > 0.02, %d break decisions differ, %d compared outputs differ".format(drift, over, flips, outDiff)))
    if (bad > 0) kotlin.system.exitProcess(1)
}
KT

src=("$here/app/src/main/java/app/hebrish/dictation/Paragraphs.kt" "$work/Harness.kt")
ortcp=""
if [ -s "$ort" ] && [ -n "$mdir" ]; then
  ortcp=":$ort"
  src+=("$here/app/src/main/java/app/hebrish/dictation/ParagraphModel.kt")
  cat > "$work/Make.kt" <<'KT'
import app.hebrish.dictation.ParagraphModel
fun makeModel(dir: java.io.File, thr: Double, file: String): Model? {
    val m = ParagraphModel(dir, thr, threads = 1, modelFile = file)
    return object : Model {
        override fun probs(words: List<String>) = m.probs(words)
        override fun apply(text: String) = m.apply(text)
        override fun close() = m.close()
    }
}
KT
else
  echo 'fun makeModel(dir: java.io.File, thr: Double, file: String): Model? = null' > "$work/Make.kt"
fi
src+=("$work/Make.kt")

"$java" -cp "$cp" org.jetbrains.kotlin.cli.jvm.K2JVMCompiler -nowarn -no-stdlib -cp "$std$ortcp" -d "$work/out" "${src[@]}"
"$java" -cp "$work/out:$std$ortcp" HarnessKt "$work/cases.txt" "$work/ref.txt" "$mdir" "${fp32:+fp32}"
