"""
Google Photos API demo (OAuth + Library API + Picker API).

IMPORTANT (as of 2025+):
  The Library API can only see media/albums *created by your app*.
  It cannot browse a user's full library or Takeout-equivalent content.
  To let a user choose photos from their library, use the Picker API.

Setup (once):
  1. Google Cloud Console -> create/select a project
  2. Enable "Google Photos Library API" and "Google Photos Picker API"
  3. Configure OAuth consent screen (External / Testing is fine for personal use)
  4. Create OAuth client ID -> Desktop app -> download JSON
  5. Save as client_secret.json (or pass -c PATH)

Install deps:
  uv sync --group gphoto
  # or: pip install google-auth google-auth-oauthlib requests

Run:
  python gphoto_api_demo.py -h
  python gphoto_api_demo.py auth -c client_secret.json
  python gphoto_api_demo.py albums
  python gphoto_api_demo.py media -n 10
  python gphoto_api_demo.py picker
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import webbrowser
from pathlib import Path

# Lazy-import Google libs so -h works even if extras are not installed.

LIBRARY_BASE = "https://photoslibrary.googleapis.com/v1"
PICKER_BASE = "https://photospicker.googleapis.com/v1"

SCOPES = [
    # Library: read albums/media created by this OAuth client/app only
    "https://www.googleapis.com/auth/photoslibrary.readonly.appcreateddata",
    # Picker: let user select items from their full library
    "https://www.googleapis.com/auth/photospicker.mediaitems.readonly",
]

DEFAULT_SECRET = Path("client_secret.json")
DEFAULT_TOKEN = Path(".gphoto_token.json")


def _require_google_libs():
    try:
        from google.auth.transport.requests import Request  # noqa: F401
        from google.oauth2.credentials import Credentials  # noqa: F401
        from google_auth_oauthlib.flow import InstalledAppFlow  # noqa: F401
        import requests  # noqa: F401
    except ImportError as e:
        print(
            "Missing Google Photos demo dependencies.\n"
            "  uv sync --group gphoto\n"
            "  # or: pip install google-auth google-auth-oauthlib requests\n"
            f"Detail: {e}",
            file=sys.stderr,
        )
        sys.exit(1)


def load_credentials(secret: Path, token_path: Path):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if token_path.is_file():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json(), encoding="utf-8")
        return creds

    if not secret.is_file():
        raise FileNotFoundError(
            f"OAuth client secret not found: {secret}\n"
            "Download Desktop client JSON from Google Cloud Console "
            "and pass -c/--credentials."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(secret), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    token_path.write_text(creds.to_json(), encoding="utf-8")
    print(f"Saved token to {token_path}")
    return creds


def api_get(creds, url: str, params: dict | None = None) -> dict:
    import requests
    from google.auth.transport.requests import Request

    if not creds.valid:
        creds.refresh(Request())
    headers = {"Authorization": f"Bearer {creds.token}"}
    r = requests.get(url, headers=headers, params=params or {}, timeout=60)
    if not r.ok:
        raise RuntimeError(f"HTTP {r.status_code} {url}: {r.text[:800]}")
    return r.json() if r.text else {}


def api_post(creds, url: str, body: dict | None = None) -> dict:
    import requests
    from google.auth.transport.requests import Request

    if not creds.valid:
        creds.refresh(Request())
    headers = {
        "Authorization": f"Bearer {creds.token}",
        "Content-Type": "application/json",
    }
    r = requests.post(url, headers=headers, json=body or {}, timeout=60)
    if not r.ok:
        raise RuntimeError(f"HTTP {r.status_code} {url}: {r.text[:800]}")
    return r.json() if r.text else {}


def cmd_auth(args: argparse.Namespace) -> int:
    _require_google_libs()
    try:
        creds = load_credentials(Path(args.credentials), Path(args.token))
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    print("Authenticated OK.")
    print(f"  scopes: {', '.join(sorted(creds.scopes or []))}")
    print(f"  token file: {args.token}")
    print()
    print(
        "Note: Library API lists only app-created content. "
        "Use 'picker' to select from the user's full library."
    )
    return 0


def cmd_albums(args: argparse.Namespace) -> int:
    _require_google_libs()
    creds = load_credentials(Path(args.credentials), Path(args.token))
    page_token = None
    total = 0
    print("Albums created by this app (Library API):")
    while True:
        params: dict = {"pageSize": min(50, args.limit) if total == 0 else 50}
        if page_token:
            params["pageToken"] = page_token
        data = api_get(creds, f"{LIBRARY_BASE}/albums", params)
        albums = data.get("albums") or []
        if not albums and total == 0:
            print("  (none — expected if this app has never created albums)")
            return 0
        for a in albums:
            total += 1
            title = a.get("title") or "(untitled)"
            mid = a.get("id", "")
            count = a.get("mediaItemsCount", "?")
            print(f"  [{total}] {title}  items={count}  id={mid}")
            if args.limit and total >= args.limit:
                print(f"(stopped at -n {args.limit})")
                return 0
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    print(f"Total albums: {total}")
    return 0


def cmd_media(args: argparse.Namespace) -> int:
    _require_google_libs()
    creds = load_credentials(Path(args.credentials), Path(args.token))
    page_token = None
    total = 0
    print("Media items created by this app (Library API):")
    while True:
        params: dict = {"pageSize": 25}
        if page_token:
            params["pageToken"] = page_token
        data = api_get(creds, f"{LIBRARY_BASE}/mediaItems", params)
        items = data.get("mediaItems") or []
        if not items and total == 0:
            print("  (none — expected if this app has never uploaded media)")
            return 0
        for m in items:
            total += 1
            mid = m.get("id", "")
            fname = m.get("filename") or "(no name)"
            mime = m.get("mimeType") or ""
            meta = m.get("mediaMetadata") or {}
            taken = meta.get("creationTime") or ""
            print(f"  [{total}] {fname}  {mime}  taken={taken}  id={mid}")
            if args.limit and total >= args.limit:
                print(f"(stopped at -n {args.limit})")
                return 0
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    print(f"Total media items: {total}")
    return 0


def cmd_picker(args: argparse.Namespace) -> int:
    """
    Picker API flow:
      1) create session -> pickerUri
      2) open browser / print URL
      3) poll until mediaItemsSet
      4) list selected media items
    """
    _require_google_libs()
    creds = load_credentials(Path(args.credentials), Path(args.token))

    print("Creating Picker session…")
    session = api_post(creds, f"{PICKER_BASE}/sessions", {})
    session_id = session.get("id")
    picker_uri = session.get("pickerUri")
    if not session_id or not picker_uri:
        print(f"Unexpected session response: {json.dumps(session, indent=2)}", file=sys.stderr)
        return 1

    # /autoclose helps web pickers close after selection
    open_uri = picker_uri if picker_uri.endswith("/autoclose") else picker_uri.rstrip("/") + "/autoclose"
    print(f"Session: {session_id}")
    print(f"Open this URL and select photos/videos:\n  {open_uri}")
    if not args.no_browser:
        webbrowser.open(open_uri)

    poll_ms = int(session.get("pollingConfig", {}).get("pollInterval") or "2000")
    # pollingConfig values are often strings like "2s" / "5m" — handle both
    interval = _parse_duration_ms(session.get("pollingConfig", {}).get("pollInterval"), default=2.0)
    timeout_s = _parse_duration_ms(
        session.get("pollingConfig", {}).get("timeout"), default=300.0
    )
    # If values looked like milliseconds already (large ints), convert
    if interval > 60:
        interval = interval / 1000.0
    if timeout_s > 3600:
        timeout_s = timeout_s / 1000.0

    print(f"Polling every {interval:.1f}s (timeout ~{timeout_s:.0f}s)…")
    t0 = time.time()
    while True:
        if time.time() - t0 > timeout_s:
            print("Timed out waiting for selection.", file=sys.stderr)
            return 1
        time.sleep(interval)
        status = api_get(creds, f"{PICKER_BASE}/sessions/{session_id}")
        if status.get("mediaItemsSet"):
            print("Selection complete.")
            break
        # Refresh recommended interval if provided
        pc = status.get("pollingConfig") or {}
        if "pollInterval" in pc:
            interval = max(1.0, _parse_duration_ms(pc["pollInterval"], default=interval))
            if interval > 60:
                interval = interval / 1000.0

    # List picked items
    page_token = None
    total = 0
    print("Selected media items:")
    while True:
        params: dict = {"sessionId": session_id, "pageSize": 50}
        if page_token:
            params["pageToken"] = page_token
        data = api_get(creds, f"{PICKER_BASE}/mediaItems", params)
        items = data.get("mediaItems") or []
        for wrapped in items:
            total += 1
            # Picker wraps Library mediaItem under mediaFile / mediaItem depending on API version
            m = wrapped.get("mediaItem") or wrapped
            mid = m.get("id") or wrapped.get("id") or ""
            fname = m.get("filename") or (m.get("mediaFile") or {}).get("filename") or "(no name)"
            mime = m.get("mimeType") or (m.get("mediaFile") or {}).get("mimeType") or ""
            print(f"  [{total}] {fname}  {mime}  id={mid}")
            if args.raw:
                print(json.dumps(wrapped, indent=2)[:2000])
            if args.limit and total >= args.limit:
                break
        if args.limit and total >= args.limit:
            break
        page_token = data.get("nextPageToken")
        if not page_token:
            break

    if total == 0:
        print("  (no items returned)")
    else:
        print(f"Total selected: {total}")

    if args.out:
        out = Path(args.out)
        # Re-fetch all pages into a list for JSON dump (small selections)
        all_items = []
        page_token = None
        while True:
            params = {"sessionId": session_id, "pageSize": 100}
            if page_token:
                params["pageToken"] = page_token
            data = api_get(creds, f"{PICKER_BASE}/mediaItems", params)
            all_items.extend(data.get("mediaItems") or [])
            page_token = data.get("nextPageToken")
            if not page_token:
                break
        out.write_text(json.dumps({"sessionId": session_id, "mediaItems": all_items}, indent=2), encoding="utf-8")
        print(f"Wrote {len(all_items)} item(s) to {out}")

    return 0


def _parse_duration_ms(value, default: float) -> float:
    """Parse API duration: '2s', '500ms', '5m', or numeric seconds/ms."""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().lower()
    try:
        if s.endswith("ms"):
            return float(s[:-2]) / 1000.0
        if s.endswith("s") and not s.endswith("ms"):
            return float(s[:-1])
        if s.endswith("m"):
            return float(s[:-1]) * 60.0
        return float(s)
    except ValueError:
        return default


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Google Photos API demo (Library + Picker). See module docstring for setup.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  auth     OAuth login; save token
  albums   List albums created by this app (often empty)
  media    List media created by this app (often empty)
  picker   Open Photos Picker; print selected items

Examples:
  python gphoto_api_demo.py auth -c client_secret.json
  python gphoto_api_demo.py albums
  python gphoto_api_demo.py media -n 20
  python gphoto_api_demo.py picker -o picked.json

Library API cannot read your full Google Photos library - only app-created data.
Use picker to select from the library.
        """,
    )
    parser.add_argument(
        "-c",
        "--credentials",
        default=str(DEFAULT_SECRET),
        help=f"OAuth client secret JSON (default: {DEFAULT_SECRET})",
    )
    parser.add_argument(
        "--token",
        default=str(DEFAULT_TOKEN),
        help=f"Saved user token path (default: {DEFAULT_TOKEN})",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    p_auth = sub.add_parser("auth", help="Run OAuth and save token")
    p_auth.set_defaults(func=cmd_auth)

    p_albums = sub.add_parser("albums", help="List app-created albums")
    p_albums.add_argument("-n", "--limit", type=int, default=0, help="Max albums (0=all)")
    p_albums.set_defaults(func=cmd_albums)

    p_media = sub.add_parser("media", help="List app-created media items")
    p_media.add_argument("-n", "--limit", type=int, default=0, help="Max items (0=all)")
    p_media.set_defaults(func=cmd_media)

    p_pick = sub.add_parser("picker", help="Picker API: select from full library")
    p_pick.add_argument("-n", "--limit", type=int, default=0, help="Max items to print (0=all)")
    p_pick.add_argument("-o", "--out", default=None, help="Write full selection JSON to file")
    p_pick.add_argument("--no-browser", action="store_true", help="Do not open browser")
    p_pick.add_argument("--raw", action="store_true", help="Print raw JSON per item")
    p_pick.set_defaults(func=cmd_picker)

    args = parser.parse_args()
    try:
        code = args.func(args)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        code = 1
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        code = 1
    sys.exit(code)


if __name__ == "__main__":
    main()
