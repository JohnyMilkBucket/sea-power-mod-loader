"""Libraries: named, switchable mod sets, plus a catalog of every mod ever seen.

A library is one self-contained mod set - "Cold War campaign", "Multiplayer night",
"vanilla" - holding an ordered list of mods and whether each is on. Exactly one
library is active at a time; activating it writes the game's [LoadOrder].

The catalog is the loader's memory. Scanning records every installed mod (Workshop
or local) so libraries can name mods that are not installed right now, and so a mod
you unsubscribe from does not become an anonymous number in your saved sets.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from .core import APP_ID, Entry, Mod, SpmlError, state_dir


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def slugify(name: str) -> str:
    slug = re.sub(r"[^\w.\-]+", "-", name.strip().lower()).strip("-")
    if not slug:
        raise SpmlError("Library name must contain at least one letter or number.")
    return slug


# ------------------------------------------------------------------------- catalog


class Catalog:
    """Everything the loader has ever seen installed, keyed by mod id."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (state_dir() / "catalog.json")
        self.entries: dict[str, dict] = {}
        if self.path.is_file():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self.entries = data.get("mods", {})
            except (json.JSONDecodeError, OSError):
                self.entries = {}

    def merge(self, mods: dict[str, Mod]) -> list[str]:
        """Fold discovered mods in. Returns the ids that were new to the catalog."""
        new = []
        for mod_id, mod in mods.items():
            if mod_id not in self.entries:
                new.append(mod_id)
            record = self.entries.setdefault(mod_id, {"first_seen": _now()})
            record.update({
                "name": mod.name,
                "source": mod.source,
                "description": mod.description,
                "has_code": mod.has_code,
                "path": str(mod.path),
                "last_seen": _now(),
            })
        return new

    def name_for(self, mod_id: str, fallback: str = "") -> str:
        return self.entries.get(mod_id, {}).get("name") or fallback or mod_id

    def save(self) -> None:
        payload = {"format": "spml-catalog", "version": 1, "updated": _now(), "mods": self.entries}
        self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


# ----------------------------------------------------------------------- libraries


@dataclass
class Library:
    name: str
    mods: list[Entry] = field(default_factory=list)
    notes: str = ""
    game_version: str | None = None
    created: str = field(default_factory=_now)
    updated: str = field(default_factory=_now)

    @property
    def slug(self) -> str:
        return slugify(self.name)

    @property
    def enabled_count(self) -> int:
        return sum(1 for m in self.mods if m.enabled)

    def to_dict(self) -> dict:
        return {
            "format": "spml-library",
            "version": 1,
            "name": self.name,
            "app_id": APP_ID,
            "game_version": self.game_version,
            "notes": self.notes,
            "created": self.created,
            "updated": self.updated,
            "mods": [{"order": i, "id": e.id, "enabled": e.enabled} for i, e in enumerate(self.mods, 1)],
        }

    @classmethod
    def from_dict(cls, data: dict, name: str | None = None) -> "Library":
        mods = [
            Entry(str(item["id"]), bool(item.get("enabled", True)))
            for item in sorted(data.get("mods", []), key=lambda m: m.get("order", 0))
        ]
        return cls(
            name=name or data.get("name") or "Unnamed",
            mods=mods,
            notes=data.get("notes", ""),
            game_version=data.get("game_version"),
            created=data.get("created", _now()),
            updated=data.get("updated", _now()),
        )


def libraries_dir() -> Path:
    path = state_dir() / "libraries"
    path.mkdir(parents=True, exist_ok=True)
    return path


def library_path(name: str) -> Path:
    return libraries_dir() / f"{slugify(name)}.json"


def save_library(library: Library) -> Path:
    library.updated = _now()
    path = library_path(library.name)
    path.write_text(json.dumps(library.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_library(name: str) -> Library:
    path = library_path(name)
    if not path.is_file():
        known = ", ".join(lib.name for lib in list_libraries()) or "none yet"
        raise SpmlError(f"No library named {name!r}. Existing libraries: {known}")
    return Library.from_dict(json.loads(path.read_text(encoding="utf-8")))


def list_libraries() -> list[Library]:
    out = []
    for path in sorted(libraries_dir().glob("*.json")):
        try:
            out.append(Library.from_dict(json.loads(path.read_text(encoding="utf-8"))))
        except (json.JSONDecodeError, OSError, SpmlError):
            continue
    return sorted(out, key=lambda lib: lib.name.lower())


def delete_library(name: str) -> None:
    path = library_path(name)
    if not path.is_file():
        raise SpmlError(f"No library named {name!r}.")
    path.unlink()
    if active_library() == slugify(name):
        set_active(None)


def rename_library(old: str, new: str) -> Library:
    library = load_library(old)
    was_active = active_library() == slugify(old)
    library_path(old).unlink(missing_ok=True)
    library.name = new
    save_library(library)
    if was_active:
        set_active(new)
    return library


# -------------------------------------------------------------------- active state


def _active_file() -> Path:
    return state_dir() / "active.json"


def active_library() -> str | None:
    """Slug of the library last applied to the game, if any."""
    path = _active_file()
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("active")
    except (json.JSONDecodeError, OSError):
        return None


def set_active(name: str | None) -> None:
    payload = {"active": slugify(name) if name else None, "updated": _now()}
    _active_file().write_text(json.dumps(payload, indent=2), encoding="utf-8")


def active() -> Library | None:
    """The library edits apply to.

    With nothing recorded but exactly one library on disk, that one is obviously it -
    adopting it beats inventing a second library beside it.
    """
    slug = active_library()
    if not slug:
        existing = list_libraries()
        if len(existing) == 1:
            set_active(existing[0].name)
            return existing[0]
        return None
    try:
        return load_library(slug)
    except SpmlError:
        return None


# ---------------------------------------------------------------------- operations


def library_from_entries(name: str, entries: list[Entry], game_version: str | None = None,
                         notes: str = "") -> Library:
    # Copy each entry: libraries must never share mutable state with the list they
    # were seeded from, or editing a copy would silently edit its source.
    mods = [Entry(e.id, e.enabled) for e in entries]
    return Library(name=name, mods=mods, game_version=game_version, notes=notes)


def diff_against(library: Library, live: list[Entry]) -> dict[str, list[str]]:
    """Compare a library with the game's current load order.

    The game's own mod menu writes the same file, so a library can drift out of date;
    this is what tells the user to sync rather than silently overwriting their changes.
    """
    lib_ids = [e.id for e in library.mods]
    live_ids = [e.id for e in live]
    lib_state = {e.id: e.enabled for e in library.mods}
    live_state = {e.id: e.enabled for e in live}
    shared_lib = [i for i in lib_ids if i in live_state]
    shared_live = [i for i in live_ids if i in lib_state]
    return {
        "added_in_game": [i for i in live_ids if i not in lib_state],
        "removed_in_game": [i for i in lib_ids if i not in live_state],
        "toggled": [i for i in shared_lib if lib_state[i] != live_state[i]],
        "reordered": ["order"] if shared_lib != shared_live else [],
    }


def is_in_sync(library: Library, live: list[Entry]) -> bool:
    return not any(diff_against(library, live).values())
