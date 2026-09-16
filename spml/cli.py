"""Command line interface for the Sea Power mod loader."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import core, library, pack, share
from .core import Entry, Mod, SpmlError, config_path, read_config

CHECK_ON, CHECK_OFF = "[x]", "[ ]"


# ----------------------------------------------------------------------- plumbing


class Context:
    """Everything a command needs: where the game is, what is installed, what is active."""

    def __init__(self, game_dir: str | None = None) -> None:
        override = game_dir or read_config().get("game_dir")
        if override:
            path = Path(override)
            if not path.is_dir():
                raise SpmlError(f"Configured game directory does not exist: {path}")
            self.game_dir = path
        else:
            self.game_dir = core.find_game()

        self.settings = core.usersettings_path()
        self.version = core.game_version(self.game_dir)
        self.mods: dict[str, Mod] = core.discover_mods(self.game_dir)
        self.catalog = library.Catalog()

    def live_order(self) -> list[Entry]:
        return core.read_load_order(self.settings)

    def display_name(self, mod_id: str) -> str:
        mod = self.mods.get(mod_id)
        return mod.name if mod else self.catalog.name_for(mod_id, fallback=mod_id)

    def active_or_create(self) -> library.Library:
        """The active library, seeding one from the game's current order on first use."""
        current = library.active()
        if current:
            return current
        lib = library.library_from_entries(
            "Default", self.live_order(), self.version,
            notes="Created automatically from the load order already set in the game.",
        )
        library.save_library(lib)
        library.set_active(lib.name)
        print(f"No active library, so one was created from your current game setup: {lib.name!r}\n")
        return lib


# ------------------------------------------------------------------------ printing


def status_marker(status: str) -> str:
    return {"ok": "ok", "bad": "MISMATCH", "warn": "warn", "unknown": "-"}.get(status, status)


def print_entries(ctx: Context, entries: list[Entry], show_compat: bool = True) -> None:
    if not entries:
        print("  (no mods in this list)")
        return
    width = max((len(ctx.display_name(e.id)) for e in entries), default=20)
    width = min(max(width, 20), 48)
    for i, entry in enumerate(entries, 1):
        mod = ctx.mods.get(entry.id)
        name = ctx.display_name(entry.id)[:width]
        mark = CHECK_ON if entry.enabled else CHECK_OFF
        if mod is None:
            detail = "NOT INSTALLED"
        elif show_compat:
            status, note = mod.compat_status(ctx.version)
            detail = f"{mod.source:<8}  {status_marker(status)}"
            if status == "bad":
                detail += f" ({note})"
        else:
            detail = mod.source
        code = " *code" if mod and mod.has_code else ""
        print(f"  {i:>2}  {mark}  {name:<{width}}  {detail}{code}")


def warn_if_out_of_sync(ctx: Context, lib: library.Library) -> None:
    diff = library.diff_against(lib, ctx.live_order())
    if not any(diff.values()):
        return
    print("\n  ! The game's current load order differs from this library:")
    for key, label in (
        ("added_in_game", "added in game"),
        ("removed_in_game", "missing in game"),
        ("toggled", "toggled in game"),
    ):
        if diff[key]:
            names = ", ".join(ctx.display_name(i) for i in diff[key])
            print(f"      {label}: {names}")
    if diff["reordered"]:
        print("      order differs")
    print("    Run 'spml library sync' to pull those changes in, or 'spml apply' to overwrite them.")


# ----------------------------------------------------------------------- selectors


def select(ctx: Context, entries: list[Entry], token: str) -> int:
    """Resolve a user's mod reference to an index in `entries`.

    Accepts a position number, an exact mod id, or a unique name substring.
    """
    token = token.strip()
    if token.isdigit() and 1 <= int(token) <= len(entries):
        return int(token) - 1
    for i, entry in enumerate(entries):
        if entry.id.lower() == token.lower():
            return i
    matches = [i for i, e in enumerate(entries) if token.lower() in ctx.display_name(e.id).lower()]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise SpmlError(f"No mod in this library matches {token!r}.")
    names = ", ".join(ctx.display_name(entries[i].id) for i in matches)
    raise SpmlError(f"{token!r} matches several mods: {names}. Be more specific or use the number.")


def select_installed(ctx: Context, token: str) -> Mod:
    token = token.strip()
    if token in ctx.mods:
        return ctx.mods[token]
    matches = [m for m in ctx.mods.values() if token.lower() in m.name.lower()]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise SpmlError(f"No installed mod matches {token!r}. Run 'spml scan' to refresh.")
    raise SpmlError(f"{token!r} matches several mods: " + ", ".join(m.name for m in matches))


# ------------------------------------------------------------------------ commands


def cmd_status(ctx: Context, args: argparse.Namespace) -> int:
    live = ctx.live_order()
    print(f"Game        {ctx.game_dir}")
    print(f"Version     {ctx.version or 'unknown'}")
    print(f"Settings    {ctx.settings}")
    print(f"Installed   {len(ctx.mods)} mods ({sum(1 for m in ctx.mods.values() if m.source == 'workshop')} workshop, "
          f"{sum(1 for m in ctx.mods.values() if m.source == 'local')} local)")
    print(f"Running     {'yes - close it before applying changes' if core.game_running() else 'no'}")

    lib = library.active()
    print(f"Library     {lib.name if lib else 'none active'}"
          + (f"  ({lib.enabled_count}/{len(lib.mods)} enabled)" if lib else ""))
    print(f"\nCurrent load order in game ({sum(1 for e in live if e.enabled)}/{len(live)} enabled):")
    print_entries(ctx, live)
    if lib:
        warn_if_out_of_sync(ctx, lib)
    return 0


def cmd_scan(ctx: Context, args: argparse.Namespace) -> int:
    """Find installed mods and record them in the catalog."""
    new_ids = ctx.catalog.merge(ctx.mods)
    ctx.catalog.save()

    print(f"Scanned {ctx.game_dir.name}: {len(ctx.mods)} mods installed, "
          f"{len(ctx.catalog.entries)} known to the catalog.")
    if new_ids:
        print(f"\nNew since the last scan ({len(new_ids)}):")
        for mod_id in new_ids:
            mod = ctx.mods[mod_id]
            print(f"  + {mod.name}  [{mod.source} {mod_id}]")
    else:
        print("\nNothing new since the last scan.")

    if args.add:
        lib = ctx.active_or_create()
        known = {e.id for e in lib.mods}
        added = [m for m in ctx.mods.values() if m.id not in known]
        if not added:
            print(f"\nLibrary {lib.name!r} already lists every installed mod.")
            return 0
        lib.mods += [Entry(m.id, enabled=False) for m in added]
        library.save_library(lib)
        print(f"\nAdded {len(added)} mod(s) to library {lib.name!r}, switched off:")
        for mod in added:
            print(f"  + {mod.name}")
        print("Turn them on with: spml enable <name>")
    elif new_ids:
        print("\nAdd them to your active library with: spml scan --add")
    return 0


def cmd_mods(ctx: Context, args: argparse.Namespace) -> int:
    """List every mod the loader knows about, installed or merely remembered."""
    lib = library.active()
    in_library = {e.id: e for e in (lib.mods if lib else [])}

    rows = []
    for mod_id, mod in sorted(ctx.mods.items(), key=lambda kv: kv[1].name.lower()):
        rows.append((mod.name, mod.source, mod_id, True, in_library.get(mod_id), mod))
    if args.all:
        for mod_id, record in sorted(ctx.catalog.entries.items(), key=lambda kv: (kv[1].get("name") or "").lower()):
            if mod_id not in ctx.mods:
                rows.append((record.get("name") or mod_id, record.get("source", "?"), mod_id,
                             False, in_library.get(mod_id), None))

    if not rows:
        print("No mods found. Subscribe to some on the Steam Workshop, then run 'spml scan'.")
        return 0

    width = min(max((len(r[0]) for r in rows), default=20), 48)
    print(f"{'MOD':<{width}}  {'SOURCE':<9} {'IN LIBRARY':<11} {'COMPAT':<9} ID")
    for name, source, mod_id, installed, entry, mod in rows:
        if entry is None:
            state = "-"
        else:
            state = "enabled" if entry.enabled else "disabled"
        compat = status_marker(mod.compat_status(ctx.version)[0]) if mod else "not inst."
        flag = " *code" if (mod and mod.has_code) else ""
        print(f"{name[:width]:<{width}}  {source:<9} {state:<11} {compat:<9} {mod_id}{flag}")

    if not args.all and len(ctx.catalog.entries) > len(ctx.mods):
        extra = len(ctx.catalog.entries) - len(ctx.mods)
        print(f"\n{extra} more mod(s) in the catalog are not installed right now - see them with 'spml mods --all'.")
    return 0


def cmd_library(ctx: Context, args: argparse.Namespace) -> int:
    action = args.action

    if action == "list":
        libs = library.list_libraries()
        if not libs:
            print("No libraries yet. Capture your current setup with:\n  spml library new \"My setup\" --from-game")
            return 0
        current = library.active_library()
        for lib in libs:
            mark = "*" if lib.slug == current else " "
            print(f" {mark} {lib.name:<28} {lib.enabled_count:>2}/{len(lib.mods):<3} mods   "
                  f"game {lib.game_version or '?':<7} updated {lib.updated[:10]}")
        print("\n* = active. Switch with: spml library use <name>")
        return 0

    if action == "new":
        if library.library_path(args.name).exists() and not args.force:
            raise SpmlError(f"A library named {args.name!r} already exists. Pass --force to replace it.")
        if args.copy:
            source = library.load_library(args.copy)
            entries = source.mods
        elif args.empty:
            entries = []
        elif args.all:
            entries = [Entry(m.id, enabled=False) for m in ctx.mods.values()]
        else:
            entries = ctx.live_order()
        lib = library.library_from_entries(args.name, entries, ctx.version, notes=args.notes or "")
        library.save_library(lib)
        print(f"Created library {lib.name!r} with {len(lib.mods)} mod(s), {lib.enabled_count} enabled.")
        if library.active() is None:
            # First library: make it the one edits apply to, so the next command
            # does not silently invent a "Default" alongside it.
            library.set_active(lib.name)
            print("It is now your active library.")
        if args.use:
            return activate(ctx, lib, force=args.force_write)
        print(f"Activate it with: spml library use \"{lib.name}\"")
        return 0

    if action == "show":
        lib = library.load_library(args.name) if args.name else ctx.active_or_create()
        print(f"{lib.name}   ({lib.enabled_count}/{len(lib.mods)} enabled)")
        if lib.notes:
            print(f"  {lib.notes}")
        print(f"  built against game {lib.game_version or 'unknown'}, updated {lib.updated[:10]}\n")
        print_entries(ctx, lib.mods)
        warn_if_out_of_sync(ctx, lib)
        return 0

    if action == "use":
        lib = library.load_library(args.name)
        return activate(ctx, lib, force=args.force_write)

    if action == "sync":
        lib = library.load_library(args.name) if args.name else ctx.active_or_create()
        live = ctx.live_order()
        if library.is_in_sync(lib, live):
            print(f"Library {lib.name!r} already matches the game.")
            return 0
        lib.mods = live
        lib.game_version = ctx.version
        library.save_library(lib)
        print(f"Pulled the game's current load order into library {lib.name!r}:")
        print_entries(ctx, lib.mods)
        return 0

    if action == "rename":
        lib = library.rename_library(args.name, args.new_name)
        print(f"Renamed to {lib.name!r}.")
        return 0

    if action == "delete":
        library.delete_library(args.name)
        print(f"Deleted library {args.name!r}. The mods themselves are untouched.")
        return 0

    raise SpmlError(f"Unknown library action {action!r}.")


def activate(ctx: Context, lib: library.Library, force: bool = False) -> int:
    """Write a library's mod set into the game's load order."""
    missing = [e.id for e in lib.mods if e.id not in ctx.mods and e.enabled]
    entries = [e for e in lib.mods if e.id in ctx.mods]
    dropped = [e.id for e in lib.mods if e.id not in ctx.mods]

    backup = core.write_load_order(entries, ctx.settings, force=force)
    library.set_active(lib.name)

    print(f"Activated library {lib.name!r}: {sum(1 for e in entries if e.enabled)} of {len(entries)} mods enabled.")
    if dropped:
        print(f"\nSkipped {len(dropped)} mod(s) that are not installed:")
        for mod_id in dropped:
            note = "  <- enabled in this library" if mod_id in missing else ""
            print(f"  - {ctx.display_name(mod_id)} [{mod_id}]{note}")
        print("Subscribe on the Workshop, then: spml scan && spml library use \"%s\"" % lib.name)
    if backup:
        print(f"\nSettings backed up to {backup}")
    print("\nRestart Sea Power for the change to take effect.")
    return 0


def cmd_apply(ctx: Context, args: argparse.Namespace) -> int:
    return activate(ctx, ctx.active_or_create(), force=args.force_write)


def _edit(ctx: Context, args: argparse.Namespace, mutate) -> int:
    lib = ctx.active_or_create()
    mutate(lib)
    library.save_library(lib)
    print(f"Library {lib.name!r} ({lib.enabled_count}/{len(lib.mods)} enabled):")
    print_entries(ctx, lib.mods)
    if args.apply:
        print()
        return activate(ctx, lib, force=args.force_write)
    print("\nNot yet applied to the game. Run 'spml apply' when you are done editing.")
    return 0


def cmd_toggle(ctx: Context, args: argparse.Namespace) -> int:
    want = args.command == "enable"

    def mutate(lib: library.Library) -> None:
        for token in args.mods:
            try:
                index = select(ctx, lib.mods, token)
            except SpmlError:
                if not want:
                    raise
                mod = select_installed(ctx, token)      # enabling something not yet listed
                lib.mods.append(Entry(mod.id, True))
                print(f"Added {mod.name!r} to the library and enabled it.")
                continue
            lib.mods[index].enabled = want

    return _edit(ctx, args, mutate)


def cmd_add(ctx: Context, args: argparse.Namespace) -> int:
    def mutate(lib: library.Library) -> None:
        known = {e.id for e in lib.mods}
        for token in args.mods:
            mod = select_installed(ctx, token)
            if mod.id in known:
                raise SpmlError(f"{mod.name!r} is already in this library.")
            lib.mods.append(Entry(mod.id, enabled=not args.off))
    return _edit(ctx, args, mutate)


def cmd_remove(ctx: Context, args: argparse.Namespace) -> int:
    def mutate(lib: library.Library) -> None:
        for token in args.mods:
            index = select(ctx, lib.mods, token)
            lib.mods.pop(index)
    return _edit(ctx, args, mutate)


def cmd_move(ctx: Context, args: argparse.Namespace) -> int:
    def mutate(lib: library.Library) -> None:
        index = select(ctx, lib.mods, args.mod)
        entry = lib.mods.pop(index)
        target = max(1, min(args.position, len(lib.mods) + 1)) - 1
        lib.mods.insert(target, entry)
    return _edit(ctx, args, mutate)


def cmd_check(ctx: Context, args: argparse.Namespace) -> int:
    """Flag version mismatches and code mods left without their loader."""
    lib = library.active()
    entries = lib.mods if lib else ctx.live_order()
    scope = f"library {lib.name!r}" if lib else "the game's current load order"
    problems = 0

    print(f"Checking {scope} against game version {ctx.version or 'unknown'}.\n")
    for entry in entries:
        if not entry.enabled:
            continue
        mod = ctx.mods.get(entry.id)
        if mod is None:
            print(f"  MISSING   {ctx.display_name(entry.id)} [{entry.id}] is enabled but not installed")
            problems += 1
            continue
        status, note = mod.compat_status(ctx.version)
        if status == "bad":
            print(f"  MISMATCH  {mod.name}: {note}")
            problems += 1

    code_mods = [e for e in entries if e.enabled and (m := ctx.mods.get(e.id)) and m.has_code]
    anchor = next((e for e in entries if e.id == core.ANCHOR_CHAIN_ID), None)
    if code_mods and (anchor is None or not anchor.enabled):
        names = ", ".join(ctx.display_name(e.id) for e in code_mods if e.id != core.ANCHOR_CHAIN_ID)
        if names:
            print(f"  LOADER    {names} ship code (.dll) but Anchor Chain is not enabled - they will not load")
            problems += 1
    elif code_mods and anchor and entries.index(anchor) != 0:
        print("  ORDER     Anchor Chain is usually loaded first; it is currently "
              f"at position {entries.index(anchor) + 1}")

    if not problems:
        print("  No problems found.")
    else:
        print(f"\n{problems} problem(s) found.")
    print("\nNote: compatibility comes from each mod's own [Compatibility] block; mods that")
    print("declare nothing are not checked, and a mismatch is a warning, not a hard block.")
    return 1 if problems else 0


def cmd_export(ctx: Context, args: argparse.Namespace) -> int:
    """Write a shareable mod list, as a file, a code, or both."""
    if args.library:
        lib = library.load_library(args.library)
        entries, name = lib.mods, lib.name
    elif args.from_game:
        entries, name = ctx.live_order(), "Current game setup"
    else:
        lib = ctx.active_or_create()
        entries, name = lib.mods, lib.name

    if args.enabled_only:
        entries = [e for e in entries if e.enabled]
    payload = share.build_list(entries, ctx.mods, name=args.name or name, game_version=ctx.version)
    for item in payload["mods"]:                      # keep names for mods not installed here
        if not item["name"]:
            item["name"] = ctx.catalog.name_for(item["id"], fallback="")

    if args.pack is not None:
        out = Path(args.pack) if args.pack else Path.cwd() / f"{library.slugify(payload['name'])}{pack.PACK_SUFFIX}"
        path, items = pack.build_pack(
            payload, ctx.mods, out, include_workshop=args.include_workshop,
            progress=lambda i, n, name: print(f"  packing {i}/{n}: {name}"))
        total = sum(i.size for i in items if i.bundled)
        print(f"\nPack written to {path}  ({pack.human_size(path.stat().st_size)} on disk, "
              f"{pack.human_size(total)} of mod files)")
        left_out = [i for i in items if not i.bundled]
        if left_out:
            print(f"\nListed but not bundled ({len(left_out)}):")
            for item in left_out:
                print(f"  - {item.mod.name}: {item.reason}")
            if not args.include_workshop and any(i.mod.source == "workshop" for i in left_out):
                print("\nWorkshop mods are listed by id so the recipient can subscribe. Bundling their")
                print("files instead means redistributing the authors' work, which the Workshop terms")
                print("generally do not allow - pass --include-workshop only if you have the right to.")
        print(f"\nThey install it with:  spml import \"{path.name}\"")
        return 0

    code = share.encode_code(payload, include_names=not args.short)
    if args.out or not args.code_only:
        out = Path(args.out) if args.out else Path.cwd() / f"{library.slugify(payload['name'])}.spml.json"
        share.write_list(payload, out)
        print(f"Mod list written to {out}")
    print(f"\n{len(payload['mods'])} mod(s). Share code (send this to anyone):\n")
    print(code)
    print("\nThey import it with:  spml import <code>")
    if args.urls:
        print("\nWorkshop links:")
        for item in payload["mods"]:
            if item["id"].isdigit():
                print(f"  {item['name'] or item['id']}: {share.workshop_url(item['id'])}")
    return 0


def cmd_import(ctx: Context, args: argparse.Namespace) -> int:
    """Take someone else's mod list and turn it into a library here."""
    if pack.is_pack(args.source):
        return import_pack(ctx, args)

    payload = share.read_list(args.source)
    present, missing = share.plan_import(payload, ctx.mods)

    print(f"Mod list {payload['name']!r}"
          + (f" (built for game {payload['game_version']})" if payload.get("game_version") else ""))
    if payload.get("game_version") and ctx.version and payload["game_version"] != ctx.version:
        print(f"  Note: your game is {ctx.version}.")
    print(f"  {len(payload['mods'])} mod(s): {len(present)} installed, {len(missing)} missing.\n")

    for item in payload["mods"]:
        mark = CHECK_ON if item.get("enabled", True) else CHECK_OFF
        here = "" if item["id"] in ctx.mods else "   <- not installed"
        print(f"  {item['order']:>2}  {mark}  {item.get('name') or item['id']}{here}")

    if missing:
        print(f"\nMissing {len(missing)} mod(s):")
        for item in missing:
            url = share.workshop_url(item["id"]) if item["id"].isdigit() else "local mod - ask the sender for the folder"
            print(f"  - {item.get('name') or item['id']}: {url}")
        if args.subscribe:
            opened = share.open_workshop_pages([i["id"] for i in missing])
            print(f"\nOpened {opened} Workshop page(s) in Steam - hit Subscribe on each, let them download,")
            print("then run:  spml scan && spml library use \"%s\"" % (args.as_name or payload["name"]))
        else:
            print("\nRe-run with --subscribe to open these in Steam.")

    if args.dry_run:
        print("\nDry run - nothing was saved.")
        return 0

    # Keep missing mods in the library so they slot into place once subscribed.
    entries = [Entry(item["id"], bool(item.get("enabled", True))) for item in payload["mods"]]
    for item in payload["mods"]:
        if item["id"] not in ctx.catalog.entries and item.get("name"):
            ctx.catalog.entries[item["id"]] = {"name": item["name"], "source": item.get("source", "workshop"),
                                               "description": "", "has_code": False, "imported": True}
    ctx.catalog.save()

    name = args.as_name or payload["name"]
    if library.library_path(name).exists() and not args.force:
        raise SpmlError(f"A library named {name!r} already exists. Pass --force to replace it, or --as <name>.")
    lib = library.library_from_entries(name, entries, payload.get("game_version"),
                                       notes=f"Imported {payload.get('exported', '')}".strip())
    library.save_library(lib)
    print(f"\nSaved as library {lib.name!r}.")

    if args.apply:
        print()
        return activate(ctx, lib, force=args.force_write)
    print(f"Activate it with: spml library use \"{lib.name}\"")
    return 0


def cmd_play(ctx: Context, args: argparse.Namespace) -> int:
    """Make sure the right mods are loaded, then start the game."""
    if core.game_running():
        print("Sea Power is already running.")
        return 0

    lib = library.active()
    if lib and not args.no_apply:
        live = ctx.live_order()
        if library.is_in_sync(lib, live):
            print(f"Library {lib.name!r} is already loaded in the game.")
        else:
            print(f"Applying library {lib.name!r} before launch...")
            entries = [e for e in lib.mods if e.id in ctx.mods]
            core.write_load_order(entries, ctx.settings, force=args.force_write)
            library.set_active(lib.name)
            dropped = [e.id for e in lib.mods if e.id not in ctx.mods]
            if dropped:
                print("  Skipped (not installed): " + ", ".join(ctx.display_name(i) for i in dropped))
            print(f"  {sum(1 for e in entries if e.enabled)} of {len(entries)} mods enabled.")

    print(core.launch_game(ctx.game_dir, direct=args.direct).capitalize() + ".")
    return 0


def import_pack(ctx: Context, args: argparse.Namespace) -> int:
    """Unpack a mod pack: install the bundled folders, then build a library from it."""
    payload = pack.read_pack(args.source)
    info = payload.get("pack", {})
    bundled = set(info.get("bundled", []))

    print(f"Mod pack {payload['name']!r}"
          + (f" (built for game {payload['game_version']})" if payload.get("game_version") else ""))
    print(f"  {len(payload['mods'])} mod(s) listed, {len(bundled)} bundled in the file.\n")
    for item in payload["mods"]:
        mark = CHECK_ON if item.get("enabled", True) else CHECK_OFF
        if item["id"] in bundled:
            where = "bundled" if item["id"] not in ctx.mods else "bundled (already installed)"
        else:
            where = "installed" if item["id"] in ctx.mods else "NOT INSTALLED - subscribe on the Workshop"
        print(f"  {item['order']:>2}  {mark}  {item.get('name') or item['id']}   [{where}]")

    if args.dry_run:
        print("\nDry run - nothing was installed.")
        return 0

    id_map, skipped, not_bundled = pack.install_pack(
        args.source, ctx.game_dir, ctx.mods, overwrite=args.overwrite,
        progress=lambda i, n, name: print(f"  installing {i}/{n}: {name}"))

    if id_map:
        print(f"\nInstalled {len(id_map)} mod(s) into the game's StreamingAssets folder:")
        for mod_id, folder in id_map.items():
            print(f"  + {folder}")
    if skipped:
        print(f"\nAlready installed, left alone ({len(skipped)}): "
              + ", ".join(info.get("names", {}).get(i, i) for i in skipped))
        print("  (pass --overwrite to replace them with the pack's copies)")

    ctx.mods = core.discover_mods(ctx.game_dir)
    ctx.catalog.merge(ctx.mods)
    ctx.catalog.save()

    entries = pack.remap_entries(payload, id_map)
    still_missing = [e.id for e in entries if e.id not in ctx.mods]
    if still_missing:
        print(f"\nStill missing {len(still_missing)} mod(s) that were listed but not bundled:")
        for mod_id in still_missing:
            name = info.get("names", {}).get(mod_id, mod_id)
            url = share.workshop_url(mod_id) if mod_id.isdigit() else "ask the sender for this folder"
            print(f"  - {name}: {url}")
        if args.subscribe:
            print(f"\nOpened {share.open_workshop_pages(still_missing)} Workshop page(s) in Steam.")

    name = args.as_name or payload["name"]
    if library.library_path(name).exists() and not args.force:
        raise SpmlError(f"A library named {name!r} already exists. Pass --force to replace it, or --as <name>.")
    lib = library.library_from_entries(name, entries, payload.get("game_version"), notes="Imported from a mod pack")
    library.save_library(lib)
    print(f"\nSaved as library {lib.name!r}.")

    if args.apply:
        print()
        return activate(ctx, lib, force=args.force_write)
    print(f"Activate it with: spml library use \"{lib.name}\"")
    return 0


def cmd_config(ctx: Context | None, args: argparse.Namespace) -> int:
    if args.game_dir_set:
        core.set_game_dir(args.game_dir_set)
        print(f"Game directory set to {args.game_dir_set}")
    if args.clear:
        core.set_game_dir(None)
        print("Game directory override cleared; auto-detection will be used.")
    config = read_config()
    if not args.game_dir_set and not args.clear:
        print(f"Config file   {config_path()}")
        print(f"State folder  {core.state_dir()}")
        print(f"Game dir      {config.get('game_dir') or '(auto-detected)'}")
    return 0


def cmd_gui(ctx: Context, args: argparse.Namespace) -> int:
    from .gui import run
    return run(ctx)


# -------------------------------------------------------------------------- parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="spml",
        description="Sea Power mod loader - switchable mod libraries, sharing and compatibility checks.",
    )
    parser.add_argument("--game-dir", help="path to the Sea Power install (overrides auto-detection)")
    sub = parser.add_subparsers(dest="command", required=True)

    def with_force(p: argparse.ArgumentParser) -> argparse.ArgumentParser:
        p.add_argument("--force-write", action="store_true",
                       help="write the load order even if the game is running")
        return p

    p = sub.add_parser("status", help="show the game, the active library and the live load order")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("scan", help="find installed mods and record them in the catalog")
    p.add_argument("--add", action="store_true", help="also add newly found mods to the active library (switched off)")
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("mods", help="list known mods")
    p.add_argument("--all", action="store_true", help="include catalog mods that are not installed now")
    p.set_defaults(func=cmd_mods)

    p = sub.add_parser("library", help="create and switch between mod sets")
    lib_sub = p.add_subparsers(dest="action", required=True)

    lib_sub.add_parser("list", help="list your libraries").set_defaults(func=cmd_library)

    q = lib_sub.add_parser("new", help="create a library")
    q.add_argument("name")
    q.add_argument("--from-game", action="store_true", help="seed from the game's current load order (default)")
    q.add_argument("--all", action="store_true", help="seed with every installed mod, switched off")
    q.add_argument("--empty", action="store_true", help="seed with nothing")
    q.add_argument("--copy", metavar="LIBRARY", help="seed by copying another library")
    q.add_argument("--notes", help="a note about what this set is for")
    q.add_argument("--use", action="store_true", help="activate it immediately")
    q.add_argument("--force", action="store_true", help="overwrite an existing library of the same name")
    with_force(q).set_defaults(func=cmd_library)

    q = lib_sub.add_parser("show", help="show a library's mods")
    q.add_argument("name", nargs="?")
    q.set_defaults(func=cmd_library)

    q = lib_sub.add_parser("use", help="activate a library and write it to the game")
    q.add_argument("name")
    with_force(q).set_defaults(func=cmd_library)

    q = lib_sub.add_parser("sync", help="pull the game's current load order back into a library")
    q.add_argument("name", nargs="?")
    q.set_defaults(func=cmd_library)

    q = lib_sub.add_parser("rename", help="rename a library")
    q.add_argument("name")
    q.add_argument("new_name")
    q.set_defaults(func=cmd_library)

    q = lib_sub.add_parser("delete", help="delete a library (mods are not touched)")
    q.add_argument("name")
    q.set_defaults(func=cmd_library)

    p = with_force(sub.add_parser("apply", help="write the active library to the game"))
    p.set_defaults(func=cmd_apply)

    for verb, helptext in (("enable", "switch mods on"), ("disable", "switch mods off")):
        p = sub.add_parser(verb, help=helptext)
        p.add_argument("mods", nargs="+", metavar="MOD", help="position, id, or part of the name")
        p.add_argument("--apply", action="store_true", help="write to the game straight away")
        with_force(p).set_defaults(func=cmd_toggle)

    p = sub.add_parser("add", help="add an installed mod to the active library")
    p.add_argument("mods", nargs="+", metavar="MOD")
    p.add_argument("--off", action="store_true", help="add it switched off")
    p.add_argument("--apply", action="store_true")
    with_force(p).set_defaults(func=cmd_add)

    p = sub.add_parser("remove", help="remove a mod from the active library")
    p.add_argument("mods", nargs="+", metavar="MOD")
    p.add_argument("--apply", action="store_true")
    with_force(p).set_defaults(func=cmd_remove)

    p = sub.add_parser("move", help="change a mod's position in the load order")
    p.add_argument("mod", metavar="MOD")
    p.add_argument("position", type=int, help="new 1-based position")
    p.add_argument("--apply", action="store_true")
    with_force(p).set_defaults(func=cmd_move)

    p = sub.add_parser("check", help="check versions and code-mod requirements")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("export", help="write a shareable mod list and share code")
    p.add_argument("--library", help="export a specific library instead of the active one")
    p.add_argument("--from-game", action="store_true", help="export the game's live load order")
    p.add_argument("--name", help="name to put on the list")
    p.add_argument("--out", help="output file path")
    p.add_argument("--code-only", action="store_true", help="print the share code without writing a file")
    p.add_argument("--short", action="store_true", help="omit mod names to shorten the code")
    p.add_argument("--enabled-only", action="store_true", help="export only switched-on mods")
    p.add_argument("--urls", action="store_true", help="also print Workshop links")
    p.add_argument("--pack", nargs="?", const="", metavar="FILE",
                   help="bundle the mod folders into a shareable pack file")
    p.add_argument("--include-workshop", action="store_true",
                   help="also bundle Workshop mod files (redistribution - see the README)")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("import", help="import a mod list from a share code or file")
    p.add_argument("source", help="share code, .spml.json path, or raw JSON")
    p.add_argument("--as", dest="as_name", help="name for the new library")
    p.add_argument("--subscribe", action="store_true", help="open missing mods in Steam to subscribe")
    p.add_argument("--apply", action="store_true", help="activate it immediately")
    p.add_argument("--dry-run", action="store_true", help="show what would happen, save nothing")
    p.add_argument("--force", action="store_true", help="overwrite an existing library of the same name")
    p.add_argument("--overwrite", action="store_true",
                   help="for packs: replace mods that are already installed")
    with_force(p).set_defaults(func=cmd_import)

    p = sub.add_parser("play", help="apply the active library and launch the game")
    p.add_argument("--no-apply", action="store_true", help="launch without touching the load order")
    p.add_argument("--direct", action="store_true", help="run the exe instead of going through Steam")
    with_force(p).set_defaults(func=cmd_play)

    p = sub.add_parser("config", help="show or set the game directory")
    p.add_argument("--game-dir", dest="game_dir_set", help="set the Sea Power directory")
    p.add_argument("--clear", action="store_true", help="clear the override")
    p.set_defaults(func=cmd_config, needs_game=False)

    p = sub.add_parser("gui", help="open the graphical mod loader")
    p.set_defaults(func=cmd_gui)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        ctx = Context(getattr(args, "game_dir", None)) if getattr(args, "needs_game", True) else None
        return args.func(ctx, args)
    except SpmlError as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
