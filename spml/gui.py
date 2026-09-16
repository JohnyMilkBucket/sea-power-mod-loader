"""Tkinter front end: the same libraries, ordering and sharing as the CLI, with a list you can click."""
from __future__ import annotations

import tkinter as tk
import sys
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk

from . import core, library, pack, share
from .core import Entry, SpmlError

PAD = 8

BG = "#0b1118"
SURFACE = "#111922"
SURFACE_2 = "#17212c"
BORDER = "#263442"
TEXT = "#eaf2f8"
MUTED = "#8fa1b2"
ACCENT = "#20e0bd"
ACCENT_DARK = "#0d806f"
BLUE = "#20b9ee"
WARNING = "#f4b942"
DANGER = "#ff6577"
SUCCESS = "#44d17a"


def _asset_path(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "assets" / name


def _configure_dark_theme(root: tk.Tk) -> None:
    style = ttk.Style(root)
    style.theme_use("clam")
    root.configure(background=BG)
    style.configure(".", background=BG, foreground=TEXT, font=("Segoe UI", 9))
    style.configure("TFrame", background=BG)
    style.configure("Card.TFrame", background=SURFACE, relief="solid", borderwidth=1)
    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure("Card.TLabel", background=SURFACE, foreground=TEXT)
    style.configure("Muted.TLabel", background=BG, foreground=MUTED)
    style.configure("CardMuted.TLabel", background=SURFACE, foreground=MUTED)
    style.configure("Title.TLabel", background=BG, foreground=TEXT,
                    font=("Segoe UI Semibold", 14))
    style.configure("Section.TLabel", background=SURFACE, foreground=TEXT,
                    font=("Segoe UI Semibold", 10))
    style.configure("Warning.TLabel", background="#332a18", foreground=WARNING,
                    padding=(10, 5))
    style.configure("TButton", background=SURFACE_2, foreground=TEXT,
                    bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
                    padding=(10, 7), relief="flat")
    style.map("TButton", background=[("active", "#22303d"), ("pressed", "#293b49")],
              foreground=[("disabled", "#607080")])
    style.configure("Primary.TButton", background=ACCENT, foreground="#04211d",
                    bordercolor=ACCENT, font=("Segoe UI Semibold", 9), padding=(14, 8))
    style.map("Primary.TButton", background=[("active", "#55ebce"), ("pressed", "#13c9aa")])
    style.configure("Secondary.TButton", background=SURFACE_2, foreground=ACCENT,
                    bordercolor=ACCENT_DARK, padding=(12, 8))
    style.configure("Danger.TButton", background="#3a2028", foreground="#ff8b98",
                    bordercolor="#61313d")
    style.configure("TEntry", fieldbackground=SURFACE_2, foreground=TEXT,
                    insertcolor=TEXT, bordercolor=BORDER, padding=7)
    style.configure("TCombobox", fieldbackground=SURFACE_2, background=SURFACE_2,
                    foreground=TEXT, arrowcolor=MUTED, bordercolor=BORDER, padding=6)
    style.map("TCombobox", fieldbackground=[("readonly", SURFACE_2)],
              foreground=[("readonly", TEXT)], selectbackground=[("readonly", SURFACE_2)])
    style.configure("Treeview", background=SURFACE, fieldbackground=SURFACE,
                    foreground=TEXT, bordercolor=BORDER, rowheight=32)
    style.configure("Treeview.Heading", background=SURFACE_2, foreground=MUTED,
                    bordercolor=BORDER, padding=(7, 7), font=("Segoe UI Semibold", 9))
    style.map("Treeview", background=[("selected", "#123f42")],
              foreground=[("selected", "#f3fffc")])
    style.map("Treeview.Heading", background=[("active", "#22303d")])
    style.configure("Vertical.TScrollbar", background=SURFACE_2, troughcolor=BG,
                    arrowcolor=MUTED, bordercolor=BG)


class ModLoaderApp:
    def __init__(self, root: tk.Tk, ctx) -> None:
        self.root = root
        self.ctx = ctx
        self.lib: library.Library | None = None

        root.title("Sea Power Mod Loader")
        root.geometry("1120x760")
        root.minsize(900, 620)
        _configure_dark_theme(root)

        self._build_menu()
        self._build_header()
        self._build_table()
        self._build_actions()
        self._build_statusbar()

        self.reload_libraries()
        self.refresh()

    # ------------------------------------------------------------------ building

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Change game folder...", command=self.on_change_game_folder)
        file_menu.add_command(label="Open loader data folder", command=self.on_open_data_folder)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.destroy)
        menubar.add_cascade(label="File", menu=file_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="About", command=self.on_about)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.root.config(menu=menubar)

    def on_change_game_folder(self) -> None:
        from tkinter import filedialog
        chosen = filedialog.askdirectory(title="Select your Sea Power folder",
                                         initialdir=str(self.ctx.game_dir))
        if not chosen:
            return
        try:
            core.set_game_dir(chosen)
        except SpmlError as exc:
            messagebox.showerror("Game folder", str(exc))
            return
        self.ctx.game_dir = Path(chosen)
        self.ctx.version = core.game_version(self.ctx.game_dir)
        self.rescan()
        self.refresh()
        self.say(f"Game folder set to {chosen}")

    def on_open_data_folder(self) -> None:
        import subprocess
        subprocess.run(["explorer", str(core.state_dir())], check=False)

    def on_about(self) -> None:
        from . import __version__
        messagebox.showinfo(
            "Sea Power Mod Loader",
            f"Sea Power Mod Loader {__version__}\n\n"
            "Switchable mod libraries, shareable mod lists and packs.\n\n"
            "It edits only the [LoadOrder] section of the game's own settings file, "
            "and never modifies game or mod files.\n\n"
            f"Game: {self.ctx.game_dir}\n"
            f"Data: {core.state_dir()}")

    def _build_header(self) -> None:
        brand = ttk.Frame(self.root, padding=(16, 12, 16, 8))
        brand.pack(fill="x")
        logo_path = _asset_path("logo-ui.png")
        if logo_path.is_file():
            try:
                self.logo_image = tk.PhotoImage(file=str(logo_path))
                ttk.Label(brand, image=self.logo_image).pack(side="left", padx=(0, 10))
            except tk.TclError:
                self.logo_image = None
        title_box = ttk.Frame(brand)
        title_box.pack(side="left")
        ttk.Label(title_box, text="Sea Power Mod Loader", style="Title.TLabel").pack(anchor="w")
        ttk.Label(title_box, text="LIBRARY  /  LOAD ORDER", style="Muted.TLabel",
                  font=("Segoe UI Semibold", 8)).pack(anchor="w")

        bar = ttk.Frame(self.root, style="Card.TFrame", padding=(14, 12))
        bar.pack(fill="x", padx=16)

        ttk.Label(bar, text="Current library", style="CardMuted.TLabel").pack(side="left", padx=(0, 8))
        self.library_var = tk.StringVar()
        self.library_box = ttk.Combobox(bar, textvariable=self.library_var, state="readonly", width=34)
        self.library_box.pack(side="left", padx=(0, 12))
        self.library_box.bind("<<ComboboxSelected>>", lambda _e: self.on_library_selected())

        for text, command in (
            ("New...", self.on_new_library),
            ("Duplicate", self.on_duplicate_library),
            ("Rename", self.on_rename_library),
            ("Delete", self.on_delete_library),
            ("Sync from game", self.on_sync),
        ):
            style = "Danger.TButton" if text == "Delete" else "TButton"
            ttk.Button(bar, text=text, command=command, style=style).pack(side="left", padx=3)

        info = ttk.Frame(self.root, padding=(18, 10, 18, 0))
        info.pack(fill="x")
        self.game_label = ttk.Label(info, text="", style="Muted.TLabel")
        self.game_label.pack(side="left")
        self.sync_label = ttk.Label(info, text="", style="Warning.TLabel")
        self.sync_label.pack(side="right")

    def _build_table(self) -> None:
        filters = ttk.Frame(self.root, padding=(16, 10, 16, 0))
        filters.pack(fill="x")
        self.search_var = tk.StringVar()
        search = ttk.Entry(filters, textvariable=self.search_var, width=42)
        search.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.search_var.trace_add("write", lambda *_: self.refresh())
        self.source_var = tk.StringVar(value="All sources")
        source = ttk.Combobox(filters, textvariable=self.source_var, state="readonly", width=16,
                              values=("All sources", "Workshop", "Local", "Missing"))
        source.pack(side="left")
        source.bind("<<ComboboxSelected>>", lambda _e: self.refresh())

        frame = ttk.Frame(self.root, padding=(16, 10, 16, 0))
        frame.pack(fill="both", expand=True)

        columns = ("on", "name", "source", "compat", "id")
        self.tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="extended")
        for key, title, width, anchor in (
            ("on", "On", 46, "center"),
            ("name", "Mod", 420, "w"),
            ("source", "Source", 90, "w"),
            ("compat", "Compatibility", 190, "w"),
            ("id", "ID", 110, "w"),
        ):
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, anchor=anchor, stretch=(key == "name"))

        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="left", fill="y")

        self.tree.tag_configure("disabled", foreground="#627383")
        self.tree.tag_configure("problem", foreground=DANGER)
        self.tree.tag_configure("compatible", foreground=SUCCESS)

        self.tree.bind("<Double-1>", lambda _e: self.toggle_selected())
        self.tree.bind("<space>", lambda _e: self.toggle_selected())

        side = ttk.Frame(frame, padding=(10, 0, 0, 0))
        side.pack(side="left", fill="y")
        for text, command in (
            ("Toggle", self.toggle_selected),
            ("Move up", lambda: self.move_selected(-1)),
            ("Move down", lambda: self.move_selected(1)),
            ("Add mod...", self.on_add_mod),
            ("Remove", self.on_remove_mod),
        ):
            ttk.Button(side, text=text, command=command, width=13).pack(pady=2)

        details = ttk.Frame(self.root, style="Card.TFrame", padding=(14, 10))
        details.pack(fill="x", padx=16, pady=(10, 0))
        self.detail_title = ttk.Label(details, text="Select a mod", style="Section.TLabel")
        self.detail_title.pack(anchor="w")
        self.detail_text = ttk.Label(details, text="Select a row to see its source, id and compatibility.",
                                     style="CardMuted.TLabel")
        self.detail_text.pack(anchor="w", pady=(4, 0))
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._update_details())

    def _build_actions(self) -> None:
        bar = ttk.Frame(self.root, padding=(16, 10))
        bar.pack(fill="x")
        for text, command in (
            ("Rescan mods", self.on_scan),
            ("Check problems", self.on_check),
            ("Export / share", self.on_export),
            ("Import list...", self.on_import),
        ):
            ttk.Button(bar, text=text, command=command).pack(side="left", padx=2)

        self.play_button = ttk.Button(bar, text="Apply & Play  ▶", command=self.on_play,
                                      style="Primary.TButton")
        self.play_button.pack(side="right", padx=(6, 0))
        self.apply_button = ttk.Button(bar, text="Apply changes", command=self.on_apply,
                                       style="Secondary.TButton")
        self.apply_button.pack(side="right")

    def _build_statusbar(self) -> None:
        self.status = tk.StringVar()
        ttk.Label(self.root, textvariable=self.status, style="Muted.TLabel",
                  anchor="w", padding=(16, 6)).pack(fill="x", side="bottom")

    # ------------------------------------------------------------------- helpers

    def say(self, message: str) -> None:
        self.status.set(message)

    def reload_libraries(self) -> None:
        libs = library.list_libraries()
        if not libs:
            seed = library.library_from_entries(
                "Default", self.ctx.live_order(), self.ctx.version,
                notes="Created from the load order already set in the game.")
            library.save_library(seed)
            library.set_active(seed.name)
            libs = [seed]
        names = [lib.name for lib in libs]
        self.library_box["values"] = names

        active = library.active()
        chosen = active.name if active and active.name in names else names[0]
        self.library_var.set(chosen)
        self.lib = library.load_library(chosen)

    def on_library_selected(self) -> None:
        self.lib = library.load_library(self.library_var.get())
        self.refresh()
        self.say(f"Showing library '{self.lib.name}'. It is not applied to the game until you press Apply.")

    def save(self) -> None:
        if self.lib:
            library.save_library(self.lib)

    def selected_indexes(self) -> list[int]:
        return sorted(int(item) for item in self.tree.selection())

    def _update_details(self) -> None:
        if not self.lib or not self.tree.selection():
            self.detail_title.config(text="Select a mod")
            self.detail_text.config(text="Select a row to see its source, id and compatibility.")
            return
        index = int(self.tree.selection()[0])
        entry = self.lib.mods[index]
        mod = self.ctx.mods.get(entry.id)
        name = self.ctx.display_name(entry.id)
        self.detail_title.config(text=name)
        if mod is None:
            detail = f"Not installed   •   ID {entry.id}   •   {'Enabled' if entry.enabled else 'Disabled'}"
        else:
            _status, note = mod.compat_status(self.ctx.version)
            code = "   •   Code mod" if mod.has_code else ""
            description = f"   •   {mod.description}" if mod.description else ""
            detail = (f"{mod.source.title()}   •   ID {entry.id}   •   {note}"
                      f"   •   {'Enabled' if entry.enabled else 'Disabled'}{code}{description}")
        self.detail_text.config(text=detail)

    # ------------------------------------------------------------------ refresh

    def refresh(self, keep_selection: list[int] | None = None) -> None:
        self.tree.delete(*self.tree.get_children())
        if not self.lib:
            return

        query = self.search_var.get().strip().lower()
        source_filter = self.source_var.get().lower()
        visible = 0
        for index, entry in enumerate(self.lib.mods):
            mod = self.ctx.mods.get(entry.id)
            name = self.ctx.display_name(entry.id)
            tags = [] if entry.enabled else ["disabled"]
            if mod is None:
                compat, source = "Not installed", "Missing"
                tags = ["problem"]
            else:
                status, note = mod.compat_status(self.ctx.version)
                source = mod.source.title()
                compat = {"ok": "Compatible", "unknown": "Not declared"}.get(status, note)
                if status == "bad" and entry.enabled:
                    tags = ["problem"]
                elif status == "ok" and entry.enabled:
                    tags = ["compatible"]
            if mod is not None and mod.has_code:
                name += "  (code)"
            if query and query not in f"{name} {entry.id} {source} {compat}".lower():
                continue
            if source_filter != "all sources" and source.lower() != source_filter:
                continue
            self.tree.insert("", "end", iid=str(index),
                             values=("ON" if entry.enabled else "OFF", name, source, compat, entry.id),
                             tags=tags)
            visible += 1

        for index in keep_selection or []:
            if self.tree.exists(str(index)):
                self.tree.selection_add(str(index))

        enabled = self.lib.enabled_count
        running = core.game_running()
        self.game_label.config(
            text=f"Sea Power {self.ctx.version or '?'}   •   {len(self.ctx.mods)} mods installed   •   "
                 f"{enabled}/{len(self.lib.mods)} enabled"
                 + (f"   •   {visible} shown" if visible != len(self.lib.mods) else "")
                 + ("   [game is running: close it before applying]" if running else ""))

        live = self.ctx.live_order()
        if library.is_in_sync(self.lib, live):
            self.sync_label.config(text="✓  Matches the game", style="Muted.TLabel")
            self.say(f"Library '{self.lib.name}' matches the game.")
        else:
            self.sync_label.config(text="⚠  This library differs from the game", style="Warning.TLabel")
            self.say(f"Library '{self.lib.name}' differs from what the game currently has loaded "
                     "- press Apply to push it, or 'Sync from game' to pull the game's version in.")
        self._update_details()

    def rescan(self) -> None:
        self.ctx.mods = core.discover_mods(self.ctx.game_dir)
        self.ctx.catalog = library.Catalog()

    # ------------------------------------------------------------------- editing

    def toggle_selected(self) -> None:
        indexes = self.selected_indexes()
        if not indexes or not self.lib:
            return
        for index in indexes:
            self.lib.mods[index].enabled = not self.lib.mods[index].enabled
        self.save()
        self.refresh(keep_selection=indexes)

    def move_selected(self, delta: int) -> None:
        indexes = self.selected_indexes()
        if not indexes or not self.lib:
            return
        order = indexes if delta < 0 else list(reversed(indexes))
        moved = []
        for index in order:
            target = index + delta
            if target < 0 or target >= len(self.lib.mods):
                moved.append(index)
                continue
            mods = self.lib.mods
            mods[index], mods[target] = mods[target], mods[index]
            moved.append(target)
        self.save()
        self.refresh(keep_selection=sorted(moved))

    def on_add_mod(self) -> None:
        if not self.lib:
            return
        present = {e.id for e in self.lib.mods}
        available = [m for m in self.ctx.mods.values() if m.id not in present]
        if not available:
            messagebox.showinfo("Add mod", "Every installed mod is already in this library.")
            return
        AddModDialog(self.root, available, self._add_mods)

    def _add_mods(self, mods) -> None:
        if not self.lib:
            return
        self.lib.mods += [Entry(mod.id, enabled=True) for mod in mods]
        self.save()
        self.refresh()
        self.say(f"Added {len(mods)} mod(s) to '{self.lib.name}'.")

    def on_remove_mod(self) -> None:
        indexes = self.selected_indexes()
        if not indexes or not self.lib:
            return
        for index in reversed(indexes):
            self.lib.mods.pop(index)
        self.save()
        self.refresh()
        self.say("Removed from the library. The mod itself is still installed.")

    # ------------------------------------------------------------------ libraries

    def on_new_library(self) -> None:
        name = simpledialog.askstring("New library", "Name for the new mod set:", parent=self.root)
        if not name:
            return
        if library.library_path(name).exists():
            messagebox.showerror("New library", f"A library named '{name}' already exists.")
            return
        seed = messagebox.askyesno(
            "New library",
            "Start from the mods currently loaded in the game?\n\n"
            "Yes - copy the game's current load order\nNo - start empty")
        entries = self.ctx.live_order() if seed else []
        lib = library.library_from_entries(name, entries, self.ctx.version)
        library.save_library(lib)
        self.reload_libraries()
        self.library_var.set(lib.name)
        self.lib = library.load_library(lib.name)
        self.refresh()
        self.say(f"Created library '{name}'.")

    def on_duplicate_library(self) -> None:
        if not self.lib:
            return
        name = simpledialog.askstring("Duplicate library", "Name for the copy:",
                                      initialvalue=f"{self.lib.name} copy", parent=self.root)
        if not name:
            return
        if library.library_path(name).exists():
            messagebox.showerror("Duplicate library", f"A library named '{name}' already exists.")
            return
        copy = library.library_from_entries(name, self.lib.mods, self.lib.game_version, self.lib.notes)
        library.save_library(copy)
        self.reload_libraries()
        self.library_var.set(name)
        self.lib = library.load_library(name)
        self.refresh()

    def on_rename_library(self) -> None:
        if not self.lib:
            return
        name = simpledialog.askstring("Rename library", "New name:", initialvalue=self.lib.name, parent=self.root)
        if not name or name == self.lib.name:
            return
        try:
            renamed = library.rename_library(self.lib.name, name)
        except SpmlError as exc:
            messagebox.showerror("Rename library", str(exc))
            return
        self.reload_libraries()
        self.library_var.set(renamed.name)
        self.lib = library.load_library(renamed.name)
        self.refresh()

    def on_delete_library(self) -> None:
        if not self.lib:
            return
        if len(library.list_libraries()) <= 1:
            messagebox.showinfo("Delete library", "This is your only library, so it cannot be deleted.")
            return
        if not messagebox.askyesno("Delete library",
                                   f"Delete '{self.lib.name}'?\n\nThe mods themselves are not touched."):
            return
        library.delete_library(self.lib.name)
        self.reload_libraries()
        self.refresh()
        self.say("Library deleted.")

    def on_sync(self) -> None:
        if not self.lib:
            return
        self.lib.mods = self.ctx.live_order()
        self.lib.game_version = self.ctx.version
        self.save()
        self.refresh()
        self.say(f"Pulled the game's current load order into '{self.lib.name}'.")

    # -------------------------------------------------------------------- actions

    def on_scan(self) -> None:
        self.rescan()
        new_ids = self.ctx.catalog.merge(self.ctx.mods)
        self.ctx.catalog.save()
        self.refresh()
        if new_ids:
            names = "\n".join(f"  - {self.ctx.mods[i].name}" for i in new_ids)
            if messagebox.askyesno("Rescan", f"Found {len(new_ids)} new mod(s):\n\n{names}\n\n"
                                             f"Add them to '{self.lib.name}' (switched off)?"):
                self.lib.mods += [Entry(i, enabled=False) for i in new_ids]
                self.save()
                self.refresh()
        else:
            self.say(f"Rescanned: {len(self.ctx.mods)} mods installed, nothing new.")

    def on_check(self) -> None:
        if not self.lib:
            return
        problems = []
        for entry in self.lib.mods:
            if not entry.enabled:
                continue
            mod = self.ctx.mods.get(entry.id)
            if mod is None:
                problems.append(f"MISSING: {self.ctx.display_name(entry.id)} is enabled but not installed")
                continue
            status, note = mod.compat_status(self.ctx.version)
            if status == "bad":
                problems.append(f"VERSION: {mod.name} - {note}")

        code_mods = [e for e in self.lib.mods
                     if e.enabled and (m := self.ctx.mods.get(e.id)) and m.has_code and e.id != core.ANCHOR_CHAIN_ID]
        anchor = next((e for e in self.lib.mods if e.id == core.ANCHOR_CHAIN_ID), None)
        if code_mods and (anchor is None or not anchor.enabled):
            names = ", ".join(self.ctx.display_name(e.id) for e in code_mods)
            problems.append(f"LOADER: {names} need Anchor Chain enabled to load their code")

        if problems:
            messagebox.showwarning("Check", "\n\n".join(problems))
        else:
            messagebox.showinfo("Check", "No problems found.\n\nMods that declare no compatibility "
                                         "information are not checked.")

    def on_apply(self) -> None:
        if not self.lib:
            return
        if core.game_running():
            if not messagebox.askyesno(
                    "Sea Power is running",
                    "Sea Power is running and rewrites its settings when it exits, "
                    "which would discard this change.\n\nClose the game first.\n\nApply anyway?"):
                return
        try:
            entries = [e for e in self.lib.mods if e.id in self.ctx.mods]
            dropped = [e.id for e in self.lib.mods if e.id not in self.ctx.mods]
            core.write_load_order(entries, self.ctx.settings, force=True)
            library.set_active(self.lib.name)
        except SpmlError as exc:
            messagebox.showerror("Apply", str(exc))
            return

        note = ""
        if dropped:
            note = "\n\nSkipped (not installed): " + ", ".join(self.ctx.display_name(i) for i in dropped)
        messagebox.showinfo("Applied", f"'{self.lib.name}' is now the active mod set.\n\n"
                                       f"Restart Sea Power for it to take effect.{note}")
        self.refresh()

    def on_play(self) -> None:
        """Apply this library if needed, then start the game through Steam."""
        if core.game_running():
            messagebox.showinfo("Play", "Sea Power is already running.")
            return
        if self.lib and not library.is_in_sync(self.lib, self.ctx.live_order()):
            if not messagebox.askyesno(
                    "Apply and play",
                    f"'{self.lib.name}' is not the mod set the game currently has.\n\n"
                    "Apply it and launch?"):
                return
            try:
                entries = [e for e in self.lib.mods if e.id in self.ctx.mods]
                core.write_load_order(entries, self.ctx.settings, force=True)
                library.set_active(self.lib.name)
            except SpmlError as exc:
                messagebox.showerror("Apply", str(exc))
                return
        try:
            note = core.launch_game(self.ctx.game_dir)
        except SpmlError as exc:
            messagebox.showerror("Play", str(exc))
            return
        self.refresh()
        self.say(f"{note.capitalize()} - it may take a moment to appear.")

    def on_export(self) -> None:
        if not self.lib:
            return
        payload = share.build_list(self.lib.mods, self.ctx.mods, name=self.lib.name, game_version=self.ctx.version)
        for item in payload["mods"]:
            if not item["name"]:
                item["name"] = self.ctx.catalog.name_for(item["id"], fallback="")
        ShareDialog(self.root, payload, self.ctx)

    def on_import(self) -> None:
        ImportDialog(self.root, self)


# ------------------------------------------------------------------------ dialogs


class AddModDialog(tk.Toplevel):
    """Pick installed mods that are not yet in this library."""

    def __init__(self, parent: tk.Misc, mods, on_add) -> None:
        super().__init__(parent)
        self.title("Add mods to library")
        self.geometry("520x380")
        self.transient(parent)
        self.mods = sorted(mods, key=lambda m: m.name.lower())
        self.on_add = on_add

        ttk.Label(self, text="Installed mods not yet in this library:",
                  padding=(PAD, PAD, PAD, 4)).pack(anchor="w")
        box = ttk.Frame(self, padding=(PAD, 0, PAD, 0))
        box.pack(fill="both", expand=True)
        self.listbox = tk.Listbox(box, selectmode="extended")
        for mod in self.mods:
            suffix = "  (code)" if mod.has_code else ""
            self.listbox.insert("end", f"{mod.name}{suffix}   [{mod.source}]")
        self.listbox.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(box, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scroll.set)
        scroll.pack(side="left", fill="y")

        buttons = ttk.Frame(self, padding=PAD)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Add selected", command=self.confirm).pack(side="right")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right", padx=4)
        self.grab_set()

    def confirm(self) -> None:
        chosen = [self.mods[i] for i in self.listbox.curselection()]
        if chosen:
            self.on_add(chosen)
        self.destroy()


class ProgressWindow(tk.Toplevel):
    """A small modal progress readout for packing and unpacking."""

    def __init__(self, parent: tk.Misc, title: str) -> None:
        super().__init__(parent)
        self.title(title)
        self.geometry("380x110")
        self.transient(parent)
        self.resizable(False, False)
        self.label = ttk.Label(self, text="Working...", padding=PAD)
        self.label.pack(fill="x")
        self.bar = ttk.Progressbar(self, mode="determinate", maximum=100)
        self.bar.pack(fill="x", padx=PAD, pady=(0, PAD))
        self.grab_set()
        self.update_idletasks()

    def update(self, index: int, total: int, name: str) -> None:
        self.label.config(text=f"{index} of {total}: {name}")
        self.bar["value"] = (index / max(total, 1)) * 100
        self.update_idletasks()


class ShareDialog(tk.Toplevel):
    """Show the share code so it can be copied into chat, or saved as a file."""

    def __init__(self, parent: tk.Misc, payload: dict, ctx=None) -> None:
        super().__init__(parent)
        self.title("Share this mod list")
        self.geometry("640x460")
        self.transient(parent)
        self.payload = payload
        self.ctx = ctx

        header = f"{payload['name']} - {len(payload['mods'])} mod(s)"
        ttk.Label(self, text=header, padding=(PAD, PAD, PAD, 0)).pack(anchor="w")
        ttk.Label(self, text="Send this code to anyone. They paste it into Import to get your exact setup.",
                  foreground="#555", padding=(PAD, 0, PAD, 4)).pack(anchor="w")

        self.text = tk.Text(self, wrap="char", height=8)
        self.text.pack(fill="both", expand=True, padx=PAD)
        self.text.insert("1.0", share.encode_code(payload))
        self.text.configure(state="disabled")

        listing = tk.Text(self, wrap="none", height=8)
        listing.pack(fill="both", expand=True, padx=PAD, pady=(PAD, 0))
        for item in payload["mods"]:
            mark = "x" if item["enabled"] else " "
            listing.insert("end", f"[{mark}] {item.get('name') or item['id']}  ({item['id']})\n")
        listing.configure(state="disabled")

        buttons = ttk.Frame(self, padding=PAD)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Copy code", command=self.copy).pack(side="right")
        ttk.Button(buttons, text="Save as file...", command=self.save_file).pack(side="right", padx=4)
        if self.ctx is not None:
            ttk.Button(buttons, text="Export as pack...", command=self.save_pack).pack(side="right", padx=4)
        ttk.Button(buttons, text="Close", command=self.destroy).pack(side="right")
        self.grab_set()

    def copy(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self.text.get("1.0", "end").strip())
        messagebox.showinfo("Copied", "Share code copied to the clipboard.", parent=self)

    def save_file(self) -> None:
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(
            parent=self, defaultextension=".spml.json",
            initialfile=f"{library.slugify(self.payload['name'])}.spml.json",
            filetypes=[("Mod list", "*.json"), ("All files", "*.*")])
        if path:
            from pathlib import Path
            share.write_list(self.payload, Path(path))
            messagebox.showinfo("Saved", f"Mod list written to\n{path}", parent=self)

    def save_pack(self) -> None:
        """Bundle the mod folders themselves, not just the list of which ones."""
        from pathlib import Path
        from tkinter import filedialog

        entries = [Entry(i["id"], i.get("enabled", True)) for i in self.payload["mods"]]
        local = pack.plan_pack(entries, self.ctx.mods, include_workshop=False)
        workshop = [i for i in local if not i.bundled and i.mod.source == "workshop"]

        include_workshop = False
        if workshop:
            size = pack.human_size(sum(i.size for i in workshop))
            answer = messagebox.askyesnocancel(
                "Include Workshop mods?",
                f"{len(workshop)} of these mods come from the Steam Workshop ({size}).\n\n"
                "No  - list them by id, so the other person subscribes themselves (recommended)\n"
                "Yes - copy their files into the pack\n\n"
                "Copying them means redistributing the authors' work, which the Workshop terms "
                "generally do not allow. Only choose Yes if you have the right to share them.",
                parent=self)
            if answer is None:
                return
            include_workshop = answer

        path = filedialog.asksaveasfilename(
            parent=self, defaultextension=pack.PACK_SUFFIX,
            initialfile=f"{library.slugify(self.payload['name'])}{pack.PACK_SUFFIX}",
            filetypes=[("Mod pack", f"*{pack.PACK_SUFFIX}"), ("Zip", "*.zip")])
        if not path:
            return

        progress = ProgressWindow(self, "Building pack")
        try:
            out, items = pack.build_pack(self.payload, self.ctx.mods, Path(path),
                                         include_workshop=include_workshop, progress=progress.update)
        except SpmlError as exc:
            progress.destroy()
            messagebox.showerror("Export pack", str(exc), parent=self)
            return
        progress.destroy()

        left_out = [i for i in items if not i.bundled]
        note = ""
        if left_out:
            note = "\n\nListed but not bundled:\n" + "\n".join(f"  - {i.mod.name} ({i.reason})" for i in left_out)
        messagebox.showinfo("Pack created",
                            f"{out.name}\n{pack.human_size(out.stat().st_size)} on disk.\n\n"
                            f"Send this file. They open it with Import list.{note}", parent=self)


class ImportDialog(tk.Toplevel):
    """Paste a share code (or load a file) and turn it into a library."""

    def __init__(self, parent: tk.Misc, app: ModLoaderApp) -> None:
        super().__init__(parent)
        self.title("Import a mod list")
        self.geometry("620x340")
        self.transient(parent)
        self.app = app

        ttk.Label(self, text="Paste a share code from a friend, or load a mod list or pack file:",
                  padding=(PAD, PAD, PAD, 4)).pack(anchor="w")
        self.text = tk.Text(self, wrap="char", height=7)
        self.text.pack(fill="both", expand=True, padx=PAD)

        buttons = ttk.Frame(self, padding=PAD)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Import", command=self.confirm).pack(side="right")
        ttk.Button(buttons, text="Load from file...", command=self.load_file).pack(side="right", padx=4)
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        self.grab_set()

    def load_file(self) -> None:
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            parent=self,
            filetypes=[("Mod list or pack", f"*.json *{pack.PACK_SUFFIX} *.zip"),
                       ("Mod pack", f"*{pack.PACK_SUFFIX}"),
                       ("Mod list", "*.json"), ("All files", "*.*")])
        if path:
            self.text.delete("1.0", "end")
            self.text.insert("1.0", path)

    def import_pack(self, source: str) -> None:
        """Install a pack's bundled mod folders, then build a library pointing at them."""
        ctx = self.app.ctx
        try:
            payload = pack.read_pack(source)
        except SpmlError as exc:
            messagebox.showerror("Import", str(exc), parent=self)
            return

        info = payload.get("pack", {})
        bundled = set(info.get("bundled", []))
        already = [i for i in bundled if i in ctx.mods]
        listed_only = [i["id"] for i in payload["mods"] if i["id"] not in bundled and i["id"] not in ctx.mods]

        summary = (f"'{payload['name']}'\n\n"
                   f"{len(payload['mods'])} mod(s) listed, {len(bundled)} bundled in the file.")
        if already:
            summary += f"\n{len(already)} of them are already installed and will be left alone."
        if listed_only:
            summary += f"\n{len(listed_only)} are not bundled and not installed - you will need to subscribe."
        summary += "\n\nInstall the bundled mods now?"
        if not messagebox.askyesno("Import pack", summary, parent=self):
            return

        name = simpledialog.askstring("Import pack", "Name for the imported library:",
                                      initialvalue=payload["name"], parent=self)
        if not name:
            return
        if library.library_path(name).exists():
            if not messagebox.askyesno("Import", f"Replace the existing library '{name}'?", parent=self):
                return

        progress = ProgressWindow(self, "Installing mods")
        try:
            id_map, skipped, _ = pack.install_pack(source, ctx.game_dir, ctx.mods, progress=progress.update)
        except SpmlError as exc:
            progress.destroy()
            messagebox.showerror("Import pack", str(exc), parent=self)
            return
        progress.destroy()

        self.app.rescan()
        ctx.catalog.merge(ctx.mods)
        for item in payload["mods"]:
            if item["id"] not in ctx.catalog.entries and item.get("name"):
                ctx.catalog.entries[item["id"]] = {"name": item["name"], "source": item.get("source", "workshop"),
                                                   "description": "", "has_code": False, "imported": True}
        ctx.catalog.save()

        entries = pack.remap_entries(payload, id_map)
        lib = library.library_from_entries(name, entries, payload.get("game_version"),
                                           notes="Imported from a mod pack")
        library.save_library(lib)

        missing = [e.id for e in entries if e.id not in ctx.mods]
        if missing:
            names = "\n".join(f"  - {ctx.display_name(i)}" for i in missing)
            if messagebox.askyesno("Missing mods",
                                   f"{len(missing)} mod(s) were listed but not bundled:\n\n{names}\n\n"
                                   "Open them on the Steam Workshop so you can subscribe?", parent=self):
                share.open_workshop_pages(missing)

        self.destroy()
        self.app.reload_libraries()
        self.app.library_var.set(lib.name)
        self.app.lib = library.load_library(lib.name)
        self.app.refresh()
        self.app.say(f"Installed {len(id_map)} mod(s) and imported '{lib.name}'. Press Apply to load it.")

    def confirm(self) -> None:
        source = self.text.get("1.0", "end").strip()
        if not source:
            return
        if pack.is_pack(source):
            self.import_pack(source)
            return
        try:
            payload = share.read_list(source)
        except SpmlError as exc:
            messagebox.showerror("Import", str(exc), parent=self)
            return

        ctx = self.app.ctx
        missing = [i for i in payload["mods"] if i["id"] not in ctx.mods]
        name = simpledialog.askstring("Import", "Name for the imported library:",
                                      initialvalue=payload["name"], parent=self)
        if not name:
            return
        if library.library_path(name).exists():
            if not messagebox.askyesno("Import", f"Replace the existing library '{name}'?", parent=self):
                return

        entries = [Entry(i["id"], bool(i.get("enabled", True))) for i in payload["mods"]]
        for item in payload["mods"]:
            if item["id"] not in ctx.catalog.entries and item.get("name"):
                ctx.catalog.entries[item["id"]] = {"name": item["name"], "source": item.get("source", "workshop"),
                                                   "description": "", "has_code": False, "imported": True}
        ctx.catalog.save()
        lib = library.library_from_entries(name, entries, payload.get("game_version"), notes="Imported")
        library.save_library(lib)

        if missing:
            names = "\n".join(f"  - {i.get('name') or i['id']}" for i in missing)
            if messagebox.askyesno("Missing mods",
                                   f"{len(missing)} mod(s) in this list are not installed:\n\n{names}\n\n"
                                   "Open them on the Steam Workshop so you can subscribe?", parent=self):
                share.open_workshop_pages([i["id"] for i in missing])

        self.destroy()
        self.app.reload_libraries()
        self.app.library_var.set(lib.name)
        self.app.lib = library.load_library(lib.name)
        self.app.refresh()
        self.app.say(f"Imported '{lib.name}'. Press Apply to load it into the game.")


def run(ctx) -> int:
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass
    ModLoaderApp(root, ctx)
    root.mainloop()
    return 0
