"""YAML config loading, ExportConfig, and ResolvedConfig for gdrive-dl."""

from __future__ import annotations

import logging
import os
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import click
import yaml

from gdrive_dl.constants import EXPORT_FORMATS
from gdrive_dl.exceptions import ConfigError

logger = logging.getLogger(__name__)

# Maps user-facing short names to Google Workspace MIME types
_SHORT_NAME_TO_MIME: dict[str, str] = {
    "docs": "application/vnd.google-apps.document",
    "sheets": "application/vnd.google-apps.spreadsheet",
    "slides": "application/vnd.google-apps.presentation",
    "drawings": "application/vnd.google-apps.drawing",
    "script": "application/vnd.google-apps.script",
}

# Reverse lookup: MIME → short name
_MIME_TO_SHORT_NAME: dict[str, str] = {v: k for k, v in _SHORT_NAME_TO_MIME.items()}

# Maps format short names to (export_mime, extension) per workspace type
_FORMAT_ENTRIES: dict[str, dict[str, tuple[str, str]]] = {
    "pdf": {
        "docs": ("application/pdf", ".pdf"),
        "sheets": ("application/pdf", ".pdf"),
        "slides": ("application/pdf", ".pdf"),
        "drawings": ("application/pdf", ".pdf"),
    },
    "docx": {
        "docs": (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".docx",
        ),
    },
    "xlsx": {
        "sheets": (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".xlsx",
        ),
    },
    "pptx": {
        "slides": (
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            ".pptx",
        ),
    },
    "odt": {
        "docs": ("application/vnd.oasis.opendocument.text", ".odt"),
    },
    "ods": {
        "sheets": ("application/vnd.oasis.opendocument.spreadsheet", ".ods"),
    },
    "odp": {
        "slides": ("application/vnd.oasis.opendocument.presentation", ".odp"),
    },
    "rtf": {
        "docs": ("application/rtf", ".rtf"),
    },
    "txt": {
        "docs": ("text/plain", ".txt"),
    },
    "csv": {
        "sheets": ("text/csv", ".csv"),
    },
    "html": {
        "docs": ("text/html", ".html"),
    },
    "epub": {
        "docs": ("application/epub+zip", ".epub"),
    },
    "json": {
        "script": ("application/vnd.google-apps.script+json", ".json"),
    },
    "png": {
        "drawings": ("image/png", ".png"),
    },
    "svg": {
        "drawings": ("image/svg+xml", ".svg"),
    },
}


# ---------------------------------------------------------------------------
# ExportConfig
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExportConfig:
    """Per-directory export format overrides for Workspace files.

    defaults: mapping of short type name → short format name,
              e.g. {"docs": "pdf", "sheets": "xlsx"}
    overrides: mapping of drive path prefix → short-name dict,
               e.g. {"Legal": {"docs": "pdf"}}
    """

    defaults: dict[str, str]
    overrides: dict[str, dict[str, str]]

    def get_format(
        self,
        workspace_mime: str,
        drive_path: str,
    ) -> tuple[str, str] | None:
        """Return (export_mime, extension) for a workspace file.

        Resolution order (highest to lowest precedence):
        1. Longest matching path prefix in self.overrides
        2. self.defaults
        3. EXPORT_FORMATS from constants.py (built-in default)
        Returns None if workspace_mime is not a known exportable type.
        """
        short_name = _MIME_TO_SHORT_NAME.get(workspace_mime)

        # 1. Path-specific overrides (longest prefix match)
        if (short_name is not None) and self.overrides:
            matched = _longest_prefix_match(drive_path, self.overrides)
            if matched is not None:
                fmt_name = self.overrides[matched].get(short_name)
                if fmt_name is not None:
                    entry = _resolve_format(short_name, fmt_name)
                    if entry is not None:
                        return entry

        # 2. Global defaults from config
        if short_name is not None:
            fmt_name = self.defaults.get(short_name)
            if fmt_name is not None:
                entry = _resolve_format(short_name, fmt_name)
                if entry is not None:
                    return entry

        # 3. Built-in constant fallback
        return EXPORT_FORMATS.get(workspace_mime)


def _longest_prefix_match(
    path: str, overrides: dict[str, dict[str, str]],
) -> str | None:
    """Return the longest key in overrides that is a prefix of path."""
    candidates = [key for key in overrides if path.startswith(key)]
    if not candidates:
        return None
    return max(candidates, key=len)


def _resolve_format(
    short_name: str, fmt_name: str,
) -> tuple[str, str] | None:
    """Lookup (export_mime, ext) for a short type name + format name pair."""
    type_map = _FORMAT_ENTRIES.get(fmt_name)
    if type_map is None:
        return None
    return type_map.get(short_name)


# ---------------------------------------------------------------------------
# ResolvedConfig
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResolvedConfig:
    """Immutable, fully-resolved configuration for a download session.

    Constructed once in cli.main() after Click has merged config-file
    defaults with CLI flags.
    """

    source_id: str
    output_dir: str
    dry_run: bool
    credentials_file: str
    token_file: str
    service_account_file: str | None
    browser: str | None
    no_browser: bool
    api_query: str | None
    post_filter: str | None
    filter_confirm: bool
    rate_limit: float | None
    retries: int
    permissions: bool
    comments: bool
    metadata: bool
    revisions: int | None
    export_config: ExportConfig


# ---------------------------------------------------------------------------
# Config File Discovery
# ---------------------------------------------------------------------------


def discover_config_file() -> Path | None:
    """Search standard locations for a gdrive-dl config file.

    Priority order (first found wins):
    1. ./gdrive-dl.yaml
    2. ./gdrive-dl.yml
    3. $XDG_CONFIG_HOME/gdrive-dl/config.yaml
    4. ~/.config/gdrive-dl/config.yaml
    5. ~/.gdrive-dl.yaml
    6. ~/Library/Application Support/gdrive-dl/config.yaml (macOS only)
    """
    candidates: list[Path] = []

    # 1-2: Current directory
    candidates.append(Path("gdrive-dl.yaml"))
    candidates.append(Path("gdrive-dl.yml"))

    # 3: XDG_CONFIG_HOME (explicit env var)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        candidates.append(Path(xdg) / "gdrive-dl" / "config.yaml")

    # 4: ~/.config fallback (XDG default)
    candidates.append(Path.home() / ".config" / "gdrive-dl" / "config.yaml")

    # 5: ~/.gdrive-dl.yaml
    candidates.append(Path.home() / ".gdrive-dl.yaml")

    # 6: macOS-specific
    if platform.system() == "Darwin":
        candidates.append(
            Path.home() / "Library" / "Application Support"
            / "gdrive-dl" / "config.yaml",
        )

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return None


# ---------------------------------------------------------------------------
# Config Loading
# ---------------------------------------------------------------------------


def load_config(path: Path) -> dict[str, Any]:
    """Load a YAML config file. Raises ConfigError on parse failure."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {path}: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"Cannot read config file {path}: {exc}") from exc

    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ConfigError(
            f"Config file {path} must be a YAML mapping, got {type(raw).__name__}",
        )
    return raw


def _flatten_config(raw: dict[str, Any]) -> dict[str, Any]:
    """Flatten nested YAML into a Click ctx.default_map-compatible dict.

    Rules:
    - Top-level scalar/null values pass through unchanged.
    - 'archival' section: each sub-key is promoted to the top level.
    - 'export_formats' section: excluded (not a Click option).
    """
    result: dict[str, Any] = {}

    for key, value in raw.items():
        if (key == "archival") and isinstance(value, dict):
            for sub_key, sub_val in value.items():
                result[sub_key] = sub_val
        elif key == "export_formats":
            pass
        else:
            result[key] = value

    return result


# ---------------------------------------------------------------------------
# Click Eager Callback
# ---------------------------------------------------------------------------


def load_config_callback(
    ctx: click.Context, param: click.Parameter, value: str | None,
) -> str | None:
    """Eager callback for the --config option. Populates ctx.default_map."""
    if value is None:
        path = discover_config_file()
        if path is None:
            return None
    else:
        path = Path(value)
        if not path.exists():
            raise click.BadParameter(
                f"Config file not found: {value}",
                ctx=ctx,
                param=param,
            )

    try:
        raw = load_config(path)
    except ConfigError as exc:
        raise click.BadParameter(str(exc), ctx=ctx, param=param) from exc

    # Stash raw config for build_export_config in main()
    ctx.ensure_object(dict)
    ctx.meta["raw_config"] = raw

    flat = _flatten_config(raw)
    if ctx.default_map is None:
        ctx.default_map = flat
    else:
        ctx.default_map = {**flat, **ctx.default_map}

    return str(path)


# ---------------------------------------------------------------------------
# build_export_config
# ---------------------------------------------------------------------------


def build_export_config(
    raw_config: dict[str, Any] | None,
    cli_overrides: tuple[str, ...],
) -> ExportConfig:
    """Build an ExportConfig from config-file data and CLI --export-format flags.

    raw_config: the 'export_formats' section of the loaded YAML (or None).
    cli_overrides: tuple of "TYPE=FORMAT" strings from --export-format.

    CLI overrides take precedence over config-file defaults.
    """
    defaults: dict[str, str] = {}
    overrides: dict[str, dict[str, str]] = {}

    if raw_config:
        defaults = dict(raw_config.get("defaults", {}))
        raw_overrides = raw_config.get("overrides", {})
        overrides = {k: dict(v) for k, v in raw_overrides.items()}

    # Apply CLI overrides into defaults (CLI wins)
    for item in cli_overrides:
        if "=" not in item:
            raise ConfigError(
                f"--export-format must be TYPE=FORMAT, got: {item!r}",
            )
        type_name, fmt_name = item.split("=", 1)
        type_name = type_name.strip().lower()
        fmt_name = fmt_name.strip().lower()
        if type_name not in _SHORT_NAME_TO_MIME:
            raise ConfigError(
                f"Unknown export type {type_name!r}. "
                f"Valid types: {', '.join(sorted(_SHORT_NAME_TO_MIME))}",
            )
        defaults[type_name] = fmt_name

    return ExportConfig(defaults=defaults, overrides=overrides)
