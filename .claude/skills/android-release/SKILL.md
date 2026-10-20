---
name: android-release
description: Take a round of Daniel's feedback on the Hebrish Android app through to a published APK — implement, compile, document, bump, tag, verify the CI build, copy to cdn.hebrish.app and rewrite latest.json, and note it on hebrish.app. Use when Daniel says "push out a new APK", "new point release", "release the app", "ship these app changes", or lists app feedback to "get into the latest version".
---

# Hebrish Android: feedback round → release

Written 2026-10-20 after Daniel had to repeat a feedback list that an earlier session had only
partly shipped (0.6.0 was committed but never tagged). The rule that follows from it: **a round
is not done until the tag is pushed, the APK is on the CDN and `latest.json` points at it.**

## 0. Before writing code

- Check what is already built but unreleased: `git tag | grep android | tail -1` vs `versionName`
  in `android/app/build.gradle.kts`, and `curl -s https://cdn.hebrish.app/downloads/latest.json`.
  If the version in gradle has no tag yet, fold the new work into it rather than bumping again.
- Read `android/docs/maintaining.md` (architecture, what is verified) and the private planning repo
  `Hebrish-ASR/Hebrish-App-Planning` (`backlog.md`, `google-play.md`; local clone
  `../Hebrish-App-Planning`). Add the round's items to `backlog.md` there.
- `shared/models.json` is fetched live by every installed app (Android and desktop). Changes
  to `default`, ids or schema affect old builds: see maintaining.md, "Catalogue: Jachnun
  recommended". After editing it: `cp shared/models.json desktop/hebrish/data/` and
  `cd desktop && uv run --with pytest python -m pytest -q tests/test_shared.py`.

## 1. Build check (no device is attached to the laptop)

```bash
cd android && JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 ./gradlew --offline -q assembleDebug
```
The shell's default `JAVA_HOME` points at a missing JDK 17. The app has no androidx and no
tests; screens are built in code (`Page.kt`). Say "compiled, not run on a device" in the
commit and docs unless Daniel has tested it.

## 2. Document in the same commit

- `android/docs/maintaining.md`: a dated section per feature (what, where in code, decisions with
  Daniel's words, (V)/(I) markers), and extend "Not yet verified".
- `android/README.md` and root `README.md` when user-visible behaviour or the model list changes.
- `.github/android-release-notes.md`: the GitHub release body (CI reads it). Plain, user-facing.

## 3. Version, tag, CI

- `versionCode` +1 and `versionName` in `android/app/build.gradle.kts` (skip if step 0 found an
  untagged version).
- Commit, push `main`, then `git tag android-vX.Y.Z && git push origin android-vX.Y.Z`.
- `.github/workflows/android.yml` builds the signed APK and creates the release
  `Hebrish-vX.Y.Z.apk`. Watch it: `gh run list -R Hebrish-ASR/Hebrish-App --workflow android -L 1`,
  `gh run watch <id> -R Hebrish-ASR/Hebrish-App`. Verify the asset exists:
  `gh release view android-vX.Y.Z -R Hebrish-ASR/Hebrish-App --json assets`.

## 4. CDN and latest.json

Follow the r2-upload skill (`../ASR-Training-Skills/skills/r2-upload/SKILL.md`):
download the release APK, upload to `downloads/android/Hebrish-vX.Y.Z.apk` with
`application/vnd.android.package-archive` and an attachment disposition, then rewrite
`downloads/latest.json` from the live copy: `files.android` = {url, name, platform, size, sha256,
version}, top-level `version`/`released`; leave the desktop entries alone. Verify with
`curl -sI https://cdn.hebrish.app/downloads/android/Hebrish-vX.Y.Z.apk` (size matches) and
`curl -sI https://hebrish.app/get/android` (302 to the new file; edge-cached up to 5 min).

## 5. Elsewhere

- F-Droid: `Hebrish-ASR/Hebrish-FDroid` polls GitHub releases hourly; nothing to do. Check
  `https://fdroid.hebrish.app/repo/index-v2.json` later if Daniel asks.
- hebrish.app (`danielrosehill/Hebrish-Website`, local `../Hebrish-App`): an entry in
  `changelog.html` (app releases section). Download links follow `latest.json`; never put a
  versioned URL on a page. If setup steps changed, keep `setup.html` and `SetupActivity` in step
  (same step ids).
- Planning repo: move the round's items in `backlog.md` to released.
