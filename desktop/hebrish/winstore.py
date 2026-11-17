"""The Microsoft Store (MSIX) build (1.041, 2026-11-17). No Qt import.

Start at login there is the manifest's StartupTask (packaging/windows/msix/AppxManifest.xml), which can't
pass `--hidden`: started_at_login() asks Windows how this process was activated, so a login start goes to
the tray like the Run-key start does elsewhere. Needs pywinrt (winrt-Windows.ApplicationModel*, the
`windows` extra); anything going wrong means "not at login" (the window shows, nothing breaks)."""


def started_at_login() -> bool:
    try:
        from winrt.windows.applicationmodel import AppInstance
        from winrt.windows.applicationmodel.activation import ActivationKind
        args = AppInstance.get_activated_event_args()
        return args is not None and args.kind == ActivationKind.STARTUP_TASK
    except Exception:
        return False
