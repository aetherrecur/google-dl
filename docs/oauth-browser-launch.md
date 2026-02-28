# Research: Auto-Launching Google OAuth Sign-In via Chrome Browser

## Table of Contents
1. [How OAuth Browser Launch Works Internally](#1-how-oauth-browser-launch-works-internally)
2. [The `browser` Parameter (Simplest Approach)](#2-the-browser-parameter-simplest-approach)
3. [Cross-Platform Chrome Detection & Registration](#3-cross-platform-chrome-detection--registration)
4. [The `BROWSER` Environment Variable](#4-the-browser-environment-variable)
5. [Full Implementation: Chrome-Targeted OAuth Flow](#5-full-implementation-chrome-targeted-oauth-flow)
6. [Edge Cases & Troubleshooting](#6-edge-cases--troubleshooting)
7. [Summary of All Approaches](#7-summary-of-all-approaches)

---

## 1. How OAuth Browser Launch Works Internally

### The Call Chain

When you call `flow.run_local_server()`, the following happens internally:

```
Your code
  └─► InstalledAppFlow.run_local_server()
        ├─► Starts a local WSGI server on localhost:8080
        ├─► Builds the Google authorization URL
        ├─► Calls webbrowser.get(browser).open(auth_url, new=1, autoraise=True)
        │     └─► Python's webbrowser module selects and launches a browser
        ├─► Waits for the redirect callback on the local server
        ├─► Exchanges the authorization code for tokens
        └─► Returns google.oauth2.credentials.Credentials
```

### Source Code (from `google-auth-oauthlib`)

The relevant lines from the actual library source (`google_auth_oauthlib/flow.py`):

```python
def run_local_server(
    self,
    host="localhost",
    bind_addr=None,
    port=8080,
    authorization_prompt_message=_DEFAULT_AUTH_PROMPT_MESSAGE,
    success_message=_DEFAULT_WEB_SUCCESS_MESSAGE,
    open_browser=True,
    redirect_uri_trailing_slash=True,
    timeout_seconds=None,
    token_audience=None,
    browser=None,          # ◄── THIS IS THE KEY PARAMETER
    **kwargs
):
    # ... sets up local server, builds auth URL ...
    if open_browser:
        # if browser is None it defaults to default browser
        webbrowser.get(browser).open(auth_url, new=1, autoraise=True)
    # ... waits for callback, exchanges token ...
```

The `browser` parameter is passed directly to Python's `webbrowser.get()`. When `None`, it uses the system default browser. When set to a browser name string, it targets that specific browser.

### Python `webbrowser` Module Behavior

`webbrowser.get(using)` works as follows:
- `None` → returns the default browser controller
- A registered name like `'chrome'` → returns the controller for that browser
- A path containing `%s` → uses it as a command template (URL substituted for `%s`)

The module maintains an internal registry of browser names, populated by `register_standard_browsers()` at first use. The registry varies by platform.

---

## 2. The `browser` Parameter (Simplest Approach)

### Direct Usage

The simplest way to force Chrome is to pass `browser='chrome'` directly:

```python
from google_auth_oauthlib.flow import InstalledAppFlow

flow = InstalledAppFlow.from_client_secrets_file(
    'credentials.json',
    scopes=['https://www.googleapis.com/auth/drive.readonly']
)

creds = flow.run_local_server(
    port=0,           # Use any available port
    browser='chrome'  # ◄── Force Chrome
)
```

### Platform-Specific Browser Names

The `webbrowser` module registers different names for Chrome depending on the platform:

| Platform | Registered Name(s) | How It's Registered |
|----------|-------------------|---------------------|
| **macOS** | `'chrome'` | `MacOSXOSAScript('google chrome')` — uses AppleScript to launch by app name |
| **Windows** | `'chrome'` | `BackgroundBrowser('chrome')` — requires `chrome` to be in PATH (via `shutil.which`) |
| **Linux** | `'google-chrome'`, `'chrome'`, `'chromium'`, `'chromium-browser'` | `BackgroundBrowser(name)` — checks PATH for each executable name |

### What Can Go Wrong

- **macOS**: `'chrome'` works reliably because macOS uses AppleScript (`open -a "Google Chrome"`) regardless of PATH.
- **Windows**: `'chrome'` only works if `chrome.exe` is in the system PATH. On many Windows machines, it is *not* in PATH by default — the `webbrowser` module falls back to `windows-default` (which may be Edge).
- **Linux**: The executable name varies by distribution. Debian/Ubuntu use `google-chrome` or `google-chrome-stable`. Some distros use `chromium-browser`.

---

## 3. Cross-Platform Chrome Detection & Registration

### Robust Chrome Detection

For production code, detect Chrome's actual location before attempting to use it:

```python
import sys
import os
import shutil
import webbrowser

def find_chrome_path():
    """Find the Chrome executable path on the current platform."""
    if sys.platform == 'darwin':
        # macOS: Chrome is always at this path if installed
        chrome_app = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
        if os.path.exists(chrome_app):
            return chrome_app
        return None

    elif sys.platform == 'win32':
        # Windows: Check common installation paths
        possible_paths = [
            os.path.join(os.environ.get('PROGRAMFILES', 'C:\\Program Files'),
                         'Google', 'Chrome', 'Application', 'chrome.exe'),
            os.path.join(os.environ.get('PROGRAMFILES(X86)', 'C:\\Program Files (x86)'),
                         'Google', 'Chrome', 'Application', 'chrome.exe'),
            os.path.join(os.environ.get('LOCALAPPDATA', ''),
                         'Google', 'Chrome', 'Application', 'chrome.exe'),
        ]
        for path in possible_paths:
            if os.path.exists(path):
                return path
        # Also check PATH
        return shutil.which('chrome')

    else:
        # Linux/BSD: Check common executable names in PATH
        for name in ('google-chrome', 'google-chrome-stable', 'chrome',
                     'chromium', 'chromium-browser'):
            path = shutil.which(name)
            if path:
                return path
        return None
```

### Registering Chrome Before OAuth

If Chrome isn't auto-detected by `webbrowser`, register it manually:

```python
def ensure_chrome_registered():
    """Ensure 'chrome' is registered in the webbrowser module."""
    # First, try the built-in registration
    try:
        webbrowser.get('chrome')
        return 'chrome'  # Already registered and available
    except webbrowser.Error:
        pass

    # Fall back to manual detection and registration
    chrome_path = find_chrome_path()
    if chrome_path is None:
        return None  # Chrome not found

    if sys.platform == 'win32':
        # On Windows, register with %s for URL substitution
        webbrowser.register('chrome', None,
                            webbrowser.BackgroundBrowser(chrome_path))
    elif sys.platform == 'darwin':
        # On macOS, the built-in 'chrome' should work; register as fallback
        webbrowser.register('chrome', None,
                            webbrowser.BackgroundBrowser(chrome_path))
    else:
        # Linux
        webbrowser.register('chrome', None,
                            webbrowser.BackgroundBrowser(chrome_path))

    return 'chrome'
```

### Using with OAuth

```python
browser_name = ensure_chrome_registered()

creds = flow.run_local_server(
    port=0,
    browser=browser_name,  # 'chrome' or None (falls back to default)
)
```

---

## 4. The `BROWSER` Environment Variable

### How It Works

Python's `webbrowser` module checks the `BROWSER` environment variable *before* consulting platform defaults. This provides a way to control browser selection without modifying code.

**Format:** A colon-separated (`os.pathsep`) list of browser names or commands.

```bash
# Set Chrome as preferred (Linux/macOS)
export BROWSER=google-chrome

# Set Chrome as preferred (Windows CMD)
set BROWSER=chrome

# Use a full path with %s placeholder for the URL
export BROWSER='/usr/bin/google-chrome-stable %s'

# Try Chrome first, fall back to Firefox
export BROWSER=google-chrome:firefox
```

### Setting It Programmatically

You can set `BROWSER` before the OAuth flow starts, which affects `webbrowser.open()` without needing the `browser` parameter:

```python
import os

# Force Chrome via environment variable
chrome_path = find_chrome_path()
if chrome_path:
    os.environ['BROWSER'] = chrome_path + ' %s'

# Now run_local_server() will use Chrome even without browser= parameter
creds = flow.run_local_server(port=0)
```

### When to Use This Approach

The `BROWSER` environment variable is useful when:
- You want to control the browser without modifying library code
- You're calling third-party code that uses `webbrowser.open()` internally
- You want users to configure their browser preference externally (e.g., via a `.env` file)

However, the `browser` parameter on `run_local_server()` is more explicit and should be preferred for direct use.

---

## 5. Full Implementation: Chrome-Targeted OAuth Flow

### Complete Working Example

```python
"""
Google Drive OAuth 2.0 authentication with Chrome browser targeting.

Prerequisites:
  pip install google-api-python-client google-auth-oauthlib google-auth-httplib2
  Place credentials.json (from Google Cloud Console) in the working directory.
"""

import os
import sys
import shutil
import webbrowser
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
CREDENTIALS_FILE = 'credentials.json'
TOKEN_FILE = 'token.json'


def find_chrome_path():
    """Detect Chrome's executable path cross-platform."""
    if sys.platform == 'darwin':
        path = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
        return path if os.path.exists(path) else None
    elif sys.platform == 'win32':
        candidates = [
            os.path.join(os.environ.get('PROGRAMFILES', r'C:\Program Files'),
                         'Google', 'Chrome', 'Application', 'chrome.exe'),
            os.path.join(os.environ.get('PROGRAMFILES(X86)', r'C:\Program Files (x86)'),
                         'Google', 'Chrome', 'Application', 'chrome.exe'),
            os.path.join(os.environ.get('LOCALAPPDATA', ''),
                         'Google', 'Chrome', 'Application', 'chrome.exe'),
        ]
        for p in candidates:
            if os.path.exists(p):
                return p
        return shutil.which('chrome')
    else:
        for name in ('google-chrome', 'google-chrome-stable', 'chrome',
                     'chromium', 'chromium-browser'):
            p = shutil.which(name)
            if p:
                return p
        return None


def get_chrome_browser_name():
    """
    Get a webbrowser-compatible browser name for Chrome.
    Registers Chrome manually if the built-in detection fails.
    Returns the browser name string, or None if Chrome is not available.
    """
    # Try the platform's pre-registered name first
    for name in ('chrome', 'google-chrome', 'chromium', 'chromium-browser'):
        try:
            webbrowser.get(name)
            return name
        except webbrowser.Error:
            continue

    # Manual detection and registration
    chrome_path = find_chrome_path()
    if chrome_path:
        webbrowser.register('chrome-custom', None,
                            webbrowser.BackgroundBrowser(chrome_path))
        return 'chrome-custom'

    return None


def authenticate(prefer_chrome=True):
    """
    Authenticate with Google Drive API.

    1. If a valid token.json exists, reuse it (refreshing if expired).
    2. Otherwise, launch the OAuth consent flow in a browser.

    Args:
        prefer_chrome: If True, attempt to open Chrome specifically.
                       Falls back to the system default if Chrome is unavailable.

    Returns:
        googleapiclient.discovery.Resource: An authorized Drive API service.
    """
    creds = None

    # --- Step 1: Try to load cached credentials ---
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    # --- Step 2: Refresh or re-authenticate ---
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            # Token exists but expired — refresh it silently (no browser needed)
            creds.refresh(Request())
        else:
            # No valid credentials — launch browser OAuth flow
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_FILE, SCOPES
            )

            # Determine browser to use
            browser_name = None
            if prefer_chrome:
                browser_name = get_chrome_browser_name()
                if browser_name:
                    print(f"Opening Chrome for authentication...")
                else:
                    print("Chrome not found. Using default browser...")

            creds = flow.run_local_server(
                port=0,              # Auto-select an available port
                browser=browser_name,  # Chrome or None (default browser)
                open_browser=True,
                authorization_prompt_message=(
                    'Please complete sign-in in your browser.\n'
                    'If the browser did not open, visit: {url}'
                ),
                success_message=(
                    'Authentication successful! You may close this tab.'
                ),
            )

        # --- Step 3: Save credentials for next run ---
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())

    return build('drive', 'v3', credentials=creds)


if __name__ == '__main__':
    service = authenticate(prefer_chrome=True)
    # Quick test: list 5 files
    results = service.files().list(
        pageSize=5,
        fields='files(id, name, mimeType)'
    ).execute()
    for f in results.get('files', []):
        print(f"  {f['name']}  ({f['mimeType']})")
```

### How It Works Step by Step

1. **Token check:** If `token.json` exists with valid credentials, no browser is needed at all.
2. **Token refresh:** If the token exists but is expired, `creds.refresh(Request())` silently obtains a new access token using the stored refresh token — no browser needed.
3. **Fresh authentication:** Only if there are no cached credentials does the browser open:
   - `get_chrome_browser_name()` tries the pre-registered `'chrome'` name first (fast, zero overhead).
   - If that fails, it calls `find_chrome_path()` to locate the Chrome executable and registers it manually.
   - The resulting name (or `None` for default browser) is passed to `run_local_server(browser=...)`.
4. **Local server:** A temporary WSGI server starts on a random port, Chrome opens the Google consent screen, the user grants permission, Google redirects to `localhost:<port>`, the server captures the auth code, and the library exchanges it for tokens.
5. **Token saved:** Credentials (including refresh token) are saved to `token.json` for future runs.

---

## 6. Edge Cases & Troubleshooting

### Chrome Not Found

If Chrome isn't installed or isn't detectable, the code falls back to the system default browser. The OAuth flow works identically regardless of which browser opens — the consent URL and callback mechanism are browser-agnostic.

### Port Conflicts

`port=0` tells `run_local_server` to pick any available port automatically. If you hardcode a port (e.g., `port=8080`), you risk conflicts with other applications. When using `port=0`, the redirect URI is dynamically constructed as `http://localhost:<auto_port>/`.

**Important:** Your OAuth Client ID in Google Cloud Console must have `http://localhost` configured as an authorized redirect URI. Google's OAuth for desktop apps allows any `localhost` port, so you don't need to register each port individually.

### Headless / SSH / Docker Environments

In environments without a display (no X11/Wayland, no GUI), `open_browser=True` will fail silently. The authorization URL is still printed to the console via `authorization_prompt_message`. Options:

- **Manual flow:** Set `open_browser=False` and have the user copy the URL to their local browser manually.
- **Remote port forwarding:** SSH with `-L 8080:localhost:8080` to forward the callback port, then access the printed URL from a local browser.
- **Service account:** Use a service account with domain-wide delegation instead of user OAuth (no browser needed at all).

### Windows: Chrome vs Edge Priority

On Windows, the `webbrowser` module first registers `windows-default` (the system default browser, often Edge). When Chrome is requested explicitly via `browser='chrome'`, this bypasses the system default entirely. If Chrome is not in PATH, you *must* use the manual registration approach from Section 3.

### macOS: AppleScript Integration

On macOS, `webbrowser.get('chrome')` returns a `MacOSXOSAScript('google chrome')` controller. This uses AppleScript (`open -a "Google Chrome" <url>`) which:
- Works even if Chrome is not in PATH
- Opens Chrome specifically (not the default browser)
- Raises the Chrome window to the foreground
- Opens the URL in a new tab if Chrome is already running

### `timeout_seconds` Parameter

If the user doesn't complete the consent flow, the local server can hang indefinitely. Use `timeout_seconds` to prevent this:

```python
creds = flow.run_local_server(
    port=0,
    browser='chrome',
    timeout_seconds=120,  # Fail after 2 minutes of no response
)
```

Note: As of `google-auth-oauthlib` 1.0.0, there's a known issue where the timeout may not always raise a clean exception. Wrap in a try/except for robustness.

### Scopes Changed After Initial Auth

If you change the requested scopes after `token.json` is already saved, the cached token won't have the new scopes. Delete `token.json` to force re-authentication:

```python
if not set(SCOPES).issubset(set(creds.scopes or [])):
    os.remove(TOKEN_FILE)
    creds = None  # Force re-auth
```

---

## 7. Summary of All Approaches

| Approach | Complexity | Reliability | Cross-Platform |
|----------|-----------|-------------|----------------|
| `run_local_server(browser='chrome')` | Minimal | Good on macOS/Linux; fragile on Windows | ⚠️ Name varies |
| Manual detection + `webbrowser.register()` | Moderate | High | ✅ Yes |
| `BROWSER` environment variable | Minimal | Good | ✅ Yes |
| `subprocess` to launch Chrome directly + manual URL handling | High | Highest | ✅ Yes |

### Recommended Pattern

For most use cases, the **manual detection with fallback** approach (Section 5's `get_chrome_browser_name()`) provides the best balance:

```python
# Detect Chrome, register if needed, fall back gracefully
browser_name = get_chrome_browser_name()  # 'chrome' / 'chrome-custom' / None
creds = flow.run_local_server(port=0, browser=browser_name)
```

This ensures Chrome is used when available, falls back to the system default when it's not, and works on all platforms without requiring users to configure environment variables or modify PATH.

---

## References

- [google-auth-oauthlib source: `flow.py`](https://googleapis.dev/python/google-auth-oauthlib/latest/_modules/google_auth_oauthlib/flow.html) — Confirms `browser` parameter and `webbrowser.get()` call
- [Python `webbrowser` module docs](https://docs.python.org/3/library/webbrowser.html) — Browser registration, BROWSER env var, predefined types
- [CPython `webbrowser.py` source](https://github.com/python/cpython/blob/main/Lib/webbrowser.py) — Platform-specific `register_standard_browsers()` implementation
- [Google OAuth 2.0 for Installed Applications](https://googleapis.github.io/google-api-python-client/docs/oauth-installed.html) — Official flow documentation
- [google-auth-oauthlib API reference: `InstalledAppFlow`](https://google-auth-oauthlib.readthedocs.io/en/latest/reference/google_auth_oauthlib.flow.html) — Method signatures and parameters
