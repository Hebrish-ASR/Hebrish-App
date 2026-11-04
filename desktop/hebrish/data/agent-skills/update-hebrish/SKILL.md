---
name: update-hebrish
description: 'Check for and install updates to the Hebrish desktop app (hebrish.app) and its downloaded speech models through the app''s local API at http://127.0.0.1:8723, and switch model. Use when a user asks to update Hebrish, whether Hebrish or its models are up to date, which model is running, or to change model. Do NOT use for a first install (use install-hebrish-linux), for an app that will not start or a failing APT upgrade (use troubleshoot-hebrish-linux), or for the Android app.'
license: MIT
compatibility: The Hebrish desktop app (Ubuntu or Windows), 1.018 or later, running with Settings, Local API and its control option on; curl. Checks need internet.
---

# Update Hebrish

Hebrish is Daniel Rosehill's dictation app, a personal project (hebrish.app). The desktop app has a
**local API** on this computer. This skill uses it to check for and install updates to the app and
its models.

## Rules for the agent

- The API is `http://127.0.0.1:8723` unless the user changed the port in Settings, Local API.
- Do not send an `Origin` header: requests with one are refused (403).
- Say what will change before installing. Models can be hundreds of MB.
- Do not restart the app or switch model while `state` is not `idle`; the API refuses it too.

## 1. Check that control is on

```bash
curl -s http://127.0.0.1:8723/health
```

- `"control": true`: go on.
- `"control": false`: ask the user to open Hebrish, **Settings → Local API**, and tick *Let agents
  read history and control the app*.
- No `control` key: the app is 1.017 or older. Update it the old way (on Ubuntu,
  `sudo apt update && sudo apt install --only-upgrade hebrish`, after showing the user the command).
- Connection refused: Hebrish is not running, or the local API is off. Ask the user to start it and
  tick *Serve transcription to apps on this computer* in the same card.

## 2. The app

```bash
curl -s http://127.0.0.1:8723/v1/app/update
```

The reply has `current`, `latest`, `update_available`, `method`, `can_install` and `download_page`.

- `can_install` is true (`method` is `apt`): install it. The user must approve a system password
  prompt on their screen, so tell them first.

  ```bash
  curl -s -X POST http://127.0.0.1:8723/v1/app/update
  ```

  Poll `GET /v1/app/status` every few seconds: `app_update.running` goes false, then
  `app_update.installed_needs_restart` holds the version, or `app_update.error` says what failed
  (a declined prompt is an error too). The app may also ask the user about restarting. If they
  have not answered and the app is idle, restart it:

  ```bash
  curl -s -X POST http://127.0.0.1:8723/v1/app/restart
  ```

- `update_available` is true but `can_install` is false: this install (`windows`, `appimage`,
  `deb-manual`) cannot update itself. Give the user `download_page`. `source` is a checkout: say a
  new version exists.

## 3. The models

```bash
curl -s http://127.0.0.1:8723/v1/app/models/updates
```

`models` and `addons` list what is newer than what is installed; `errors` lists checks that failed.
Report the failures, do not call them up to date. To download everything listed:

```bash
curl -s -X POST http://127.0.0.1:8723/v1/app/models/updates
```

Poll `GET /v1/app/status` until `models.downloading` is null, `models.queued` is 0 and
`models.addons_downloading` is empty.

## 4. Which model, and switching

```bash
curl -s http://127.0.0.1:8723/v1/app/models
curl -s http://127.0.0.1:8723/v1/app/status
```

Each model has `id`, `name`, `installed`, `version`, `current` and `recommended`. To switch:

```bash
curl -s -X POST http://127.0.0.1:8723/v1/app/models/select \
  -H 'Content-Type: application/json' -d '{"id": "sabich"}'
```

A model that is not downloaded answers 409 with its size. Add `"download": true` after the user
agrees.

## Errors

Errors are `{"error": {"message": "..."}}`: 400 bad request, 403 control is off, 404 unknown id or
route, 409 the app cannot do it now or on this install. `GET /v1` lists every route.
