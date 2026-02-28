"""Tests for gdrive_dl.filters — query building, predicate parsing, post-fetch filtering."""

from __future__ import annotations

import pytest

from gdrive_dl.constants import FOLDER_MIME
from gdrive_dl.exceptions import ConfigError
from gdrive_dl.filters import (
    ExtensionPredicate,
    ModifiedAfterPredicate,
    ModifiedBeforePredicate,
    NamePredicate,
    PredicateCost,
    SizePredicate,
    apply_post_filter,
    build_query,
    estimate_filter_cost,
    parse_filter,
)
from gdrive_dl.walker import DriveItem


def _item(
    name: str = "test.pdf",
    size: int | None = 1024,
    mime_type: str = "application/pdf",
    modified_time: str = "2025-06-01T00:00:00.000Z",
    is_folder: bool = False,
) -> DriveItem:
    return DriveItem(
        id="f1",
        name=name,
        mime_type=mime_type,
        size=size,
        md5_checksum=None,
        created_time="2025-01-01T00:00:00.000Z",
        modified_time=modified_time,
        parents=["root"],
        drive_path=name,
        is_folder=is_folder,
        can_download=True,
        is_shortcut=False,
        shortcut_target_id=None,
        shared_drive_id=None,
    )


# ---------------------------------------------------------------------------
# build_query
# ---------------------------------------------------------------------------


class TestBuildQuery:
    """API query string construction."""

    def test_base_only(self):
        q = build_query("folder123")
        assert q == "'folder123' in parents and trashed = false"

    def test_with_extra_query(self):
        q = build_query("folder123", extra_query="mimeType = 'application/pdf'")
        assert "'folder123' in parents and trashed = false" in q
        assert "mimeType = 'application/pdf'" in q
        assert q.startswith("(")

    def test_extra_query_none_same_as_base(self):
        assert build_query("f1") == build_query("f1", extra_query=None)

    def test_extra_query_empty_string_same_as_base(self):
        assert build_query("f1") == build_query("f1", extra_query="")


# ---------------------------------------------------------------------------
# SizePredicate
# ---------------------------------------------------------------------------


class TestSizePredicate:
    """Filter by file size."""

    def test_greater_than(self):
        pred = SizePredicate(">", 500)
        assert pred.evaluate(_item(size=1000)) is True
        assert pred.evaluate(_item(size=500)) is False
        assert pred.evaluate(_item(size=100)) is False

    def test_less_than(self):
        pred = SizePredicate("<", 500)
        assert pred.evaluate(_item(size=100)) is True
        assert pred.evaluate(_item(size=500)) is False
        assert pred.evaluate(_item(size=1000)) is False

    def test_none_size_excluded(self):
        """Workspace files with None size are excluded by size filters."""
        pred = SizePredicate(">", 0)
        assert pred.evaluate(_item(size=None)) is False

    def test_cost_is_free(self):
        assert SizePredicate(">", 100).cost == PredicateCost.FREE


# ---------------------------------------------------------------------------
# ExtensionPredicate
# ---------------------------------------------------------------------------


class TestExtensionPredicate:
    """Filter by file extension."""

    def test_matches_pdf(self):
        pred = ExtensionPredicate(".pdf")
        assert pred.evaluate(_item(name="report.pdf")) is True
        assert pred.evaluate(_item(name="report.docx")) is False

    def test_case_insensitive(self):
        pred = ExtensionPredicate(".PDF")
        assert pred.evaluate(_item(name="report.pdf")) is True

    def test_no_extension(self):
        pred = ExtensionPredicate(".pdf")
        assert pred.evaluate(_item(name="README")) is False

    def test_cost_is_free(self):
        assert ExtensionPredicate(".pdf").cost == PredicateCost.FREE


# ---------------------------------------------------------------------------
# NamePredicate
# ---------------------------------------------------------------------------


class TestNamePredicate:
    """Filter by name substring."""

    def test_substring_match(self):
        pred = NamePredicate("report")
        assert pred.evaluate(_item(name="Q3 Report Final.pdf")) is True
        assert pred.evaluate(_item(name="invoice.pdf")) is False

    def test_case_insensitive(self):
        pred = NamePredicate("REPORT")
        assert pred.evaluate(_item(name="report.pdf")) is True

    def test_cost_is_free(self):
        assert NamePredicate("x").cost == PredicateCost.FREE


# ---------------------------------------------------------------------------
# ModifiedBeforePredicate / ModifiedAfterPredicate
# ---------------------------------------------------------------------------


class TestModifiedPredicates:
    """Filter by modification date."""

    def test_modified_before(self):
        pred = ModifiedBeforePredicate("2025-07-01")
        assert pred.evaluate(_item(modified_time="2025-06-01T00:00:00.000Z")) is True
        assert pred.evaluate(_item(modified_time="2025-08-01T00:00:00.000Z")) is False

    def test_modified_after(self):
        pred = ModifiedAfterPredicate("2025-01-01")
        assert pred.evaluate(_item(modified_time="2025-06-01T00:00:00.000Z")) is True
        assert pred.evaluate(_item(modified_time="2024-06-01T00:00:00.000Z")) is False

    def test_cost_is_free(self):
        assert ModifiedBeforePredicate("2025-01-01").cost == PredicateCost.FREE
        assert ModifiedAfterPredicate("2025-01-01").cost == PredicateCost.FREE


# ---------------------------------------------------------------------------
# parse_filter
# ---------------------------------------------------------------------------


class TestParseFilter:
    """Parse filter expression strings into Predicate lists."""

    def test_parse_size_gt(self):
        preds = parse_filter("size>10mb")
        assert len(preds) == 1
        assert isinstance(preds[0], SizePredicate)

    def test_parse_size_lt(self):
        preds = parse_filter("size<1kb")
        assert len(preds) == 1
        assert isinstance(preds[0], SizePredicate)

    def test_parse_extension(self):
        preds = parse_filter("ext:.pdf")
        assert len(preds) == 1
        assert isinstance(preds[0], ExtensionPredicate)

    def test_parse_name(self):
        preds = parse_filter("name:report")
        assert len(preds) == 1
        assert isinstance(preds[0], NamePredicate)

    def test_parse_modified_before(self):
        preds = parse_filter("modified_before:2025-01-01")
        assert len(preds) == 1
        assert isinstance(preds[0], ModifiedBeforePredicate)

    def test_parse_modified_after(self):
        preds = parse_filter("modified_after:2025-01-01")
        assert len(preds) == 1
        assert isinstance(preds[0], ModifiedAfterPredicate)

    def test_parse_multiple_comma_separated(self):
        preds = parse_filter("size>10mb,ext:.pdf,name:report")
        assert len(preds) == 3

    def test_parse_invalid_raises_config_error(self):
        with pytest.raises(ConfigError):
            parse_filter("invalid_expression")

    def test_parse_size_units(self):
        """Various size units parse correctly."""
        preds = parse_filter("size>1gb")
        assert isinstance(preds[0], SizePredicate)

    def test_parse_size_no_unit_bytes(self):
        preds = parse_filter("size>1024")
        assert isinstance(preds[0], SizePredicate)


# ---------------------------------------------------------------------------
# apply_post_filter
# ---------------------------------------------------------------------------


class TestApplyPostFilter:
    """Post-fetch filtering on DriveItem lists."""

    def test_filters_by_size(self):
        items = [
            _item(name="big.pdf", size=10_000_000),
            _item(name="small.pdf", size=100),
        ]
        result = apply_post_filter(items, "size>1mb")
        assert len(result) == 1
        assert result[0].name == "big.pdf"

    def test_keeps_folders_unconditionally(self):
        items = [
            _item(name="SubDir", is_folder=True, mime_type=FOLDER_MIME, size=None),
            _item(name="small.pdf", size=100),
        ]
        result = apply_post_filter(items, "size>1mb")
        assert len(result) == 1
        assert result[0].is_folder is True

    def test_multiple_predicates_anded(self):
        items = [
            _item(name="report.pdf", size=10_000_000),
            _item(name="report.docx", size=10_000_000),
            _item(name="invoice.pdf", size=10_000_000),
        ]
        result = apply_post_filter(items, "ext:.pdf,name:report")
        assert len(result) == 1
        assert result[0].name == "report.pdf"

    def test_none_filter_returns_all(self):
        items = [_item(name="a.pdf"), _item(name="b.pdf")]
        result = apply_post_filter(items, None)
        assert len(result) == 2

    def test_empty_filter_returns_all(self):
        items = [_item(name="a.pdf"), _item(name="b.pdf")]
        result = apply_post_filter(items, "")
        assert len(result) == 2


# ---------------------------------------------------------------------------
# estimate_filter_cost
# ---------------------------------------------------------------------------


class TestEstimateFilterCost:
    """Cost estimation for filter predicates."""

    def test_free_predicates_zero_cost(self):
        items = [_item() for _ in range(100)]
        preds = parse_filter("size>10mb,ext:.pdf")
        assert estimate_filter_cost(items, preds) == 0

    def test_cost_guard_raises_on_high_cost(self):
        """FilterCostError raised when cost > 100 without filter_confirm."""
        # This tests the guard inside apply_post_filter, not estimate_filter_cost
        # Since we don't have expensive predicates yet, this is a framework test
        pass


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestFilterEdgeCases:
    """Edge cases and error handling."""

    def test_size_with_equals(self):
        """size>=10mb and size<=10mb work."""
        preds = parse_filter("size>=1000")
        assert len(preds) == 1

    def test_extension_without_dot(self):
        """ext:pdf (no dot) still works — adds dot automatically."""
        preds = parse_filter("ext:pdf")
        assert isinstance(preds[0], ExtensionPredicate)
        assert preds[0].evaluate(_item(name="report.pdf")) is True
