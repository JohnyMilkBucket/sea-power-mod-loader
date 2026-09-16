"""Locate Steam / Sea Power, discover installed mods, read and write the game's load order.

Sea Power has a native mod system: mods are folders (Steam Workshop items or local
folders under StreamingAssets) each carrying an `_info.ini`, and the active set plus
its order lives in the `[LoadOrder]` section of `usersettings.ini`:

    [LoadOrder]
    NumberOfModFiles=7
    Mod1Directory=3380210757,True
    Mod2Directory=ACConfigs,False

Lower index = loaded earlier = higher priority (the base game `original` folder is
always loaded last). This module drives that file; it never touches game assets.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

APP_ID = 1286220
GAME_DIR_NAME = "Sea Power"
PUBLISHER = "Triassic Games"
ANCHOR_CHAIN_ID = "3380210757"

# Folders under StreamingAssets that are engine data, not mods.
RESERVED_DATA_DIRS = {"original", "user", "EntityScenes"}


class SpmlError(Exception):
    """Anything the user should see as a clean error message rather than a traceback."""


# --------------------------------------------------------------------------- paths


def steam_root() -> Path:
    """Find the Steam installation, preferring the registry over guesses."""
    try:
        import winreg

        for hive, key in (
            (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
        ):
            try:
                with winreg.OpenKey(hive, key) as k:
                    value = winreg.QueryValueEx(k, "SteamPath" if hive == winreg.HKEY_CURRENT_USER else "InstallPath")[0]
                    p = Path(value)
                    if (p / "steamapps").is_dir():
                        return p
            except OSError:
                continue
    except ImportError:
        pass

    for guess in (
        Path(r"C:\Program Files (x86)\Steam"),
        Path(r"C:\Program Files\Steam"),
        Path.home() / "Steam",
    ):
        if (guess / "steamapps").is_dir():
            return guess
    raise SpmlError("Could not find your Steam installation.")


def steam_libraries(root: Path | None = None) -> list[Path]:
    """Every Steam library folder, starting with the main one."""
    root = root or steam_root()
    libraries = [root]
    vdf = root / "steamapps" / "libraryfolders.vdf"
    if vdf.is_file():
        text = vdf.read_text(encoding="utf-8", errors="replace")
        for match in re.finditer(r'"path"\s+"([^"]+)"', text):
            p = Path(match.group(1).replace("\\\\", "\\"))
            if p not in libraries and (p / "steamapps").is_dir():
                libraries.append(p)
    return libraries


def find_game() -> Path:
    """The Sea Power install directory, via the app manifest in any Steam library."""
    for lib in steam_libraries():
        manifest = lib / "steamapps" / f"appmanifest_{APP_ID}.acf"
        if manifest.is_file():
            text = manifest.read_text(encoding="utf-8", errors="replace")
            m = re.search(r'"installdir"\s+"([^"]+)"', text)
            installdir = m.group(1) if m else GAME_DIR_NAME
            path = lib / "steamapps" / "common" / installdir
            if path.is_dir():
                return path
    raise SpmlError(
        f"Sea Power (app {APP_ID}) is not installed in any Steam library.\n"
        "If you moved it, pass --game-dir or set it once with: spml config --game-dir <path>"
    )


def workshop_dir() -> Path | None:
    """Where subscribed Workshop mods are downloaded, if any have been."""
    for lib in steam_libraries():
        path = lib / "steamapps" / "workshop" / "content" / str(APP_ID)
        if path.is_dir():
            return path
    return None


def streaming_assets(game_dir: Path) -> Path:
    path = game_dir / f"{GAME_DIR_NAME}_Data" / "StreamingAssets"
    if not path.is_dir():
        raise SpmlError(f"Game data folder not found under {game_dir}")
    return path


def usersettings_path() -> Path:
    """The game's settings file, which owns the [LoadOrder] section."""
    base = Path(os.environ.get("USERPROFILE", Path.home()))
    return base / "AppData" / "LocalLow" / PUBLISHER / GAME_DIR_NAME / "usersettings.ini"


def game_version(game_dir: Path) -> str | None:
    """Read the current build number off the top of the shipped changelog."""
    changelog = game_dir / "changelog.txt"
    if not changelog.is_file():
        return None
    with changelog.open(encoding="utf-8", errors="replace") as fh:
        for _ in range(60):
            line = fh.readline()
            if not line:
                break
            m = re.search(r":\s*(\d+\.\d+\.\d+)", line)
            if m:
                return m.group(1)
    return None


def game_running() -> bool:
    """True if Sea Power has the settings file open; writing under it would be lost."""
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {GAME_DIR_NAME}.exe", "/NH"],
            capture_output=True, text=True, timeout=15,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return f"{GAME_DIR_NAME}.exe".lower() in out.lower()


def config_path() -> Path:
    return state_dir() / "config.json"


def read_config() -> dict:
    """User settings for the loader itself (currently just a game-directory override)."""
    path = config_path()
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def write_config(data: dict) -> None:
    config_path().write_text(json.dumps(data, indent=2), encoding="utf-8")


def set_game_dir(path: Path | str | None) -> None:
    """Remember where the game is, or clear the override to go back to auto-detection."""
    config = read_config()
    if path is None:
        config.pop("game_dir", None)
    else:
        path = Path(path)
        if not (path / f"{GAME_DIR_NAME}_Data").is_dir():
            raise SpmlError(
                f"That folder does not look like a Sea Power install "
                f"(no '{GAME_DIR_NAME}_Data' inside):\n{path}")
        config["game_dir"] = str(path)
    write_config(config)


def launch_game(game_dir: Path | None = None, direct: bool = False) -> str:
    """Start Sea Power. Returns a short description of how it was launched.

    Going through Steam is the default: launching the executable directly skips
    Steam, which the game needs for Workshop mods and cloud saves.
    """
    if direct:
        game_dir = game_dir or find_game()
        exe = game_dir / f"{GAME_DIR_NAME}.exe"
        if not exe.is_file():
            raise SpmlError(f"Game executable not found: {exe}")
        subprocess.Popen([str(exe)], cwd=str(game_dir), close_fds=True)
        return f"launched {exe.name} directly (Steam features may be unavailable)"

    try:
        subprocess.run(["cmd", "/c", "start", "", f"steam://rungameid/{APP_ID}"],
                       check=True, capture_output=True, timeout=20)
    except (OSError, subprocess.SubprocessError) as exc:
        raise SpmlError(f"Could not ask Steam to launch the game ({exc}). Try --direct.") from exc
    return "asked Steam to launch Sea Power"


def state_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local"))
    path = base / "SeaPowerModLoader"
    (path / "backups").mkdir(parents=True, exist_ok=True)
    return path


# ----------------------------------------------------------------------- ini files

# `_info.ini` descriptions are free-form BBCode, so lines like "[h1]" and "[list]"
# look exactly like section headers. Only these are real sections.
INFO_SECTION_RE = re.compile(r"^\[(Language_[A-Za-z]{2}|Compatibility)\]\s*$")


def parse_info_ini(path: Path) -> dict:
    """Parse a mod's `_info.ini` into {'names': {lang: str}, 'descriptions': {...}, 'compat': {...}}."""
    result: dict = {"names": {}, "descriptions": {}, "compat": {}}
    if not path.is_file():
        return result

    section = None
    description_lang = None
    description_lines: list[str] = []

    def flush() -> None:
        if description_lang and description_lines:
            result["descriptions"][description_lang] = "\n".join(description_lines).strip()

    for raw in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        header = INFO_SECTION_RE.match(raw.strip())
        if header:
            flush()
            description_lang, description_lines = None, []
            section = header.group(1)
            continue

        if section is None:
            continue

        if section.startswith("Language_"):
            lang = section.split("_", 1)[1].lower()
            if raw.startswith("Name="):
                result["names"][lang] = raw[5:].strip()
                continue
            if raw.startswith("Description="):
                flush()
                description_lang, description_lines = lang, [raw[12:].strip()]
                continue
            if description_lang:
                description_lines.append(raw.rstrip())
        elif section == "Compatibility":
            line = raw.strip()
            if not line or line[0] in ";#" or line.startswith("//"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                result["compat"][key.strip()] = value.strip()

    flush()
    return result


def _pick_language(mapping: dict[str, str], fallback: str = "") -> str:
    for lang in ("en", *sorted(mapping)):
        if mapping.get(lang):
            return mapping[lang]
    return fallback


def parse_version(text: str) -> tuple[int, ...] | None:
    m = re.match(r"\s*v?(\d+)\.(\d+)(?:\.(\d+))?", text or "")
    if not m:
        return None
    return tuple(int(g or 0) for g in m.groups())


# ---------------------------------------------------------------------------- mods


@dataclass
class Mod:
    id: str                       # Workshop item id, or local folder name
    source: str                   # "workshop" | "local"
    path: Path
    name: str
    description: str = ""
    compat: dict = field(default_factory=dict)
    has_code: bool = False        # ships a .dll, so it needs the Anchor Chain loader
    empty: bool = False           # folder exists but has no content to load

    @property
    def installed(self) -> bool:
        return self.path.is_dir()

    def compat_status(self, version: str | None) -> tuple[str, str]:
        """Check the mod's [Compatibility] block against the installed game version.

        Returns (status, detail) where status is 'ok', 'unknown', 'warn' or 'bad'.
        """
        if not self.compat:
            return "unknown", "no compatibility info"
        game = parse_version(version or "")
        if not game:
            return "unknown", "game version unknown"

        approx = parse_version(self.compat.get("ApproximateVersion", ""))
        if approx:
            # Documented in the shipped mods as: MAJOR and MINOR must match,
            # a higher PATCH is accepted. It overrides the bounds below.
            if game[:2] == approx[:2] and game[2] >= approx[2]:
                return "ok", f"built for {'.'.join(map(str, approx))}"
            return "bad", f"built for {'.'.join(map(str, approx))}, game is {version}"

        low = parse_version(self.compat.get("GreaterThanEqualToVersion", ""))
        high = parse_version(self.compat.get("LessThanVersion", ""))
        if low and game < low:
            return "bad", f"needs >= {'.'.join(map(str, low))}, game is {version}"
        if high and game >= high:
            return "bad", f"needs < {'.'.join(map(str, high))}, game is {version}"
        if low or high:
            return "ok", "within declared range"
        return "unknown", "no version constraint"


def _load_mod(path: Path, source: str) -> Mod:
    info = parse_info_ini(path / "_info.ini")
    name = _pick_language(info["names"], fallback=path.name)
    description = _pick_language(info["descriptions"]).splitlines()
    empty = not any(path.iterdir()) if path.is_dir() else True
    return Mod(
        id=path.name,
        source=source,
        path=path,
        name=name,
        description=description[0] if description else ("empty folder" if empty else ""),
        compat=info["compat"],
        has_code=any(path.glob("*.dll")),
        empty=empty,
    )


def discover_mods(game_dir: Path) -> dict[str, Mod]:
    """Every mod the game can see: subscribed Workshop items and local data folders."""
    mods: dict[str, Mod] = {}

    workshop = workshop_dir()
    if workshop:
        for child in sorted(workshop.iterdir()):
            if child.is_dir():
                mods[child.name] = _load_mod(child, "workshop")

    # A local mod is any StreamingAssets folder that is not engine data. `_info.ini`
    # is optional here: the game happily lists bare folders (e.g. ACConfigs) in the
    # load order, and hiding them would make the order look wrong.
    for child in sorted(streaming_assets(game_dir).iterdir()):
        if child.is_dir() and child.name not in RESERVED_DATA_DIRS:
            mods[child.name] = _load_mod(child, "local")

    return mods


# ---------------------------------------------------------------------- load order

SECTION_RE = re.compile(r"^\[([^\]]+)\]\s*$")
MOD_ENTRY_RE = re.compile(r"^Mod(\d+)Directory\s*=\s*(.*)$", re.IGNORECASE)


@dataclass
class Entry:
    """One line of the game's load order: a mod id plus whether it is switched on."""
    id: str
    enabled: bool = True


def _read_settings_text(path: Path) -> tuple[str, str]:
    if not path.is_file():
        raise SpmlError(
            f"Game settings file not found:\n  {path}\n"
            "Launch Sea Power once so it writes its settings, then try again."
        )
    raw = path.read_bytes().decode("utf-8-sig", errors="replace")
    newline = "\r\n" if "\r\n" in raw else "\n"
    return raw.replace("\r\n", "\n"), newline


def _find_section(lines: list[str], name: str) -> tuple[int, int] | None:
    """Return (header_index, end_index_exclusive) for a section, or None."""
    start = None
    for i, line in enumerate(lines):
        match = SECTION_RE.match(line.strip())
        if match:
            if start is not None:
                return start, i
            if match.group(1).lower() == name.lower():
                start = i
    return (start, len(lines)) if start is not None else None


def read_load_order(settings: Path | None = None) -> list[Entry]:
    """The active load order, in the order the game applies it."""
    settings = settings or usersettings_path()
    text, _ = _read_settings_text(settings)
    lines = text.split("\n")
    span = _find_section(lines, "LoadOrder")
    if not span:
        return []

    numbered: list[tuple[int, Entry]] = []
    for line in lines[span[0] + 1 : span[1]]:
        match = MOD_ENTRY_RE.match(line.strip())
        if not match:
            continue
        index, value = int(match.group(1)), match.group(2).strip()
        mod_id, _, flag = value.rpartition(",")
        if not mod_id:                      # no comma: bare id, treat as enabled
            mod_id, flag = value, "True"
        numbered.append((index, Entry(mod_id.strip(), flag.strip().lower() == "true")))

    return [entry for _, entry in sorted(numbered, key=lambda pair: pair[0])]


def backup_settings(settings: Path | None = None, keep: int = 20) -> Path | None:
    """Snapshot usersettings.ini before we touch it, keeping the last few."""
    settings = settings or usersettings_path()
    if not settings.is_file():
        return None
    backups = state_dir() / "backups"
    target = backups / f"usersettings-{time.strftime('%Y%m%d-%H%M%S')}.ini"
    shutil.copy2(settings, target)
    for old in sorted(backups.glob("usersettings-*.ini"))[:-keep]:
        old.unlink(missing_ok=True)
    return target


def write_load_order(entries: list[Entry], settings: Path | None = None, force: bool = False) -> Path | None:
    """Rewrite the [LoadOrder] section, leaving every other setting byte-identical."""
    settings = settings or usersettings_path()
    if not force and game_running():
        raise SpmlError(
            "Sea Power is running. It rewrites usersettings.ini when it exits, which would\n"
            "discard these changes. Close the game first (or pass --force to write anyway)."
        )

    text, newline = _read_settings_text(settings)
    lines = text.split("\n")

    block = [f"NumberOfModFiles={len(entries)}"]
    block += [f"Mod{i}Directory={e.id},{'True' if e.enabled else 'False'}" for i, e in enumerate(entries, 1)]

    span = _find_section(lines, "LoadOrder")
    if span:
        start, end = span
        # Keep any unrelated keys a future patch might add to this section.
        preserved = [
            line for line in lines[start + 1 : end]
            if line.strip()
            and not MOD_ENTRY_RE.match(line.strip())
            and not line.strip().lower().startswith("numberofmodfiles")
        ]
        lines[start : end] = ["[LoadOrder]", *block, *preserved, ""]
    else:
        if lines and lines[-1].strip():
            lines.append("")
        lines += ["[LoadOrder]", *block, ""]

    backup = backup_settings(settings)
    payload = newline.join(lines)
    tmp = settings.with_suffix(".ini.spml-tmp")
    tmp.write_bytes(payload.encode("utf-8"))
    os.replace(tmp, settings)
    return backup


def resolve_order(entries: list[Entry], mods: dict[str, Mod]) -> list[Mod | None]:
    """Pair load-order entries with discovered mods; None means installed-but-missing."""
    return [mods.get(entry.id) for entry in entries]
