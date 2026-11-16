---
date: 2026-11-16
platform: android
environment: Google Pixel (model and Android version not reported)
component: android/core/src/main/java/app/hebrish/core/ModelStore.kt (downloadFiles), ModelDownload.kt
affected: "<= 1.035"
fixed_in: "unreleased"
status: fixed
---

# Model downloads keep timing out and are hard to get to finish

## Symptom

A user on a Pixel, 2026-11-16: "Hard to get the downloads to finish, they keep timing out." Downloads of the
speech models (hundreds of MB) failed part way with a timeout message; tapping Download again resumed, then failed again.

## Cause

(V, from the code) A single attempt per download: `ModelStore.downloadFiles` opened one `HttpURLConnection` per
file (connect 20 s, read 30 s) and let any `IOException` propagate; `ModelDownload.run` turned it into
`Status.Failed` ("Download failed: … Tap Download to resume") and cleared the queue. A 30 s stall (weak signal,
Wi-Fi roaming, a slow CDN edge) was enough to end the download.

(I) Made worse with the screen off or the app left: the download ran on a plain thread with no foreground service,
wake lock or Wi-Fi lock, so Doze, app standby and Wi-Fi power save could pause the process or the socket long enough
for the read timeout to fire.

(I) Separately found: the manifest lacked `ACCESS_NETWORK_STATE`, so `ModelUpdates.metered` (B-107) always read
"metered" and background model updates never ran with Only on Wi-Fi on (the default).

## How it was found

Reading `ModelStore.downloadFiles` and `ModelDownload.run` after the report: no retry anywhere, and every
`IOException`, including `SocketTimeoutException`, ends in `Status.Failed`. The merged manifest (built 1.035) had no
`ACCESS_NETWORK_STATE`, which `ConnectivityManager.isActiveNetworkMetered` needs. Not reproduced on a device: no
phone was connected.

## Ruled out

- Not a checksum or a resume bug: the `.part` resumed correctly on the next tap (the user could finish by retrying),
  and the `Range` resume is exercised in `DownloadRetryTest`.
- Raising the read timeout alone: it only moves the threshold; a dropped connection still failed outright.

## Fix

Unreleased, 2026-11-16. Details and the lasting rules: `android/docs/maintaining.md`, "Download robustness".

- `core/.../DownloadRetry.kt` + `ModelStore.fetchWithRetry`: transient errors (connection `IOException`s, a body
  that ends early, HTTP 408/429/5xx) back off 2, 4, 8, 15, 30 s and resume the same file from its `.part`; with no
  network it waits for one; it gives up only after 10 min with no new byte (30 min offline). Read timeout 60 s,
  `useCaches = false`.
- `ModelDownload.Status.Running.waiting`: the Models card says "Connection lost: retrying in 8 s…" or
  "Waiting for a connection…".
- `DownloadService` (app module, via the null-by-default `ModelDownload.keepAlive` hook): a `dataSync` foreground
  service with a progress notification (Cancel, tap opens Models), a partial wake lock and a Wi-Fi lock while a
  user-started download runs. Background updates (B-107) don't start it; they retry inside the job.
- `ACCESS_NETWORK_STATE`, `WAKE_LOCK`, `FOREGROUND_SERVICE_DATA_SYNC` added to the manifest.

## Verified / not verified

- (V) Both flavors compile; `DownloadRetryTest` (17 tests) passes, including a local server that drops the
  connection twice mid-file and the download completing with the right SHA-256.
- (I) Not run on a device: the service and notification, the locks with the screen off, Doze, Android 15's
  dataSync `onTimeout`, and whether the user's timeouts are gone. Ask the reporter to try the next build.

## Related

- The desktop app (`desktop/hebrish/model_store.py`, `download`) has the same single-attempt weakness (one
  `urlopen` per file, no retry; resumes from `.part` on the next click). Unchanged.
