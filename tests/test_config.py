"""Tests for gdrive_dl.config — YAML loading, flattening, ExportConfig, ResolvedConfig."""

from __future__ import annotations

import dataclasses

import click
import pytest
from click.testing import CliRunner

from gdrive_dl.config import (
    ExportConfig,
    ResolvedConfig,
    _flatten_config,
    build_export_config,
    discover_config_file,
    load_config,
    load_config_callback,
)
from gdrive_dl.constants import EXPORT_FORMATS
from gdrive_dl.exceptions import ConfigError

# ---------------------------------------------------------------------------
# Config File Discovery
# ---------------------------------------------------------------------------


class TestDiscoverConfigFile:
    """Config file auto-discovery."""

    def test_discover_local_yaml(self, tmp_path, monkeypatch):
        """Finds ./gdrive-dl.yaml in the current directory."""
        config = tmp_path / "gdrive-dl.yaml"
        config.write_text("retries: 10\n")
        monkeypatch.chdir(tmp_path)
        result = discover_config_file()
        assert result is not None
        assert result.name == "gdrive-dl.yaml"

    def test_discover_local_yml(self, tmp_path, monkeypatch):
        """Finds ./gdrive-dl.yml when .yaml doesn't exist."""
        config = tmp_path / "gdrive-dl.yml"
        config.write_text("retries: 10\n")
        monkeypatch.chdir(tmp_path)
        result = discover_config_file()
        assert result is not None
        assert result.name == "gdrive-dl.yml"

    def test_discover_xdg_config(self, tmp_path, monkeypatch):
        """Finds config in XDG_CONFIG_HOME."""
        xdg_dir = tmp_path / "xdg"
        config_dir = xdg_dir / "gdrive-dl"
        config_dir.mkdir(parents=True)
        (config_dir / "config.yaml").write_text("retries: 10\n")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_dir))
        # chdir to a dir with no local config
        empty = tmp_path / "empty"
        empty.mkdir()
        monkeypatch.chdir(empty)
        result = discover_config_file()
        assert result is not None
        assert "xdg" in str(result)

    def test_discover_no_config(self, tmp_path, monkeypatch):
        """Returns None when no config file exists in any location."""
        monkeypatch.chdir(tmp_path)
        # Override HOME and XDG to prevent finding real user configs
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "nonexistent"))
        result = discover_config_file()
        assert result is None

    def test_explicit_config_missing_raises(self, tmp_path):
        """load_config_callback raises click.BadParameter for missing explicit file."""
        @click.command()
        @click.option(
            "--config", callback=load_config_callback,
            is_eager=True, expose_value=False,
        )
        @click.option("--retries", default=5)
        def cmd(retries):
            click.echo(str(retries))

        runner = CliRunner()
        result = runner.invoke(cmd, ["--config", str(tmp_path / "missing.yaml")])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Config Loading
# ---------------------------------------------------------------------------


class TestLoadConfig:
    """YAML loading and validation."""

    def test_load_valid_yaml(self, tmp_path):
        """Valid YAML file loads as dict correctly."""
        config = tmp_path / "config.yaml"
        config.write_text("retries: 10\ncredentials: ./creds.json\n")
        data = load_config(config)
        assert data["retries"] == 10
        assert data["credentials"] == "./creds.json"

    def test_load_invalid_yaml_raises_error(self, tmp_path):
        """Malformed YAML raises ConfigError."""
        config = tmp_path / "config.yaml"
        config.write_text(":\n  bad: [yaml\n")
        with pytest.raises(ConfigError):
            load_config(config)

    def test_load_empty_yaml_returns_empty_dict(self, tmp_path):
        """Empty YAML file returns empty dict."""
        config = tmp_path / "config.yaml"
        config.write_text("")
        data = load_config(config)
        assert data == {}

    def test_load_non_dict_raises_error(self, tmp_path):
        """YAML that parses to a list raises ConfigError."""
        config = tmp_path / "config.yaml"
        config.write_text("- item1\n- item2\n")
        with pytest.raises(ConfigError):
            load_config(config)


# ---------------------------------------------------------------------------
# Config Flattening
# ---------------------------------------------------------------------------


class TestFlattenConfig:
    """Flatten nested YAML into Click-compatible default_map."""

    def test_flatten_nested_archival(self):
        """archival.permissions flattens to 'permissions'."""
        raw = {
            "archival": {
                "permissions": True,
                "comments": True,
                "metadata": False,
            },
        }
        flat = _flatten_config(raw)
        assert flat["permissions"] is True
        assert flat["comments"] is True
        assert flat["metadata"] is False
        assert "archival" not in flat

    def test_flatten_preserves_top_level(self):
        """Top-level keys like 'retries' pass through unchanged."""
        raw = {"retries": 10, "credentials": "./creds.json"}
        flat = _flatten_config(raw)
        assert flat["retries"] == 10
        assert flat["credentials"] == "./creds.json"

    def test_flatten_excludes_export_formats(self):
        """export_formats section is excluded from default_map."""
        raw = {
            "retries": 5,
            "export_formats": {
                "defaults": {"docs": "pdf"},
            },
        }
        flat = _flatten_config(raw)
        assert "export_formats" not in flat
        assert flat["retries"] == 5


# ---------------------------------------------------------------------------
# Merge Precedence (via Click integration)
# ---------------------------------------------------------------------------


class TestMergePrecedence:
    """Config file + CLI flag merge precedence."""

    def _make_cmd(self):
        @click.command()
        @click.option(
            "--config", callback=load_config_callback,
            is_eager=True, expose_value=False,
        )
        @click.option("--retries", type=int, default=5)
        def cmd(retries):
            click.echo(str(retries))
        return cmd

    def test_config_overrides_default(self, tmp_path):
        """Config file value (retries: 10) overrides Click's default=5."""
        config = tmp_path / "gdrive-dl.yaml"
        config.write_text("retries: 10\n")
        runner = CliRunner()
        result = runner.invoke(self._make_cmd(), ["--config", str(config)])
        assert result.exit_code == 0
        assert result.output.strip() == "10"

    def test_cli_overrides_config(self, tmp_path):
        """Explicit CLI --retries 3 beats config file retries: 10."""
        config = tmp_path / "gdrive-dl.yaml"
        config.write_text("retries: 10\n")
        runner = CliRunner()
        result = runner.invoke(
            self._make_cmd(), ["--config", str(config), "--retries", "3"],
        )
        assert result.exit_code == 0
        assert result.output.strip() == "3"

    def test_cli_default_does_not_override_config(self, tmp_path):
        """When --retries is not passed, config file value wins over Click default."""
        config = tmp_path / "gdrive-dl.yaml"
        config.write_text("retries: 7\n")
        runner = CliRunner()
        result = runner.invoke(self._make_cmd(), ["--config", str(config)])
        assert result.exit_code == 0
        assert result.output.strip() == "7"


# ---------------------------------------------------------------------------
# ExportConfig
# ---------------------------------------------------------------------------


class TestExportConfig:
    """Export format resolution with defaults and path overrides."""

    def test_default_fallback_to_constants(self):
        """With empty defaults and overrides, falls back to EXPORT_FORMATS."""
        ec = ExportConfig(defaults={}, overrides={})
        mime = "application/vnd.google-apps.document"
        result = ec.get_format(mime, "report.gdoc")
        expected = EXPORT_FORMATS[mime]
        assert result == expected

    def test_custom_default_format(self):
        """ExportConfig with defaults={'docs': 'pdf'} returns pdf for docs."""
        ec = ExportConfig(defaults={"docs": "pdf"}, overrides={})
        mime = "application/vnd.google-apps.document"
        result = ec.get_format(mime, "report.gdoc")
        assert result is not None
        assert result[1] == ".pdf"

    def test_path_override(self):
        """Path-specific override takes precedence over default."""
        ec = ExportConfig(
            defaults={"docs": "docx"},
            overrides={"Legal": {"docs": "pdf"}},
        )
        mime = "application/vnd.google-apps.document"
        result = ec.get_format(mime, "Legal/contract.gdoc")
        assert result is not None
        assert result[1] == ".pdf"

    def test_longest_prefix_match(self):
        """Longest matching prefix wins among overrides."""
        ec = ExportConfig(
            defaults={"docs": "docx"},
            overrides={
                "Legal": {"docs": "pdf"},
                "Legal/Internal": {"docs": "odt"},
            },
        )
        mime = "application/vnd.google-apps.document"
        result = ec.get_format(mime, "Legal/Internal/memo.gdoc")
        assert result is not None
        assert result[1] == ".odt"

    def test_unknown_mime_returns_none(self):
        """Unknown workspace MIME returns None."""
        ec = ExportConfig(defaults={}, overrides={})
        result = ec.get_format("application/vnd.google-apps.unknown", "file")
        assert result is None


# ---------------------------------------------------------------------------
# build_export_config
# ---------------------------------------------------------------------------


class TestBuildExportConfig:
    """Building ExportConfig from YAML + CLI overrides."""

    def test_from_yaml_section(self):
        """Builds from export_formats YAML section."""
        raw = {
            "defaults": {"docs": "pdf", "sheets": "xlsx"},
            "overrides": {"Legal": {"docs": "pdf"}},
        }
        ec = build_export_config(raw, ())
        assert ec.defaults["docs"] == "pdf"
        assert "Legal" in ec.overrides

    def test_cli_overrides_yaml(self):
        """CLI --export-format overrides config file defaults."""
        raw = {"defaults": {"docs": "docx"}}
        ec = build_export_config(raw, ("docs=pdf",))
        assert ec.defaults["docs"] == "pdf"

    def test_invalid_cli_format_raises(self):
        """Invalid --export-format string raises ConfigError."""
        with pytest.raises(ConfigError):
            build_export_config(None, ("bad-format",))

    def test_none_raw_config(self):
        """None raw_config produces empty defaults/overrides."""
        ec = build_export_config(None, ())
        assert ec.defaults == {}
        assert ec.overrides == {}


# ---------------------------------------------------------------------------
# ResolvedConfig
# ---------------------------------------------------------------------------


class TestResolvedConfig:
    """ResolvedConfig frozen dataclass."""

    def test_frozen(self):
        """ResolvedConfig is immutable (frozen dataclass)."""
        ec = ExportConfig(defaults={}, overrides={})
        rc = ResolvedConfig(
            source_id="root",
            output_dir="./out",
            dry_run=False,
            credentials_file="./creds.json",
            token_file="./token.json",
            service_account_file=None,
            browser=None,
            no_browser=False,
            api_query=None,
            post_filter=None,
            filter_confirm=False,
            rate_limit=None,
            retries=5,
            permissions=False,
            comments=False,
            metadata=False,
            revisions=None,
            export_config=ec,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            rc.retries = 10  # type: ignore[misc]
