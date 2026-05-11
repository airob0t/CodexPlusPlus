import json
from pathlib import Path

import pytest

from codex_session_delete import updater


def test_parse_version_tag_accepts_v_prefix_and_suffix():
    assert updater.parse_version_tag("v1.2.3") == (1, 2, 3)
    assert updater.parse_version_tag("1.2.3") == (1, 2, 3)
    assert updater.parse_version_tag("v1.2.3-beta.1") == (1, 2, 3)


def test_is_newer_version_compares_numeric_segments():
    assert updater.is_newer_version("v1.0.10", "1.0.4") is True
    assert updater.is_newer_version("v1.0.4", "1.0.4") is False
    assert updater.is_newer_version("v1.0.3", "1.0.4") is False


def test_release_from_github_payload_selects_wheel_asset():
    release = updater.Release.from_github_payload(
        {
            "tag_name": "v1.0.5",
            "html_url": "https://github.com/BigPizzaV3/CodexPlusPlus/releases/tag/v1.0.5",
            "body": "fixes",
            "prerelease": False,
            "draft": False,
            "assets": [
                {"name": "CodexPlusPlus.zip", "browser_download_url": "https://example.test/source.zip"},
                {"name": "codex_session_delete-1.0.5-py3-none-any.whl", "browser_download_url": "https://example.test/pkg.whl"},
            ],
        }
    )

    assert release.version == "v1.0.5"
    assert release.asset_name == "codex_session_delete-1.0.5-py3-none-any.whl"
    assert release.asset_url == "https://example.test/pkg.whl"


def test_fetch_latest_release_is_disabled():
    with pytest.raises(updater.UpdateError, match="更新功能已禁用"):
        updater.fetch_latest_release()


def test_download_asset_is_disabled(tmp_path):
    with pytest.raises(updater.UpdateError, match="更新功能已禁用"):
        updater.download_asset("https://example.test/pkg.whl", "pkg.whl", tmp_path)


def test_perform_update_is_disabled(tmp_path):
    release = updater.Release(version="v1.0.5", url="https://example.test", body="", asset_name="pkg.whl", asset_url="https://example.test/pkg.whl")

    with pytest.raises(updater.UpdateError, match="更新功能已禁用"):
        updater.perform_update(release, python_executable="python.exe", download_dir=tmp_path)


def test_source_tree_root_detects_git_clone_project(tmp_path):
    project = tmp_path / "CodexPlusPlus"
    package = project / "codex_session_delete"
    package.mkdir(parents=True)
    (project / ".git").mkdir()
    (project / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    module_file = package / "updater.py"
    module_file.write_text("", encoding="utf-8")

    assert updater.source_tree_root(module_file) == project


def test_source_tree_root_ignores_non_source_install(tmp_path):
    package = tmp_path / "site-packages" / "codex_session_delete"
    package.mkdir(parents=True)
    module_file = package / "updater.py"
    module_file.write_text("", encoding="utf-8")

    assert updater.source_tree_root(module_file) is None


def test_check_for_update_skips_source_tree_mode(monkeypatch, tmp_path):
    project = tmp_path / "CodexPlusPlus"
    package = project / "codex_session_delete"
    package.mkdir(parents=True)
    (project / ".git").mkdir()
    (project / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    module_file = package / "updater.py"
    module_file.write_text("", encoding="utf-8")
    monkeypatch.setattr(updater, "PACKAGE_MODULE_FILE", module_file)

    assert updater.check_for_update() is None


def test_check_for_update_is_disabled_even_outside_source_tree(monkeypatch, tmp_path):
    package = tmp_path / "site-packages" / "codex_session_delete"
    package.mkdir(parents=True)
    module_file = package / "updater.py"
    module_file.write_text("", encoding="utf-8")
    monkeypatch.setattr(updater, "PACKAGE_MODULE_FILE", module_file)

    assert updater.check_for_update() is None
