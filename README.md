# Sea Power Mod Loader

*A Helios tool.*

One file. Double-click **`SeaPowerModLoader.exe`**.

Switchable mod sets for **Sea Power**, with setups you can send to other people.

Nothing to install, no Python, nothing written into your game folder. Windows
SmartScreen will warn the first time because the app is not code-signed —
*More info* → *Run anyway*.

## What it does

Sea Power already has a mod system: mods are folders (Steam Workshop items, or local
folders under `StreamingAssets`), and the game keeps the active set plus its order in
the `[LoadOrder]` section of `usersettings.ini`. This app drives that file. It does not
patch the game, inject code, or move mod files around, so nothing here can break on a
Steam update or trip file verification.

On top of the in-game mod menu you get:

- **Libraries** — named mod sets you switch between, like CurseForge instances. One for
  multiplayer, one for a campaign, one near-vanilla. Switching rewrites the load order.
- **Sharing** — send a setup as a short code, or as a pack file that carries the mod
  folders themselves. Import someone else's the same way.
- **A catalog** — every mod it has seen you install, so a saved set still shows real
  names for mods you later unsubscribed from.
- **Checks** — flags mods whose declared version does not match your game, and code mods
  (`.dll`) left enabled without Anchor Chain to load them.
- **Play** — applies your set and starts the game through Steam.

## Using it

The window has one list: the mods in the current library, in load order. Position 1
loads first and wins conflicts.

| To do this | Do that |
| --- | --- |
| Turn a mod on or off | double-click it, or select and press Space |
| Change load order | select it, **Move up** / **Move down** |
| Add or remove | **Add mod...** / **Remove** |
| Make a new set | **New...**, then choose to copy the current setup or start empty |
| Switch sets | pick one from **Current library** |
| Push it to the game | **Apply to game** |
| Play | **Apply and play** |

Changes you make are saved to the library immediately, but the game does not see them
until you press **Apply**. If you change mods in the game's own mod menu instead, press
**Sync from game** to pull that back into the library.

**Close Sea Power before applying.** The game rewrites its own settings when it exits,
so anything applied while it is running would be thrown away. The app refuses to write
while the game is open.

## Sending a setup to someone

**Export / share** gives you three options:

| | Carries | Good for |
| --- | --- | --- |
| Share code | the list of mods | pasting into Discord |
| `.spml.json` | the list of mods | attaching as a file |
| `.spmlpack` | the list **and the mod folders** | someone who cannot or will not subscribe |

A share code is one line and looks like `SPML1-eNptj01PhDAQhv...`. The other person
pastes it into **Import list...**, and anything they are missing can be opened on the
Workshop to subscribe. Mods they do not have yet stay in the library, so once they
subscribe and rescan, everything slots into the right position.

A pack is a plain zip holding the mod folders. Unpacked mods install as local mods under
readable names, and anything already installed is left alone so a Workshop copy Steam can
update never gets overwritten.

> Local mods are bundled by default; Workshop mods are only listed, by id. Bundling
> someone else's Workshop mod redistributes their work, which the Workshop terms and most
> mod licences do not allow. The option to include them exists for mods that are yours or
> that you have permission to share.

## Safety

- Only the `[LoadOrder]` section of the game's settings file is ever written. Every other
  setting is preserved exactly.
- That file is backed up before every change, to
  `%LOCALAPPDATA%\SeaPowerModLoader\backups\` (last 20 kept).
- Mod files are never modified, moved or deleted. Deleting a library deletes nothing else.
- Packs from other people are checked before unpacking: a pack that tries to write outside
  its own folder is refused.

## Where things live

| What | Where |
| --- | --- |
| Libraries, catalog, backups | `%LOCALAPPDATA%\SeaPowerModLoader\` |
| Game load order | `%USERPROFILE%\AppData\LocalLow\Triassic Games\Sea Power\usersettings.ini` |
| Workshop mods | `<Steam library>\steamapps\workshop\content\1286220\` |
| Local mods | `<game>\Sea Power_Data\StreamingAssets\` |

The game is found automatically through Steam. If you moved it, use
**File → Change game folder...**

## Notes on load order

Position 1 loads first and wins conflicts; the base game (`original`) always loads last.
The game additionally sorts mods by their Workshop dependencies at startup, so the order
it settles on can differ slightly from what you set here — this app sets your preference
rather than fighting the game's own dependency sort.

Code mods only load through
[Anchor Chain](https://steamcommunity.com/sharedfiles/filedetails/?id=3380210757), and
enabling or disabling one needs a **full restart of the game**, not just a scene reload.

---

## Building it

The app is built from the Python source in `spml/`. You only need this to make changes —
people you send the exe to do not.

```
pip install pyinstaller
python build.py                 -> dist/SeaPowerModLoader.exe
python build.py --with-cli      -> also dist/spml.exe, a command line version
```

`tools/make_icon.py` regenerates the icon from `assets/` and is the only place Pillow is
used; the app itself has no image dependencies.

The exe is not code-signed, so SmartScreen warns on first run. Signing needs a paid
certificate; short of that, sharing the source alongside the exe is what lets a cautious
person check what they are running.

---

## About

Part of **Helios** — tools and utilities built for games. Standalone tools like this one
run entirely on your machine, need no account, and are free. Anything that needs a server
behind it is the exception, and is priced accordingly.

The Sea Power Mod Loader is not affiliated with or endorsed by the developers of Sea Power.
