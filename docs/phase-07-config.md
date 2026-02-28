# Phase 7: Config File + Export Config

**Status:** `pending`
**Estimated effort:** Day 15–16
**Depends on:** Phase 2 (walker + download)
**Blocks:** Nothing

---

## Objective

Implement YAML config file loading with Click's `ctx.default_map` pattern, the `ResolvedConfig` frozen dataclass, and per-directory export format overrides.

---

## Deliverables

### 1. `config.py` — YAML Loading + Config Resolution

**Reference:** [development-plan.md §14](development-plan.md#14-configuration)

#### Config File Discovery

Search order (first found wins):
1. `--config FILE` (explicit, hard error if missing)
2. `./gdrive-dl.yaml` / `./gdrive-dl.yml`
3. `$XDG_CONFIG_HOME/gdrive-dl/config.yaml`
4. `~/.config/gdrive-dl/config.yaml`
5. `~/.gdrive-dl.yaml`
6. Platform-specific: `~/Library/Application Support/gdrive-dl/config.yaml` (macOS)

```python
def discover_config_file() -> Optional[Path]:
    """Search standard locations for config file."""

def load_config(path: Path) -> dict:
    """Load and validate YAML config file."""
```

#### Config Flattening for `ctx.default_map`

Click's `ctx.default_map` expects a flat dict. Nested YAML must be flattened:

```python
def _flatten_config(raw: dict) -> dict:
    """Flatten nested YAML into Click-compatible default_map."""
    # archival.permissions → permissions
    # archival.comments → comments
    # export_formats → export_config (special handling)
```

#### Click Eager Callback

```python
def load_config_callback(ctx, param, value):
    """Eager callback for --config option. Populates ctx.default_map."""
    if value is None:
        value = discover_config_file()
    if value is None:
        return value
    raw = yaml.safe_load(Path(value).read_text())
    ctx.default_map = _flatten_config(raw)
    return value
```

#### Merge Precedence

Lowest to highest:
1. Click `default=` values
2. Config file values (via `ctx.default_map`)
3. CLI flags explicitly passed by user

**Critical:** CLI defaults must not silently override config file values — handled by `ctx.default_map`.

### 2. `ResolvedConfig` Dataclass

**Reference:** [development-plan.md §4](development-plan.md#4-core-module-architecture)

```python
@dataclass(frozen=True)
class ResolvedConfig:
    """Immutable config constructed once in cli.main(), threaded everywhere."""
    source_id: str
    output_dir: str
    dry_run: bool
    flat: bool
    shared_drives: Optional[str]
    credentials_file: str
    token_file: str
    service_account_file: Optional[str]
    browser: Optional[str]
    no_browser: bool
    permissions: bool
    comments: bool
    revisions: Optional[int]
    metadata: bool
    api_query: Optional[str]
    post_filter: Optional[str]
    filter_confirm: bool
    export_config: ExportConfig
    resume: bool
    manifest_file: str
    verify_checksums: bool
    rate_limit: Optional[int]
    retries: int
    report: bool
    report_format: str
    quiet: bool
    verbose: bool
```

### 3. `ExportConfig` — Per-Directory Export Formats

```python
@dataclass(frozen=True)
class ExportConfig:
    defaults: dict[str, str]      # {"docs": "docx", "sheets": "xlsx", ...}
    overrides: dict[str, dict]    # {"/Legal": {"docs": "pdf"}, ...}

    def get_format(self, workspace_type: str, drive_path: str) -> tuple[str, str]:
        """Return (export_mime, extension) for a file based on type and path."""
```

#### Override Resolution

1. Check path-specific overrides (longest prefix match)
2. Fall back to global defaults from config
3. Fall back to built-in defaults from `constants.py`

### 4. YAML Config Schema

```yaml
credentials: ./credentials.json
token: ./token.json
browser: null
verify: true
retries: 5
rate_limit: null

archival:
  permissions: false
  comments: false
  revisions: false          # false | true (all) | integer (N most recent)
  metadata: false

export_formats:
  defaults:
    docs: docx
    sheets: xlsx
    slides: pptx
  overrides:
    "/Legal":
      docs: pdf
      sheets: pdf

report: false
report_format: markdown
```

### 5. CLI Integration

```python
@click.option("--config", callback=load_config_callback, is_eager=True,
              expose_value=False, help="YAML config file path")
@click.option("--export-format", multiple=True, help="TYPE=FORMAT export override")
@click.option("--export-config", default=None, help="Export config YAML file")
@click.option("--dual-export", multiple=True, help="TYPE=FORMAT1,FORMAT2 dual export")
```

---

## Tests (Write First)

### `test_config.py`

```python
# Discovery
def test_discover_explicit_config():
    """--config FILE uses that file directly."""

def test_discover_local_yaml():
    """Finds ./gdrive-dl.yaml in current directory."""

def test_discover_xdg_config():
    """Finds config in XDG_CONFIG_HOME."""

def test_discover_no_config():
    """Returns None when no config file exists."""

def test_explicit_config_missing_raises_error():
    """--config with nonexistent file raises ConfigError."""

# Loading
def test_load_valid_yaml():
    """Valid YAML file loads correctly."""

def test_load_invalid_yaml_raises_error():
    """Malformed YAML raises ConfigError."""

# Flattening
def test_flatten_nested_archival():
    """archival.permissions flattens to 'permissions'."""

def test_flatten_preserves_top_level():
    """Top-level keys pass through unchanged."""

# Merge precedence
def test_cli_overrides_config():
    """CLI flag overrides config file value."""

def test_config_overrides_default():
    """Config file value overrides Click default."""

def test_cli_default_does_not_override_config():
    """Unprovided CLI flag does not override config value."""

# ExportConfig
def test_export_config_default_format():
    """Default format returned for unmatched path."""

def test_export_config_path_override():
    """Path-specific override takes precedence."""

def test_export_config_longest_prefix():
    """/Legal/Contracts matches /Legal override, not root default."""

def test_export_format_cli_override():
    """--export-format docs=pdf overrides config defaults."""

# ResolvedConfig
def test_resolved_config_frozen():
    """ResolvedConfig is immutable (frozen dataclass)."""
```

---

## Verification Checklist

- [ ] `--config gdrive-dl.yaml` loads settings from YAML
- [ ] Config values are overridden by CLI flags
- [ ] Auto-discovery finds `./gdrive-dl.yaml` without `--config`
- [ ] Per-directory export format overrides work (e.g., `/Legal` → PDF)
- [ ] `--export-format docs=pdf` overrides default format
- [ ] Invalid YAML gives clear error message
- [ ] Missing explicit `--config` file gives clear error
- [ ] `ResolvedConfig` is immutable
- [ ] `pytest tests/test_config.py` — all pass
