# Desktop crashes at start when /dev/uinput doesn't exist

- **Date:** 2026-10-31 · **Platform:** desktop-linux · **Status:** fixed (unreleased; first in 1.017)
- **Found by:** the AppImage's offline first-start test (ubuntu:22.04 container, Xvfb, no network), B-80.

## Symptom
`Controller.__init__` -> `make_inserter()` -> `LinuxInserter()` raised
`evdev.uinput.UInputError: "/dev/uinput" does not exist or is not a character device file` and
the app exited before showing a window.

## Cause
`inserter_linux.LinuxInserter` caught only `OSError` around `UInput(...)`, which covers a
`/dev/uinput` without permission (the usual case, handled since 0.x: "transcripts go to the
clipboard only"). When the device node is missing altogether (uinput module not loaded, some
containers, minimal or unusual kernels), python-evdev's `UInput._verify()` raises its own
`UInputError`, a plain `Exception` subclass. Same gap in `hotkey_evdev.hold_send` (the Enter
guard's passthrough device).

## Fix
Both sites catch `(OSError, UInputError)`. The inserter's message says the device doesn't exist
and asks whether the uinput module is loaded; under an AppImage it adds the udev-rule command.

## Checked
Re-ran the same container test: the window opens on Models. Unit tests unchanged (314 passed;
the one failure is the known `test_numbers_and_rules_match_the_website`).

## Ruled out
Not AppImage-specific: the .deb has the same code path; Ubuntu desktops load uinput, so it hadn't
shown there.
