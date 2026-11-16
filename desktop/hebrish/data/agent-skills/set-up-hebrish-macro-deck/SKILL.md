---
name: set-up-hebrish-macro-deck
description: 'Sets up a Macro Deck 3 deck (a phone, tablet or browser as a button pad) that controls the Hebrish desktop app (hebrish.app) through its local API at http://127.0.0.1:8723: hold to talk, tap to start and stop, stop, and switching between the Sabich, Shakshuka and Falafel models. Turns on the local API, then installs the ready-made template by import or builds it through the Macro Deck MCP server. Use when a user asks for Macro Deck, a stream deck, macropad or phone remote for Hebrish dictation, or a push-to-talk button on their phone. Do NOT use for installing Hebrish itself (install-hebrish-linux), for installing Macro Deck itself (its own docs, macro-deck.app), or for the Hebrish Android keyboard.'
license: MIT
compatibility: Hebrish desktop 1.018 or later (Ubuntu or Windows) and Macro Deck 3.0 or later on the same computer. A phone or tablet on the same network as the deck, or any browser. curl. The MCP route also needs the agent connected to Macro Deck's built-in MCP server.
---

# Set up a Macro Deck for Hebrish

Hebrish is Daniel Rosehill's dictation app, a personal project (hebrish.app). Its desktop app has
a **local API** on `http://127.0.0.1:8723` that other programs on the same computer can use to
start and stop dictation and switch model. [Macro Deck](https://macro-deck.app) 3 is a free,
open-source stream-deck app: it runs on the computer and shows its buttons on a phone, tablet or
browser. Each button in this deck sends one HTTP request from the Macro Deck host to Hebrish, so
nothing needs window focus and it works on Wayland. Text is typed into whatever window has focus
on the computer, as with the Hebrish hotkey.

The deck (2 columns, 4 rows, thumb-friendly on a phone held upright):

| Button | Trigger | Request |
| --- | --- | --- |
| Sabich | tap | `POST /v1/app/models/select` `{"id": "sabich-rolling", "download": false}` |
| Shakshuka | tap | `POST /v1/app/models/select` `{"id": "shakshuka", "download": false}` |
| Falafel | tap | `POST /v1/app/models/select` `{"id": "falafel", "download": false}` |
| Stop | tap | `POST /v1/app/dictation` `{"action": "stop"}` |
| Tap: start / stop (2 wide) | tap | `POST /v1/app/dictation` `{"action": "toggle"}` |
| Hold to talk (2 wide, bottom) | touch start, touch end | `{"action": "start"}`, then `{"action": "stop"}` |

The template, as a portable spec, is
<https://raw.githubusercontent.com/Hebrish-ASR/Hebrish-Agent-Skills/main/skills/set-up-hebrish-macro-deck/assets/hebrish-dictation.deck.json>.

## Rules for the agent

- Everything here runs on the user's own computer. Do not open Macro Deck's or Hebrish's ports to
  the internet.
- Do not test the dictation buttons yourself: a `start` records from the user's microphone and types
  into their focused window. Switching to a model that is already selected is the harmless test.
- Model switches use `"download": false`. A model that is not downloaded answers with an error;
  tell the user to download it on Hebrish's Models tab (about 660 MB) rather than downloading it
  from the deck.
- Show the user each command that needs `sudo` and ask before running it.

## 1. Check Hebrish and turn on its local API

```bash
curl -s http://127.0.0.1:8723/v1/app/status
```

- A JSON reply with `"state"` (`idle`, `recording` or `busy`): ready. Go to step 2.
- `403` with `control`: the local API is on but control is off.
- Connection refused: the local API is off, or Hebrish is not running.

For either of the last two, ask the user to open Hebrish, **Settings → Local API**, and tick both
*Serve transcription to apps on this computer* and *Let agents read history and control the app*.
If they would rather you do it: close Hebrish, set `"local_api": true` and
`"local_api_control": true` in its config file (`~/.config/hebrish/config.json` on Linux,
`%APPDATA%\Hebrish\config.json` on Windows), start Hebrish again and re-run the check. If Settings
has no Local API card, Hebrish is older than 1.018: update it first (skill `update-hebrish`, or on
Ubuntu `sudo apt update && sudo apt install hebrish`).

The second switch also lets local programs read the transcript history; say so when you ask.

Then list the models, so you can tell the user which buttons will work now:

```bash
curl -s http://127.0.0.1:8723/v1/app/models
```

`installed: true` models switch at once; the others need downloading in Hebrish first.

## 2. Check Macro Deck

Macro Deck 3 must be installed and running on the same computer (Linux: its APT repository at
`packages.macro-deck.app`; Windows and others: <https://macro-deck.app>). Its host listens on
port 8193 by default:

```bash
ss -ltn | grep -E ':8193'          # Linux
```

The user opens the deck on their phone or tablet by scanning the pairing code Macro Deck shows, or
in a browser. Macro Deck 2 and its old Android app do not work with this deck: it needs version 3.

## 3. Install the deck

Pick the first route that applies.

### A. Import the template (any user, no agent tools needed)

1. Download
   <https://hebrish.app/downloads/macro-deck/hebrish-dictation.macroDeckProfile>.
2. In Macro Deck, open the profile menu and choose **Import profile**, then the file. It arrives as the profile
   *Hebrish Dictation*, with its icons.
3. On the phone, switch the deck to that profile.

If the download is not there yet, use route B or C.

### B. Build it through the Macro Deck MCP server

If you have Macro Deck's MCP tools (`catalog`, `list`, `apply_changes`, ...): the user creates a
token in **Settings → AI clients → Create token** and connects you; see Macro Deck's docs. Then:

1. Fetch the template JSON above.
2. Icons: read `${XDG_DATA_HOME:-$HOME/.local/share}/MacroDeck/data/icons/packs/*/pack.json`
   (Windows: Macro Deck's data folder) and find the pack named `MDI-Icons`; each button's `icon`
   is an `icons[].name` there, and its `icons[].id` is the reference. Without the pack, ask the
   user to install *MDI-Icons* from Macro Deck's **Store**, or build without icons.
3. `list {entity: "profiles"}`. If there is no *Hebrish Dictation* profile, create it with
   `apply_changes` (`{op: "create", entity: "profile", data: {name: "Hebrish Dictation"}}`). Then
   `list {entity: "folders", profileId}` and use its default folder (create `Home` if it has none).
   Note that `list` and `get` take plural entity names, `apply_changes` singular ones.
4. One `apply_changes` batch, `dryRun: true` first, then for real:
   `update folder {id, data: {name: "Home", rows: 4, columns: 2}}`, then one
   `create widget` per button:

```json
{"op": "create", "entity": "widget", "data": {
  "folderId": "<folder id>", "type": "ActionButton",
  "positionX": 0, "positionY": 3, "width": 2, "height": 1,
  "data": {
    "label": "Hold to talk", "backgroundColor": "#0f6b5c",
    "labelColor": "#ffffff", "labelPosition": "bottom",
    "icon": {"type": "icon-pack", "reference": "<icon id>"}, "iconColor": "#ffffff",
    "iconDisplay": {"fit": "contain", "zoom": 55, "offsetX": 0, "offsetY": -12, "opacity": 100},
    "flows": [
      {"triggerId": "<new uuid>", "triggerType": "onTouchStart", "triggerLabel": "Touch start",
       "children": [{"id": "<new uuid>", "type": "action",
         "blockType": "app.macro-deck.http.send-request", "label": "Send HTTP Request",
         "color": "#4f7cff", "integrationId": "app.macro-deck.http", "actionId": "send-request",
         "parameters": [
           {"name": "method", "type": "choice", "label": "Method", "value": "POST"},
           {"name": "url", "type": "url", "label": "URL", "value": "http://127.0.0.1:8723/v1/app/dictation"},
           {"name": "bodyType", "type": "choice", "label": "Body type", "value": "json"},
           {"name": "jsonBody", "type": "json", "label": "JSON body", "value": "{\"action\": \"start\"}"},
           {"name": "expectedStatus", "type": "string", "label": "Expected status", "value": "2xx"},
           {"name": "timeout", "type": "duration", "label": "Timeout", "value": 5000}]}]},
      {"triggerId": "<new uuid>", "triggerType": "onTouchEnd", "triggerLabel": "Touch end",
       "children": ["... the same block with {\"action\": \"stop\"} ..."]}
    ]}}}
```

   `positionX` is the template's `col`, `positionY` its `row`. Tap buttons use `triggerType`
   `onShortPress` (`triggerLabel` `Short press`). `jsonBody` is a JSON **string**. Every `id` and
   `triggerId` is a fresh UUID. A batch that passes the dry run can still fail on apply if two
   buttons share a cell: it is rolled back, so fix and re-apply.
5. Prove the route without touching the microphone: `run_action` with `app.macro-deck.http` /
   `send-request`, `POST` to `/v1/app/models/select` with the model that is already current. It
   should report `Succeeded`.

### C. By hand in Macro Deck

Create the profile and six buttons in the Macro Deck editor from the table at the top. Each button
gets an **HTTP → Send HTTP Request** action, method `POST`, body type JSON. For *Hold to talk*, add
two triggers on the same button: **Touch start** sends `start`, **Touch end** sends `stop`.

## 4. Hand over

Ask the user to put the cursor in a text field on the computer, then on the phone:

- hold **Hold to talk**, say a sentence, let go: the text is typed;
- tap **Tap: start / stop**, speak, tap again.

If nothing happens, check `curl -s http://127.0.0.1:8723/v1/app/status` while they press (it
should say `recording`), and that the phone shows the *Hebrish Dictation* profile. A press that
changes nothing in the status means the button's URL or port is wrong (the user may have changed
the port in Settings, Local API: use theirs). Unknown problems:
<https://github.com/Hebrish-ASR/Hebrish-App/issues>.
