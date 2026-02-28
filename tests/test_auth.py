"""Tests for gdrive_dl.auth — OAuth flow, token lifecycle, browser selection, Drive about."""

import json
import os
import stat
from unittest.mock import MagicMock, patch

import pytest

from gdrive_dl.auth import (
    _authenticate_oauth,
    _resolve_browser,
    _save_token,
    _scopes_sufficient,
    extract_folder_id,
    format_drive_about,
    get_drive_about,
)
from gdrive_dl.constants import SCOPES
from gdrive_dl.exceptions import AuthError, SourceNotFoundError

# ---------------------------------------------------------------------------
# Scope checking
# ---------------------------------------------------------------------------


class TestScopesSufficient:
    """_scopes_sufficient checks whether cached scopes cover the required set."""

    def test_returns_true_for_exact_match(self):
        assert _scopes_sufficient(SCOPES, SCOPES) is True

    def test_returns_true_for_superset(self):
        cached = SCOPES + ["https://www.googleapis.com/auth/drive.metadata.readonly"]
        assert _scopes_sufficient(cached, SCOPES) is True

    def test_returns_false_for_empty(self):
        assert _scopes_sufficient([], SCOPES) is False

    def test_returns_false_for_none(self):
        assert _scopes_sufficient(None, SCOPES) is False

    def test_returns_false_for_subset(self):
        cached = ["https://www.googleapis.com/auth/drive.metadata.readonly"]
        assert _scopes_sufficient(cached, SCOPES) is False


# ---------------------------------------------------------------------------
# Browser selection
# ---------------------------------------------------------------------------


class TestResolveBrowser:
    """_resolve_browser maps user input to webbrowser-compatible name."""

    def test_none_returns_none(self):
        assert _resolve_browser(None) is None

    def test_explicit_chrome(self):
        assert _resolve_browser("chrome") == "chrome"

    def test_explicit_firefox(self):
        assert _resolve_browser("firefox") == "firefox"

    def test_auto_returns_none_as_fallback(self):
        """'auto' falls back to None (system default) when Chrome is not found."""
        with patch("webbrowser.get", side_effect=Exception("not found")):
            result = _resolve_browser("auto")
            assert result is None

    def test_respects_browser_env_var(self, monkeypatch):
        """BROWSER env var is checked when browser_arg is None."""
        monkeypatch.setenv("BROWSER", "firefox")
        assert _resolve_browser(None) == "firefox"


# ---------------------------------------------------------------------------
# Source ID extraction
# ---------------------------------------------------------------------------


class TestExtractFolderId:
    """extract_folder_id parses folder IDs from URLs, raw IDs, and 'root'."""

    def test_from_root_keyword(self):
        assert extract_folder_id("root") == "root"

    def test_from_raw_id(self):
        assert extract_folder_id("1ABC123xyz") == "1ABC123xyz"

    def test_from_full_url(self):
        url = "https://drive.google.com/drive/folders/1ABC123xyz"
        assert extract_folder_id(url) == "1ABC123xyz"

    def test_from_url_with_query_params(self):
        url = "https://drive.google.com/drive/folders/1ABC123xyz?usp=sharing"
        assert extract_folder_id(url) == "1ABC123xyz"

    def test_from_url_with_fragment(self):
        url = "https://drive.google.com/drive/folders/1ABC123xyz#section"
        assert extract_folder_id(url) == "1ABC123xyz"

    def test_invalid_url_raises_error(self):
        with pytest.raises(SourceNotFoundError):
            extract_folder_id("https://docs.google.com/document/d/1ABC")

    def test_empty_string_raises_error(self):
        with pytest.raises(SourceNotFoundError):
            extract_folder_id("")


# ---------------------------------------------------------------------------
# Token lifecycle
# ---------------------------------------------------------------------------


class TestAuthenticateOAuth:
    """_authenticate_oauth handles the full token lifecycle."""

    def _make_mock_creds(self, valid=True, expired=False, has_refresh=True, scopes=None):
        creds = MagicMock()
        creds.valid = valid
        creds.expired = expired
        creds.refresh_token = "refresh_tok" if has_refresh else None
        creds.scopes = scopes if scopes is not None else list(SCOPES)
        creds.to_json.return_value = json.dumps({"token": "fake", "scopes": list(SCOPES)})
        return creds

    @patch("gdrive_dl.auth.InstalledAppFlow")
    @patch("gdrive_dl.auth.Credentials")
    def test_valid_cached_token_reused(self, mock_creds_cls, mock_flow_cls, tmp_path):
        """When token.json has valid credentials, no browser flow is triggered."""
        token_file = tmp_path / "token.json"
        token_file.write_text(json.dumps({"token": "cached"}))

        valid_creds = self._make_mock_creds(valid=True, expired=False)
        mock_creds_cls.from_authorized_user_info.return_value = valid_creds

        result = _authenticate_oauth(
            credentials_file=str(tmp_path / "creds.json"),
            token_file=str(token_file),
            browser=None,
            no_browser=False,
        )

        assert result is valid_creds
        mock_flow_cls.from_client_secrets_file.assert_not_called()

    @patch("gdrive_dl.auth.Request")
    @patch("gdrive_dl.auth.InstalledAppFlow")
    @patch("gdrive_dl.auth.Credentials")
    def test_expired_token_refreshed_silently(
        self, mock_creds_cls, mock_flow_cls, mock_request_cls, tmp_path
    ):
        """When token is expired but has refresh token, creds.refresh() is called."""
        token_file = tmp_path / "token.json"
        token_file.write_text(json.dumps({"token": "expired"}))

        expired_creds = self._make_mock_creds(valid=False, expired=True, has_refresh=True)
        # After refresh, the creds become valid
        expired_creds.refresh.side_effect = lambda req: setattr(expired_creds, "valid", True)
        mock_creds_cls.from_authorized_user_info.return_value = expired_creds

        result = _authenticate_oauth(
            credentials_file=str(tmp_path / "creds.json"),
            token_file=str(token_file),
            browser=None,
            no_browser=False,
        )

        expired_creds.refresh.assert_called_once()
        assert result is expired_creds

    @patch("gdrive_dl.auth.InstalledAppFlow")
    @patch("gdrive_dl.auth.Credentials")
    def test_missing_token_triggers_browser_flow(self, mock_creds_cls, mock_flow_cls, tmp_path):
        """When token.json doesn't exist, InstalledAppFlow.run_local_server() is called."""
        creds_file = tmp_path / "creds.json"
        creds_file.write_text(json.dumps({"installed": {"client_id": "test"}}))
        token_file = tmp_path / "token.json"  # does not exist

        new_creds = self._make_mock_creds(valid=True)
        mock_flow_cls.from_client_secrets_file.return_value.run_local_server.return_value = (
            new_creds
        )

        result = _authenticate_oauth(
            credentials_file=str(creds_file),
            token_file=str(token_file),
            browser=None,
            no_browser=False,
        )

        mock_flow_cls.from_client_secrets_file.assert_called_once()
        assert result is new_creds

    @patch("gdrive_dl.auth.Request")
    @patch("gdrive_dl.auth.InstalledAppFlow")
    @patch("gdrive_dl.auth.Credentials")
    def test_refresh_failure_triggers_browser_flow(
        self, mock_creds_cls, mock_flow_cls, mock_request_cls, tmp_path
    ):
        """When refresh fails (revoked token), full browser flow runs."""
        token_file = tmp_path / "token.json"
        token_file.write_text(json.dumps({"token": "revoked"}))
        creds_file = tmp_path / "creds.json"
        creds_file.write_text(json.dumps({"installed": {"client_id": "test"}}))

        expired_creds = self._make_mock_creds(valid=False, expired=True, has_refresh=True)
        expired_creds.refresh.side_effect = Exception("Token revoked")
        mock_creds_cls.from_authorized_user_info.return_value = expired_creds

        new_creds = self._make_mock_creds(valid=True)
        mock_flow_cls.from_client_secrets_file.return_value.run_local_server.return_value = (
            new_creds
        )

        result = _authenticate_oauth(
            credentials_file=str(creds_file),
            token_file=str(token_file),
            browser=None,
            no_browser=False,
        )

        mock_flow_cls.from_client_secrets_file.assert_called_once()
        assert result is new_creds

    @patch("gdrive_dl.auth.InstalledAppFlow")
    @patch("gdrive_dl.auth.Credentials")
    def test_scope_mismatch_deletes_token_and_reauths(
        self, mock_creds_cls, mock_flow_cls, tmp_path
    ):
        """When cached scopes don't include drive.readonly, token is deleted."""
        token_file = tmp_path / "token.json"
        token_file.write_text(json.dumps({"token": "wrong_scope"}))
        creds_file = tmp_path / "creds.json"
        creds_file.write_text(json.dumps({"installed": {"client_id": "test"}}))

        wrong_scope_creds = self._make_mock_creds(
            valid=True,
            scopes=["https://www.googleapis.com/auth/drive.metadata.readonly"],
        )
        mock_creds_cls.from_authorized_user_info.return_value = wrong_scope_creds

        new_creds = self._make_mock_creds(valid=True)
        mock_flow_cls.from_client_secrets_file.return_value.run_local_server.return_value = (
            new_creds
        )

        result = _authenticate_oauth(
            credentials_file=str(creds_file),
            token_file=str(token_file),
            browser=None,
            no_browser=False,
        )

        # Token file should have been deleted and re-created by browser flow
        mock_flow_cls.from_client_secrets_file.assert_called_once()
        assert result is new_creds

    def test_credentials_file_missing_raises_auth_error(self, tmp_path):
        """Missing credentials.json raises AuthError with setup instructions."""
        with pytest.raises(AuthError, match="credentials"):
            _authenticate_oauth(
                credentials_file=str(tmp_path / "nonexistent.json"),
                token_file=str(tmp_path / "token.json"),
                browser=None,
                no_browser=False,
            )


# ---------------------------------------------------------------------------
# Token storage
# ---------------------------------------------------------------------------


class TestSaveToken:
    """_save_token writes token JSON with restricted permissions."""

    def test_token_saved_with_restricted_permissions(self, tmp_path):
        token_file = tmp_path / "token.json"
        creds = MagicMock()
        creds.to_json.return_value = json.dumps({"token": "secret"})

        _save_token(creds, str(token_file))

        assert token_file.exists()
        mode = stat.S_IMODE(os.stat(token_file).st_mode)
        assert mode == 0o600

    def test_creates_parent_directory(self, tmp_path):
        token_file = tmp_path / "subdir" / "token.json"
        creds = MagicMock()
        creds.to_json.return_value = json.dumps({"token": "secret"})

        _save_token(creds, str(token_file))

        assert token_file.exists()


# ---------------------------------------------------------------------------
# Drive about
# ---------------------------------------------------------------------------


class TestGetDriveAbout:
    """get_drive_about calls about.get with correct fields."""

    def test_returns_user_and_quota(self):
        mock_service = MagicMock()
        mock_service.about.return_value.get.return_value.execute.return_value = {
            "user": {"displayName": "Alice", "emailAddress": "alice@co.com"},
            "storageQuota": {
                "limit": "15000000000",
                "usage": "12400000000",
                "usageInDrive": "10100000000",
                "usageInDriveTrash": "1200000000",
            },
        }

        result = get_drive_about(mock_service)

        assert result["user"]["emailAddress"] == "alice@co.com"
        assert "storageQuota" in result
        mock_service.about.return_value.get.assert_called_once()


class TestFormatDriveAbout:
    """format_drive_about produces human-readable output."""

    def test_normal_quota(self):
        about = {
            "user": {"displayName": "Alice Chen", "emailAddress": "alice@company.com"},
            "storageQuota": {
                "limit": "16106127360",
                "usage": "12884901888",
                "usageInDrive": "10737418240",
                "usageInDriveTrash": "1073741824",
            },
        }
        output = format_drive_about(about)
        assert "alice@company.com" in output
        assert "Alice Chen" in output

    def test_unlimited_quota(self):
        about = {
            "user": {"displayName": "Bob", "emailAddress": "bob@enterprise.com"},
            "storageQuota": {
                "usage": "5000000000",
                "usageInDrive": "4000000000",
                "usageInDriveTrash": "500000000",
            },
        }
        output = format_drive_about(about)
        assert "bob@enterprise.com" in output
        assert "unlimited" in output.lower() or "Unlimited" in output
