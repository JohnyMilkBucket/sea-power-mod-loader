"""Entry point for the packaged desktop app.

The CLI can report a problem and exit; a double-clicked .exe has no console to report
into, so everything that can fail before the window opens - Steam missing, the game
moved, the game never launched - has to become a dialog the user can act on.
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

from . import core
from .core import SpmlError


def _icon_path() -> Path | None:
    """The bundled icon, whether running from source or from a PyInstaller build."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    for candidate in (base / "assets" / "icon.ico", base / "icon.ico"):
        if candidate.is_file():
            return candidate
    return None


def _apply_icon(root) -> None:
    icon = _icon_path()
    if icon:
        try:
            root.iconbitmap(str(icon))
        except Exception:                                  # noqa: BLE001 - cosmetic only
            pass


def resolve_game(root):
    """Get a working Context, asking the user to locate the game if we cannot find it."""
    from tkinter import filedialog, messagebox
    from .cli import Context

    while True:
        try:
            return Context()
        except SpmlError as exc:
            choice = messagebox.askretrycancel(
                "Sea Power not found",
                f"{exc}\n\nPress Retry to pick the Sea Power folder yourself, "
                "or Cancel to quit.",
                icon="warning")
            if not choice:
                return None
            chosen = filedialog.askdirectory(title="Select your Sea Power folder")
            if not chosen:
                continue
            try:
                core.set_game_dir(chosen)
            except SpmlError as bad:
                messagebox.showerror("Not a Sea Power folder", str(bad))


def check_settings(root, ctx) -> bool:
    """The game writes its settings on first run; without them there is no load order."""
    from tkinter import messagebox

    if ctx.settings.is_file():
        return True

    launch = messagebox.askyesno(
        "Sea Power has not been run yet",
        "The loader edits the mod list inside Sea Power's own settings file, and that "
        "file does not exist yet:\n\n"
        f"{ctx.settings}\n\n"
        "Sea Power needs to be launched once so it creates it.\n\n"
        "Launch Sea Power now?",
        icon="warning")
    if launch:
        try:
            core.launch_game(ctx.game_dir)
            messagebox.showinfo(
                "Launching",
                "Sea Power is starting. Once you have reached the main menu, quit the game "
                "and open the mod loader again.")
        except SpmlError as exc:
            messagebox.showerror("Launch failed", str(exc))
    return False


def main() -> int:
    try:
        import tkinter as tk
        from tkinter import messagebox
    except ImportError:
        print("This build is missing Tk, so the window cannot open. Use spml.exe instead.")
        return 1

    root = tk.Tk()
    root.withdraw()
    _apply_icon(root)

    def show_unexpected(*exc_info) -> None:
        """Never die silently: an unhandled error in a callback becomes a dialog."""
        detail = "".join(traceback.format_exception(*(exc_info or sys.exc_info())))
        messagebox.showerror(
            "Something went wrong",
            "The mod loader hit an unexpected error. Your game files and mods are not "
            "affected.\n\n" + detail[-1500:])

    root.report_callback_exception = lambda *a: show_unexpected(*a)

    try:
        ctx = resolve_game(root)
        if ctx is None:
            root.destroy()
            return 1
        if not check_settings(root, ctx):
            root.destroy()
            return 1

        from .gui import ModLoaderApp
        root.deiconify()
        ModLoaderApp(root, ctx)
        # Launched from a shortcut or from Steam's overlay the window can open behind
        # whatever had focus, which looks like nothing happened.
        root.lift()
        root.after(50, root.focus_force)
        root.mainloop()
        return 0
    except SpmlError as exc:
        messagebox.showerror("Sea Power Mod Loader", str(exc))
        return 2
    except Exception:                                      # noqa: BLE001 - last resort
        show_unexpected()
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
