"""Export, import and share mod lists.

A mod list is a small JSON document describing an ordered set of mods. It travels
either as a `.spml.json` file or as a single-line share code that pastes cleanly
into Discord:

    SPML1-eJyrVkrLz1eyUsooKSkottLXLy8v10vOz9UvLi3Wy8wtyC8qUaoFAKZLDB0

Workshop mods are identified by their Steam item id, so a list stays meaningful on
someone else's machine: whatever they are missing can be opened for subscription.
"""
from __future__ import annotations

import base64
import json
import re
import subprocess
import time
import zlib
from pathlib import Path

from .core import APP_ID, Entry, Mod, SpmlError

CODE_PREFIX = "SPML1-"
WORKSHOP_URL = "https://steamcommunity.com/sharedfiles/filedetails/?id={}"


def build_list(entries: list[Entry], mods: dict[str, Mod], name: str = "", game_version: str | None = None) -> dict:
    """Package a load order into the portable list format."""
    return {
        "format": "spml-modlist",
        "version": 1,
        "name": name or "Sea Power mod list",
        "app_id": APP_ID,
        "game_version": game_version,
        "exported": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "mods": [
            {
                "order": i,
                "id": entry.id,
                "enabled": entry.enabled,
                "source": mods[entry.id].source if entry.id in mods else "workshop",
                "name": mods[entry.id].name if entry.id in mods else "",
            }
            for i, entry in enumerate(entries, 1)
        ],
    }


# --------------------------------------------------------------------- share codes


def encode_code(payload: dict, include_names: bool = True) -> str:
    """Compress a list into a single pasteable token."""
    compact = {
        "v": 1,
        "n": payload.get("name", ""),
        "g": payload.get("game_version"),
        "m": [
            [m["id"], 1 if m["enabled"] else 0] + ([m["name"]] if include_names and m.get("name") else [])
            for m in payload["mods"]
        ],
    }
    raw = json.dumps(compact, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return CODE_PREFIX + base64.urlsafe_b64encode(zlib.compress(raw, 9)).decode("ascii").rstrip("=")


def decode_code(text: str) -> dict:
    """Read a share code back, tolerating line breaks picked up from chat clients."""
    token = re.sub(r"\s+", "", text.strip())
    if not token.upper().startswith(CODE_PREFIX):
        raise SpmlError("That does not look like an SPML share code (it should start with SPML1-).")
    token = token[len(CODE_PREFIX):]
    try:
        padded = token + "=" * (-len(token) % 4)
        compact = json.loads(zlib.decompress(base64.urlsafe_b64decode(padded)).decode("utf-8"))
    except Exception as exc:                                   # noqa: BLE001 - user-facing
        raise SpmlError(f"Share code is corrupt or truncated ({exc}).") from exc

    mods = []
    for i, item in enumerate(compact.get("m", []), 1):
        mod_id = str(item[0])
        mods.append({
            "order": i,
            "id": mod_id,
            "enabled": bool(item[1]) if len(item) > 1 else True,
            "name": item[2] if len(item) > 2 else "",
            "source": "workshop" if mod_id.isdigit() else "local",
        })
    return {
        "format": "spml-modlist",
        "version": 1,
        "name": compact.get("n") or "Imported mod list",
        "app_id": APP_ID,
        "game_version": compact.get("g"),
        "mods": mods,
    }


# ------------------------------------------------------------------- read and write


def read_list(source: str) -> dict:
    """Load a list from a share code, a file path, or raw JSON."""
    text = source.strip()
    if text.upper().startswith(CODE_PREFIX):
        return decode_code(text)

    path = Path(text)
    if path.is_file():
        text = path.read_text(encoding="utf-8-sig")
        if text.strip().upper().startswith(CODE_PREFIX):
            return decode_code(text)

    if text.lstrip().startswith("{"):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise SpmlError(f"Could not parse that mod list as JSON ({exc}).") from exc
        if payload.get("format") != "spml-modlist":
            raise SpmlError("That JSON file is not an SPML mod list.")
        return payload

    raise SpmlError(f"Could not read a mod list from {source!r} — expected a share code or a .spml.json file.")


def write_list(payload: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


# ---------------------------------------------------------------------- applying it


def plan_import(payload: dict, mods: dict[str, Mod]) -> tuple[list[Entry], list[dict]]:
    """Split an incoming list into what can be applied now and what is missing."""
    present, missing = [], []
    for item in payload["mods"]:
        entry = Entry(item["id"], bool(item.get("enabled", True)))
        (present if item["id"] in mods else missing).append(entry if item["id"] in mods else item)
    return present, missing


def workshop_url(mod_id: str) -> str:
    return WORKSHOP_URL.format(mod_id)


def open_workshop_pages(ids: list[str]) -> int:
    """Open each missing Workshop item in Steam so the user can hit Subscribe."""
    opened = 0
    for mod_id in ids:
        if not mod_id.isdigit():
            continue
        try:
            subprocess.run(
                ["cmd", "/c", "start", "", f"steam://url/CommunityFilePage/{mod_id}"],
                check=False, capture_output=True, timeout=15,
            )
            opened += 1
        except (OSError, subprocess.SubprocessError):
            pass
    return opened
