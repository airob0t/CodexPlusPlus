from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codex_session_delete import __version__

DEFAULT_REPOSITORY = "BigPizzaV3/CodexPlusPlus"
DEFAULT_RELEASE_API_URL = f"https://api.github.com/repos/{DEFAULT_REPOSITORY}/releases/latest"
USER_AGENT = f"Codex++/{__version__}"
PACKAGE_MODULE_FILE = Path(__file__).resolve()
UPDATE_FEATURE_ENABLED = False


class UpdateError(RuntimeError):
    pass


@dataclass(frozen=True)
class Release:
    version: str
    url: str
    body: str
    asset_name: str | None = None
    asset_url: str | None = None

    @classmethod
    def from_github_payload(cls, payload: dict[str, Any]) -> "Release":
        asset = select_update_asset(payload.get("assets", []))
        return cls(
            version=str(payload["tag_name"]),
            url=str(payload.get("html_url") or ""),
            body=str(payload.get("body") or ""),
            asset_name=asset.get("name") if asset else None,
            asset_url=asset.get("browser_download_url") if asset else None,
        )


@dataclass(frozen=True)
class UpdateResult:
    release: Release
    installed_path: Path


def parse_version_tag(value: str) -> tuple[int, ...]:
    normalized = value.strip().lstrip("vV")
    match = re.match(r"^(\d+(?:\.\d+)*)", normalized)
    if not match:
        raise ValueError(f"Invalid version tag: {value}")
    return tuple(int(part) for part in match.group(1).split("."))


def is_newer_version(candidate: str, current: str = __version__) -> bool:
    left = parse_version_tag(candidate)
    right = parse_version_tag(current)
    length = max(len(left), len(right))
    left += (0,) * (length - len(left))
    right += (0,) * (length - len(right))
    return left > right


def select_update_asset(assets: list[dict[str, Any]]) -> dict[str, str] | None:
    named_assets = [asset for asset in assets if asset.get("name") and asset.get("browser_download_url")]
    for asset in named_assets:
        if str(asset["name"]).endswith(".whl"):
            return {"name": str(asset["name"]), "browser_download_url": str(asset["browser_download_url"])}
    for asset in named_assets:
        name = str(asset["name"]).lower()
        if name.endswith((".zip", ".tar.gz", ".tgz")):
            return {"name": str(asset["name"]), "browser_download_url": str(asset["browser_download_url"])}
    return None


def fetch_latest_release(api_url: str = DEFAULT_RELEASE_API_URL, timeout: int = 10) -> Release:
    raise UpdateError("更新功能已禁用")


def source_tree_root(module_file: Path = PACKAGE_MODULE_FILE) -> Path | None:
    package_dir = module_file.resolve().parent
    project_root = package_dir.parent
    if package_dir.name != "codex_session_delete":
        return None
    if not (project_root / ".git").exists():
        return None
    if not ((project_root / "pyproject.toml").exists() or (project_root / "setup.py").exists()):
        return None
    return project_root


def is_source_tree_mode() -> bool:
    return source_tree_root(PACKAGE_MODULE_FILE) is not None


def check_for_update(current_version: str = __version__) -> Release | None:
    return None


def safe_asset_name(name: str) -> str:
    cleaned = Path(name).name
    if cleaned in {"", ".", ".."}:
        raise UpdateError(f"非法 Release asset 文件名: {name}")
    return cleaned


def download_asset(url: str, name: str, download_dir: Path) -> Path:
    raise UpdateError("更新功能已禁用")


def perform_update(
    release: Release,
    *,
    python_executable: str = "",
    download_dir: Path | None = None,
) -> UpdateResult:
    raise UpdateError("更新功能已禁用")
