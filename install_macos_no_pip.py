from __future__ import annotations

import argparse
import re
import shutil
import stat
import sys
from pathlib import Path


APP_NAME = "Codex++.app"
EXECUTABLE_NAME = "CodexPlusPlus"


def repo_root() -> Path:
    return Path(__file__).resolve().parent


def package_version(root: Path) -> str:
    init_file = root / "codex_session_delete" / "__init__.py"
    text = init_file.read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    if not match:
        raise RuntimeError("Cannot determine package version")
    return match.group(1)


def launcher_command(root: Path) -> str:
    python = shlex_quote(str(sys.executable))
    return f'env PYTHONPATH={shlex_quote(str(root))} {python} -m codex_session_delete launch'


def shlex_quote(value: str) -> str:
    import shlex

    return shlex.quote(value)


def install_macos_app(root: Path, install_root: Path | None = None, launcher_override: str | None = None) -> Path:
    version = package_version(root)
    app_root = (install_root or Path("/Applications")) / APP_NAME
    contents = app_root / "Contents"
    macos = contents / "MacOS"
    resources = contents / "Resources"
    macos.mkdir(parents=True, exist_ok=True)
    resources.mkdir(parents=True, exist_ok=True)

    launcher = launcher_override or launcher_command(root)
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Codex++</string>
  <key>CFBundleDisplayName</key><string>Codex++</string>
  <key>CFBundleIdentifier</key><string>com.bigpizzav3.codexplusplus</string>
  <key>CFBundleVersion</key><string>{version}</string>
  <key>CFBundleShortVersionString</key><string>{version}</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>{EXECUTABLE_NAME}</string>
  <key>CFBundleIconFile</key><string>codex-plus-plus.png</string>
  <key>LSUIElement</key><true/>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
</dict>
</plist>
"""
    (contents / "Info.plist").write_text(plist, encoding="utf-8")

    executable = macos / EXECUTABLE_NAME
    executable.write_text(f"#!/bin/sh\nexec {launcher}\n", encoding="utf-8")
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    icon_asset = root / "codex_session_delete" / "assets" / "codex-plus-plus.png"
    if icon_asset.is_file():
        shutil.copy2(icon_asset, resources / "codex-plus-plus.png")

    return app_root


def uninstall_macos_app(install_root: Path | None = None) -> None:
    app_root = (install_root or Path("/Applications")) / APP_NAME
    if app_root.exists():
        shutil.rmtree(app_root)


def main(argv: list[str] | None = None) -> int:
    root = repo_root()
    parser = argparse.ArgumentParser(description="Install Codex++ on macOS without pip")
    subparsers = parser.add_subparsers(dest="command", required=True)

    setup = subparsers.add_parser("setup", help="Create /Applications/Codex++.app from source tree")
    setup.add_argument("--install-root", type=Path, default=None)
    setup.add_argument("--launcher-command", default=None)

    remove = subparsers.add_parser("remove", help="Remove /Applications/Codex++.app")
    remove.add_argument("--install-root", type=Path, default=None)

    args = parser.parse_args(argv)
    if args.command == "setup":
        app_root = install_macos_app(root, args.install_root, args.launcher_command)
        print(f"Codex++ 已安装: {app_root}")
        return 0
    if args.command == "remove":
        uninstall_macos_app(args.install_root)
        print("Codex++ 已卸载。")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
