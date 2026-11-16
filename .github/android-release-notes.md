**1.036: Model downloads survive a dropped connection.**

- **Retries instead of failing:** a timeout, a dropped connection or a server error no longer stops a model download. It waits (2 s, then longer, up to 30 s) and carries on from where it stopped; with no network at all it waits for one. It gives up only after 10 minutes online without any progress. The card shows "Connection lost: retrying…" or "Waiting for a connection…".
- **Keeps going in the background:** a download you start runs with a progress notification (with Cancel), so it continues with the screen off or in another app.
- **Background model updates on Wi-Fi now run:** the app was missing the permission to tell Wi-Fi from mobile data, so with "Only on Wi-Fi" on they never did.
- Not yet tested on a device. arm64-v8a only. Android 9+. Downloads: [hebrish.app/download](https://hebrish.app/download).
