# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build recipe for VibeParser.exe (one-file, console)."""

from PyInstaller.utils.hooks import collect_all, copy_metadata

datas = [(".env.example", ".")]
binaries = []
hiddenimports = []

# aiogram loads some modules dynamically; tzdata ships the IANA timezone files.
for package in ("aiogram", "tzdata"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

# Packages that read their own version from importlib.metadata.
for distribution in (
    "aiogram",
    "aiosqlite",
    "httpx",
    "pydantic",
    "pydantic-settings",
    "beautifulsoup4",
    "lxml",
    "pillow",
    "qrcode",
    "python-dotenv",
    "tzdata",
):
    try:
        datas += copy_metadata(distribution)
    except Exception:  # noqa: BLE001 - metadata is nice to have, not required
        pass

hiddenimports += [
    "aiosqlite",
    "aiofiles",
    "aiofiles.threadpool",
    "aiofiles.os",
    "bs4",
    "bs4.builder._lxml",
    "lxml.etree",
    "lxml.html",
    "qrcode",
    "qrcode.image.pil",
    "pydantic",
    "pydantic_settings",
    "dotenv",
    "sqlite3",
    "zoneinfo",
]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Playwright is optional and not bundled: SCREENSHOT_MODE=page falls back
    # to the Pillow card in the .exe.
    excludes=[
        "playwright",
        "greenlet",
        "pyee",
        "pytest",
        "pytest_asyncio",
        "tkinter",
        "setuptools",
        "pip",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="VibeParser",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/vibeparser.ico",
    version="assets/version_info.txt",
)
