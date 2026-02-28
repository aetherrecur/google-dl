# Phase 4: Filtering

**Status:** `completed`
**Estimated effort:** Day 8–9
**Depends on:** Phase 2 (walker)
**Blocks:** Nothing

---

## Objective

Implement the two-tier filtering system: API-level query pushdown (`--query`) and post-fetch local filtering (`--filter`). Include cost estimation and the `--filter-confirm` safety guard.

---

## Deliverables

### 1. `filters.py` — Two-Tier Filtering

**Reference:** [development-plan.md §10](development-plan.md#10-filtering)

#### Tier 1: API Pushdown (`--query`)

Injected verbatim into the `q` parameter of `files.list`:

```python
def build_query(folder_id: str, extra_query: Optional[str] = None) -> str:
    base = f"'{folder_id}' in parents and trashed = false"
    if extra_query:
        return f"({base}) and ({extra_query})"
    return base
```

#### Tier 2: Post-Fetch (`--filter`)

Applied locally after metadata retrieval:

```python
def apply_post_filter(items: list[DriveItem], filter_expr: str,
                      service, config) -> list[DriveItem]:
    """Evaluate post-fetch filter. May require additional API calls."""
```

#### Supported Filter Predicates

| Expression | Cost | Extra API Calls |
|-----------|------|----------------|
| `size>10mb` | Free | None |
| `ext:.pdf` | Free | None |
| `name:report` | Free | None |
| `modified_before:2025-01-01` | Free | None |
| `owner:alice@company.com` | Free | None (in walker metadata) |
| `shared_by:alice@company.com` | Per-file | +1 `permissions.list` |
| `has:comments` | Free/Per-file | None if `commentCount` available |
| `has:revisions` | Per-file | +1 `revisions.list` |

#### Evaluation Order

Free predicates first (short-circuit before expensive ones):

```python
def _evaluate_predicates(item, predicates, service):
    free = [p for p in predicates if p.cost == PredicateCost.FREE]
    expensive = [p for p in predicates if p.cost == PredicateCost.PER_FILE]

    # Short-circuit: if any free predicate fails, skip expensive ones
    for pred in free:
        if not pred.evaluate(item):
            return False

    for pred in expensive:
        if not pred.evaluate(item, service):
            return False

    return True
```

### 2. Filter Expression Parser

```python
def parse_filter(expression: str) -> list[Predicate]:
    """Parse filter expression into list of Predicate objects."""
    # "size>10mb" → SizePredicate(op=">", value=10_000_000)
    # "ext:.pdf" → ExtensionPredicate(ext=".pdf")
    # "name:report" → NamePredicate(pattern="report")
```

### 3. Cost Estimation + `--filter-confirm`

```python
def estimate_filter_cost(items: list[DriveItem], predicates: list[Predicate]) -> int:
    """Estimate additional API calls needed for expensive predicates."""
```

- If estimated calls > 100 and `--filter-confirm` not set and not `--dry-run`: print warning, exit
- In `--dry-run` mode: show cost estimate without prompting

### 4. CLI Options

```python
@click.option("--query", default=None, help="API-level filter (Drive query syntax)")
@click.option("--filter", "post_filter", default=None, help="Post-fetch filter expression")
@click.option("--filter-confirm", is_flag=True, help="Allow expensive filter operations")
```

### 5. Integration with Walker

Pass `--query` value into `walker.walk()` as `extra_query` parameter:

```python
file_tree = walker.walk(service, source_id, config)
# --query is already applied during walk via build_query()
# --filter is applied after walk returns
filtered = filters.apply_post_filter(file_tree, config.post_filter, service, config)
```

---

## Tests (Write First)

### `test_filters.py`

```python
# Query building
def test_build_query_base_only():
    """Without extra_query, returns standard parent + not trashed."""

def test_build_query_with_extra():
    """Extra query is ANDed with base query."""

# Free predicates
def test_size_predicate_greater_than():
    """size>10mb filters files larger than 10MB."""

def test_size_predicate_less_than():
    """size<1mb filters files smaller than 1MB."""

def test_extension_predicate():
    """ext:.pdf matches .pdf files."""

def test_name_predicate():
    """name:report matches files containing 'report'."""

def test_modified_before_predicate():
    """modified_before:2025-01-01 filters by modifiedTime."""

def test_owner_predicate():
    """owner:alice@company.com matches by owner email."""

# Expensive predicates
def test_shared_by_predicate_calls_permissions_api():
    """shared_by: triggers permissions.list call."""

# Evaluation order
def test_free_predicates_evaluated_first():
    """Free predicates short-circuit before expensive ones."""

def test_failing_free_predicate_skips_expensive():
    """If free predicate fails, expensive predicates are not called."""

# Cost estimation
def test_cost_estimation_with_expensive_predicate():
    """shared_by on 200 items estimates 200 API calls."""

def test_filter_confirm_required_for_high_cost():
    """>100 estimated calls without --filter-confirm raises FilterCostError."""

def test_filter_confirm_not_required_for_dry_run():
    """--dry-run mode skips the cost guard."""

# Parser
def test_parse_size_expression():
    """'size>10mb' parses to SizePredicate."""

def test_parse_extension_expression():
    """'ext:.pdf' parses to ExtensionPredicate."""

def test_parse_invalid_expression():
    """Invalid filter expression raises ConfigError."""

# Dry-run interaction
def test_dry_run_shows_conditional_items():
    """Expensive predicates in dry-run mark items as 'conditionally included'."""
```

---

## Verification Checklist

- [ ] `--query "mimeType = 'application/pdf'"` only fetches PDFs from API
- [ ] `--filter "size>10mb"` excludes small files locally
- [ ] `--filter "shared_by:user@email"` triggers permissions lookup per file
- [ ] Cost warning shown for >100 estimated API calls
- [ ] `--filter-confirm` suppresses cost warning
- [ ] `--dry-run` with `--filter` shows conditional inclusion
- [ ] Free predicates evaluated before expensive ones
- [ ] Invalid filter expression gives clear error message
- [ ] `pytest tests/test_filters.py` — all pass
