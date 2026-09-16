"""Build the app.

    python build.py                 -> dist/SeaPowerModLoader.exe
    python build.py --with-cli      -> also dist/spml.exe, the command line version

One self-contained executable. Whoever you send it to does not need Python, this
source, or anything else installed.

Needs PyInstaller (`pip install pyinstaller`) and, only if the icon is missing,
Pillow (`pip install pillow`).
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from spml import __version__                                # noqa: E402

DIST = ROOT / "dist"
BUILD = ROOT / "build"
ICON = ROOT / "assets" / "icon.ico"
UI_LOGO = ROOT / "assets" / "logo-ui.png"

# Only things nothing in the app can reach. A couple of megabytes is not worth the
# risk of excluding something a Tk dialog imports lazily on someone else's machine.
EXCLUDES = ["PIL", "numpy", "pytest", "setuptools", "pip", "pydoc_data"]


def run(command: list[str]) -> None:
    print("  $", " ".join(command[:6]), "..." if len(command) > 6 else "")
    result = subprocess.run(command, cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit(f"command failed with exit code {result.returncode}")


def ensure_icon() -> None:
    if ICON.is_file():
        return
    print("[icon] generating assets/icon.ico")
    run([sys.executable, str(ROOT / "tools" / "make_icon.py")])


def version_file() -> Path:
    """A Windows version resource, so the exe has real file properties."""
    parts = (__version__.split(".") + ["0", "0", "0"])[:3]
    major, minor, patch = (int(p) if p.isdigit() else 0 for p in parts)
    out = BUILD / "version_info.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({major}, {minor}, {patch}, 0),
    prodvers=({major}, {minor}, {patch}, 0),
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0,
    date=(0, 0)),
  kids=[
    StringFileInfo([
      StringTable('040904B0', [
        StringStruct('CompanyName', 'Helios'),
        StringStruct('FileDescription', 'Sea Power Mod Loader'),
        StringStruct('FileVersion', '{__version__}'),
        StringStruct('InternalName', 'spml'),
        StringStruct('LegalCopyright', 'Helios'),
        StringStruct('OriginalFilename', 'SeaPowerModLoader.exe'),
        StringStruct('ProductName', 'Sea Power Mod Loader'),
        StringStruct('ProductVersion', '{__version__}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])]
)
""", encoding="utf-8")
    return out


def pyinstall(name: str, entry: Path, windowed: bool, version: Path) -> None:
    command = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onefile",
        "--name", name,
        "--icon", str(ICON),
        "--add-data", f"{ICON}{';' if sys.platform == 'win32' else ':'}assets",
        "--add-data", f"{UI_LOGO}{';' if sys.platform == 'win32' else ':'}assets",
        "--paths", str(ROOT),
        "--version-file", str(version),
        "--distpath", str(DIST / "_exe"),
        "--workpath", str(BUILD / name),
        "--specpath", str(BUILD),
    ]
    command += ["--windowed"] if windowed else ["--console"]
    for module in EXCLUDES:
        command += ["--exclude-module", module]
    command.append(str(entry))
    run(command)


def collect() -> None:
    """Put the finished executables straight in dist/, with no wrapper folder."""
    for exe in (DIST / "_exe").glob("*.exe"):
        shutil.copy2(exe, DIST / exe.name)
    shutil.rmtree(DIST / "_exe", ignore_errors=True)


def main() -> int:
    with_cli = "--with-cli" in sys.argv

    print(f"Building Sea Power Mod Loader {__version__}")
    ensure_icon()
    version = version_file()

    print("[1/2] building the app")
    pyinstall("SeaPowerModLoader", ROOT / "tools" / "entry_gui.py", windowed=True, version=version)

    if with_cli:
        print("[2/2] building the command line version")
        pyinstall("spml", ROOT / "tools" / "entry_cli.py", windowed=False, version=version)

    print("[2/2] collecting" if not with_cli else "[done] collecting")
    collect()

    app_exe = DIST / "SeaPowerModLoader.exe"
    print("\nDone.\n")
    print("  Send this one file. Nothing else is needed:")
    print(f"    {app_exe}  ({app_exe.stat().st_size / (1024 * 1024):.1f} MB)")
    if with_cli:
        cli_exe = DIST / "spml.exe"
        print(f"\n  Command line version: {cli_exe}  "
              f"({cli_exe.stat().st_size / (1024 * 1024):.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
