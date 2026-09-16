"""Mod packs: a whole mod set bundled as one file, mod folders included.

A share code carries only *which* mods to load, so the person receiving it still has
to subscribe to each one. A pack carries the mod folders themselves, which is what you
want for local or private mods, for someone who cannot reach the Workshop, or for
pinning an exact version of a set.

A pack is a zip:

    modlist.json          the same list format as a share code, plus a "pack" section
    mods/<id>/...         the mod folder as it sits on disk

Packing someone else's Workshop mod means redistributing their work, which the Workshop
terms and most mod licences do not allow. Local mods are bundled by default; Workshop
items only when explicitly asked for.
"""
from __future__ import annotations

import json
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .core import Entry, Mod, SpmlError, streaming_assets

PACK_SUFFIX = ".spmlpack"
MANIFEST = "modlist.json"
MOD_ROOT = "mods"


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit in ("B", "KB") else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def folder_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


@dataclass
class PackItem:
    mod: Mod
    size: int
    bundled: bool
    reason: str = ""


def plan_pack(entries: list[Entry], mods: dict[str, Mod], include_workshop: bool = False) -> list[PackItem]:
    """Decide what goes into a pack, and why anything is left out."""
    items = []
    for entry in entries:
        mod = mods.get(entry.id)
        if mod is None:
            continue
        if mod.empty:
            items.append(PackItem(mod, 0, False, "empty folder"))
        elif mod.source == "workshop" and not include_workshop:
            items.append(PackItem(mod, folder_size(mod.path), False, "Workshop mod - listed only"))
        else:
            items.append(PackItem(mod, folder_size(mod.path), True))
    return items


def build_pack(payload: dict, mods: dict[str, Mod], out_path: Path,
               include_workshop: bool = False, progress=None) -> tuple[Path, list[PackItem]]:
    """Write a pack file. `payload` is the same document a share code carries."""
    out_path = Path(out_path)
    if out_path.suffix.lower() not in (PACK_SUFFIX, ".zip"):
        out_path = out_path.with_suffix(PACK_SUFFIX)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    entries = [Entry(item["id"], item.get("enabled", True)) for item in payload["mods"]]
    items = plan_pack(entries, mods, include_workshop)
    bundled = [item for item in items if item.bundled]

    manifest = dict(payload)
    manifest["pack"] = {
        "version": 1,
        "bundled": [item.mod.id for item in bundled],
        "names": {item.mod.id: item.mod.name for item in items},
        "sources": {item.mod.id: item.mod.source for item in items},
    }

    tmp = out_path.with_suffix(out_path.suffix + ".part")
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            zf.writestr(MANIFEST, json.dumps(manifest, indent=2, ensure_ascii=False))
            for index, item in enumerate(bundled, 1):
                if progress:
                    progress(index, len(bundled), item.mod.name)
                root = item.mod.path
                for file in sorted(root.rglob("*")):
                    if file.is_file():
                        zf.write(file, f"{MOD_ROOT}/{item.mod.id}/{file.relative_to(root).as_posix()}")
        tmp.replace(out_path)
    finally:
        tmp.unlink(missing_ok=True)
    return out_path, items


def is_pack(path: str | Path) -> bool:
    path = Path(path)
    if not path.is_file():
        return False
    if path.suffix.lower() not in (PACK_SUFFIX, ".zip"):
        return False
    try:
        with zipfile.ZipFile(path) as zf:
            return MANIFEST in zf.namelist()
    except (zipfile.BadZipFile, OSError):
        return False


def read_pack(path: str | Path) -> dict:
    """The mod list inside a pack, without extracting anything."""
    try:
        with zipfile.ZipFile(path) as zf:
            payload = json.loads(zf.read(MANIFEST).decode("utf-8"))
    except KeyError as exc:
        raise SpmlError(f"{Path(path).name} is a zip but not a mod pack (no {MANIFEST}).") from exc
    except (zipfile.BadZipFile, OSError, json.JSONDecodeError) as exc:
        raise SpmlError(f"Could not read the mod pack ({exc}).") from exc
    if payload.get("format") != "spml-modlist":
        raise SpmlError("That file is not an SPML mod pack.")
    return payload


def _safe_members(zf: zipfile.ZipFile, mod_id: str) -> list[zipfile.ZipInfo]:
    """Members belonging to one mod, rejecting anything that escapes its folder.

    Packs arrive from other people, so absolute paths, drive letters and `..` segments
    are refused outright rather than normalised.
    """
    prefix = f"{MOD_ROOT}/{mod_id}/"
    out = []
    for info in zf.infolist():
        if info.is_dir() or not info.filename.startswith(prefix):
            continue
        relative = info.filename[len(prefix):]
        if not relative:
            continue
        parts = Path(relative.replace("\\", "/")).parts
        if any(part in ("..", "") for part in parts) or Path(relative).is_absolute() or ":" in relative:
            raise SpmlError(f"Refusing to unpack unsafe path in mod pack: {info.filename!r}")
        out.append(info)
    return out


def install_pack(path: str | Path, game_dir: Path, mods: dict[str, Mod],
                 overwrite: bool = False, progress=None) -> tuple[dict[str, str], list[str], list[str]]:
    """Extract a pack's bundled mods as local mods.

    Returns (id_map, skipped_already_installed, not_bundled) where `id_map` maps the
    pack's mod id to the local folder name it now lives in.
    """
    payload = read_pack(path)
    pack_info = payload.get("pack", {})
    bundled = list(pack_info.get("bundled", []))
    names = pack_info.get("names", {})
    target_root = streaming_assets(game_dir)

    id_map: dict[str, str] = {}
    skipped: list[str] = []
    with zipfile.ZipFile(path) as zf:
        for index, mod_id in enumerate(bundled, 1):
            if mod_id in mods and not overwrite:
                # Already installed, most likely via the Workshop: prefer that copy,
                # which keeps Steam able to update it.
                skipped.append(mod_id)
                continue

            folder = _target_folder(target_root, mod_id, names.get(mod_id, mod_id), mods)
            if progress:
                progress(index, len(bundled), names.get(mod_id, mod_id))

            members = _safe_members(zf, mod_id)
            if not members:
                continue
            destination = target_root / folder
            if destination.exists() and overwrite:
                shutil.rmtree(destination)
            for info in members:
                relative = info.filename[len(f"{MOD_ROOT}/{mod_id}/"):]
                out_file = destination / relative
                out_file.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, out_file.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
            id_map[mod_id] = folder

    not_bundled = [item["id"] for item in payload["mods"] if item["id"] not in bundled]
    return id_map, skipped, not_bundled


def _target_folder(root: Path, mod_id: str, name: str, mods: dict[str, Mod]) -> str:
    """Pick a local folder name for an unpacked mod.

    A Workshop id is not reused as a local folder name: the game resolves those against
    the Workshop, so a same-named local folder would be ambiguous. A readable name keyed
    off the mod's title is used instead.
    """
    import re

    base = re.sub(r"[^\w.\- ]+", "", name).strip().replace(" ", "_") or f"mod_{mod_id}"
    base = base[:48]
    candidate, counter = base, 2
    while (candidate in mods and mods[candidate].path.parent != root) or \
            ((root / candidate).exists() and candidate != base):
        candidate = f"{base}_{counter}"
        counter += 1
    return candidate


def remap_entries(payload: dict, id_map: dict[str, str]) -> list[Entry]:
    """Turn a pack's mod list into load-order entries, pointing at unpacked folders."""
    return [
        Entry(id_map.get(item["id"], item["id"]), bool(item.get("enabled", True)))
        for item in payload["mods"]
    ]
