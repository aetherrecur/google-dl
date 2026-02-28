"""Two-tier filtering: API query pushdown and post-fetch predicate evaluation."""

from __future__ import annotations

import enum
import logging
import re
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import TYPE_CHECKING

from gdrive_dl.exceptions import ConfigError, FilterCostError

if TYPE_CHECKING:
    from gdrive_dl.walker import DriveItem

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cost classification
# ---------------------------------------------------------------------------


class PredicateCost(enum.Enum):
    """How expensive a predicate is to evaluate."""

    FREE = "free"
    PER_FILE = "per_file"


# ---------------------------------------------------------------------------
# Predicate base + concrete classes
# ---------------------------------------------------------------------------


class Predicate(ABC):
    """Base class for filter predicates."""

    cost: PredicateCost = PredicateCost.FREE

    @abstractmethod
    def evaluate(self, item: DriveItem) -> bool:
        """Return True if *item* passes this predicate."""


class SizePredicate(Predicate):
    """Filter by file size in bytes."""

    def __init__(self, op: str, value_bytes: int) -> None:
        self.op = op
        self.value_bytes = value_bytes

    def evaluate(self, item: DriveItem) -> bool:
        if item.size is None:
            return False
        if self.op == ">":
            return item.size > self.value_bytes
        if self.op == "<":
            return item.size < self.value_bytes
        if self.op == ">=":
            return item.size >= self.value_bytes
        if self.op == "<=":
            return item.size <= self.value_bytes
        return False  # pragma: no cover


class ExtensionPredicate(Predicate):
    """Filter by file extension (case-insensitive)."""

    def __init__(self, ext: str) -> None:
        self.ext = ext.lower() if ext.startswith(".") else f".{ext.lower()}"

    def evaluate(self, item: DriveItem) -> bool:
        return item.name.lower().endswith(self.ext)


class NamePredicate(Predicate):
    """Filter by name substring (case-insensitive)."""

    def __init__(self, pattern: str) -> None:
        self.pattern = pattern.lower()

    def evaluate(self, item: DriveItem) -> bool:
        return self.pattern in item.name.lower()


class ModifiedBeforePredicate(Predicate):
    """Include files modified before a date (YYYY-MM-DD)."""

    def __init__(self, cutoff: str) -> None:
        self.cutoff = cutoff

    def evaluate(self, item: DriveItem) -> bool:
        return item.modified_time[:10] < self.cutoff


class ModifiedAfterPredicate(Predicate):
    """Include files modified after a date (YYYY-MM-DD)."""

    def __init__(self, cutoff: str) -> None:
        self.cutoff = cutoff

    def evaluate(self, item: DriveItem) -> bool:
        return item.modified_time[:10] > self.cutoff


# ---------------------------------------------------------------------------
# Query builder (Tier 1)
# ---------------------------------------------------------------------------


def build_query(folder_id: str, extra_query: str | None = None) -> str:
    """Build the ``q`` parameter for ``files.list``.

    The base query restricts to *folder_id*'s children and excludes trashed
    items.  When *extra_query* is provided it is ANDed with the base.
    """
    base = f"'{folder_id}' in parents and trashed = false"
    if extra_query:
        return f"({base}) and ({extra_query})"
    return base


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

_SIZE_RE = re.compile(
    r"^size\s*(>=|<=|>|<)\s*(\d+(?:\.\d+)?)\s*(kb|mb|gb|b)?$",
    re.IGNORECASE,
)
_SIZE_UNITS = {"b": 1, "kb": 1_000, "mb": 1_000_000, "gb": 1_000_000_000}


def _parse_size(value: str, unit: str | None) -> int:
    multiplier = _SIZE_UNITS.get((unit or "b").lower(), 1)
    return int(float(value) * multiplier)


def parse_filter(expression: str) -> list[Predicate]:
    """Parse a comma-separated filter expression into a list of predicates.

    Raises :class:`ConfigError` on unrecognised syntax.
    """
    predicates: list[Predicate] = []

    for token in expression.split(","):
        token = token.strip()
        if not token:
            continue

        # size>10mb / size<1kb / size>=500
        m = _SIZE_RE.match(token)
        if m:
            op, val, unit = m.group(1), m.group(2), m.group(3)
            predicates.append(SizePredicate(op, _parse_size(val, unit)))
            continue

        # ext:.pdf
        if token.startswith("ext:"):
            ext = token[4:].strip()
            if not ext:
                raise ConfigError(f"Empty extension in filter: {token!r}")
            predicates.append(ExtensionPredicate(ext))
            continue

        # name:report
        if token.startswith("name:"):
            pattern = token[5:].strip()
            if not pattern:
                raise ConfigError(f"Empty name pattern in filter: {token!r}")
            predicates.append(NamePredicate(pattern))
            continue

        # modified_before:2025-01-01
        if token.startswith("modified_before:"):
            cutoff = token[len("modified_before:") :].strip()
            if not cutoff:
                raise ConfigError(f"Empty date in filter: {token!r}")
            predicates.append(ModifiedBeforePredicate(cutoff))
            continue

        # modified_after:2025-01-01
        if token.startswith("modified_after:"):
            cutoff = token[len("modified_after:") :].strip()
            if not cutoff:
                raise ConfigError(f"Empty date in filter: {token!r}")
            predicates.append(ModifiedAfterPredicate(cutoff))
            continue

        raise ConfigError(f"Unrecognised filter expression: {token!r}")

    return predicates


# ---------------------------------------------------------------------------
# Cost estimation
# ---------------------------------------------------------------------------


def estimate_filter_cost(
    items: Sequence[DriveItem],
    predicates: Sequence[Predicate],
) -> int:
    """Estimate additional API calls needed for expensive predicates.

    Free predicates cost 0.  Each PER_FILE predicate costs 1 call per
    non-folder item.
    """
    per_file_count = sum(1 for p in predicates if p.cost == PredicateCost.PER_FILE)
    if per_file_count == 0:
        return 0
    file_count = sum(1 for i in items if not i.is_folder)
    return per_file_count * file_count


# ---------------------------------------------------------------------------
# Post-fetch filter application (Tier 2)
# ---------------------------------------------------------------------------


def apply_post_filter(
    items: list[DriveItem],
    filter_expr: str | None,
    filter_confirm: bool = False,
) -> list[DriveItem]:
    """Apply post-fetch filter to *items*, returning matching items.

    Folders are always kept (filtering only applies to files).
    Raises :class:`FilterCostError` if estimated API calls exceed 100
    and *filter_confirm* is False.
    """
    if not filter_expr:
        return items

    predicates = parse_filter(filter_expr)
    if not predicates:
        return items

    # Cost guard
    cost = estimate_filter_cost(items, predicates)
    if (cost > 100) and (not filter_confirm):
        raise FilterCostError(
            f"Filter would require ~{cost} additional API calls. "
            f"Use --filter-confirm to proceed."
        )

    # Partition by cost
    free = [p for p in predicates if p.cost == PredicateCost.FREE]
    expensive = [p for p in predicates if p.cost == PredicateCost.PER_FILE]

    result: list[DriveItem] = []
    for item in items:
        # Always keep folders
        if item.is_folder:
            result.append(item)
            continue

        # Evaluate free predicates first (short-circuit)
        if not all(p.evaluate(item) for p in free):
            continue

        # Evaluate expensive predicates
        if not all(p.evaluate(item) for p in expensive):
            continue

        result.append(item)

    filtered_count = len(items) - len(result)
    if filtered_count > 0:
        logger.info("Post-filter excluded %d items", filtered_count)

    return result
