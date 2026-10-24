**1.000: Hebrish 1.0. Output becomes three switches.**

Versions now count 1.000, 1.001, 1.002, and so on, for the desktop app and Android alike. Earlier releases have been taken down from GitHub; this one includes everything they had, including the personal dictionary from 0.8.0.

- **Output** on the Dictate tab (and in the tray menu) is now three buttons you can combine: *At the cursor*, *Clipboard* and *This window*. By default only *At the cursor* is on, so your dictation goes where you are typing and no longer also fills the app's text box. Turn on *This window* to collect takes there; *Clipboard* puts the whole take on the clipboard when it ends.
- Your earlier choice carries over: paste becomes *At the cursor* only, clipboard-only and text-box-only stay as they were.
- Takes in the text box are separated by a blank line, so separate thoughts read as separate blocks. The text is a little larger.
- Every take is still in History, whatever the switches say.
- **Paste last transcription**: an action key (Settings → Action keys) and a tray item that paste your last take again where the cursor is now, for when it went into the wrong window.
- Experimental, off by default (Settings → Output): when a take finds no text field to paste into, the overlay shows *No text field* with a **Paste** button. Click into the field you meant, then Paste. It uses the desktop's accessibility interface, and some apps report no field when there is one.
- Ubuntu 26.04 .deb and a portable Windows zip. Not yet tested on Windows hardware. Downloads: [hebrish.app/download](https://hebrish.app/download).
