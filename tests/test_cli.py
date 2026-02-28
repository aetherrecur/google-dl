"""Tests for gdrive_dl.cli — CLI integration via click.testing.CliRunner."""

from click.testing import CliRunner

from gdrive_dl.cli import main


class TestCliBasics:
    """Basic CLI behavior: version, help, option validation."""

    def test_version_flag(self):
        """--version prints version and exits 0."""
        runner = CliRunner()
        result = runner.invoke(main, ["--version"])

        assert result.exit_code == 0
        assert "gdrive-dl" in result.output

    def test_help_includes_key_options(self):
        """--help lists all documented options."""
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])

        assert result.exit_code == 0
        # Core options
        assert "--credentials" in result.output
        assert "--token" in result.output
        assert "--output" in result.output
        assert "--dry-run" in result.output
        # Phase 4+
        assert "--query" in result.output
        assert "--filter" in result.output
        # Phase 6+
        assert "--permissions" in result.output
        assert "--comments" in result.output
        assert "--metadata" in result.output
        assert "--revisions" in result.output
        # Phase 7+
        assert "--export-format" in result.output
        # Phase 8+
        assert "--report" in result.output
        assert "--report-format" in result.output
        # Phase 9+
        assert "--shared-drives" in result.output
        # Phase 10
        assert "--no-verify" in result.output

    def test_no_verify_option_accepted(self):
        """--no-verify is accepted without error (though source is missing)."""
        runner = CliRunner()
        # Will fail because no source argument, but should not fail on the option itself
        result = runner.invoke(main, ["--no-verify", "--help"])

        assert result.exit_code == 0

    def test_missing_source_shows_error(self):
        """Missing SOURCE argument produces an error."""
        runner = CliRunner()
        result = runner.invoke(main, [])

        assert result.exit_code != 0
