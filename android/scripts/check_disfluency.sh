#!/usr/bin/env bash
# Runs shared/disfluency-cases.json against core/.../Disfluency.kt on the JVM (same harness as check_dictionary.sh).
# The app has no test setup, so this compiles the one file with the Kotlin compiler Gradle
# already downloaded (offline) and android.jar for the android.* imports. The matching code
# uses only java.util.regex, so the JVM result stands for the phone's (ICU regex; (I) not run on a device).
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
sdk=$(grep sdk.dir "$here/local.properties" | cut -d= -f2); aj=$(ls -d "$sdk"/platforms/android-* | sort -V | tail -1)/android.jar
python3 - "$repo/shared/disfluency-cases.json" > "$work/Harness.kt" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
q = lambda s: json.dumps(s).replace("$", "\\$")
print("import app.hebrish.core.Disfluency\nfun main() {\n var bad = 0\n val cases = listOf(")
print(",\n".join(f"  Triple({q(c['in'])}, {q(c.get('before', ''))}, {q(c['out'])})" for c in d["cases"]))
print(' )\n for ((i, b, o) in cases) { val r = Disfluency.chop(i, b); if (r != o) { bad++; println("FAIL [$i] -> [$r] want [$o]") } }\n println("${cases.size - bad}/${cases.size} pass")\n if (bad > 0) kotlin.system.exitProcess(1)\n}')
PY
java=${JAVA_HOME:-/usr/lib/jvm/java-21-openjdk-amd64}/bin/java
"$java" -cp "$cp" org.jetbrains.kotlin.cli.jvm.K2JVMCompiler -nowarn -no-stdlib -cp "$aj:$std" -d "$work/out" \
  "$here/core/src/main/java/app/hebrish/core/Disfluency.kt" "$work/Harness.kt"
"$java" -cp "$work/out:$std:$aj" HarnessKt
