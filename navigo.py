#!/usr/bin/env python3
"""Download your monthly Île-de-France Mobilités (Navigo) justificatif, and
optionally prefill an HR reimbursement form with it.

Three commands:
  bootstrap  one-time interactive login, saves your session
  fetch      headless: download one month's justificatif PDF
  prefill    open an HR form prefilled, so you can attach the PDF and submit

Credit: the "save a session once, reuse it headlessly" idea and the
single-month download shape follow github.com/Scout22/Navigogo (2022),
adapted here for the current site and driven through a real browser session
(Playwright) instead of a raw cookie, since the site now sits behind
Cloudflare bot protection.
"""

import argparse
import json
import subprocess
import sys
import tomllib
import webbrowser
from datetime import date
from pathlib import Path
from urllib.parse import urlencode

from playwright.sync_api import sync_playwright

CONFIG_DIR = Path.home() / ".navigo-justificatif"
DEFAULT_CONFIG_PATH = CONFIG_DIR / "config.toml"
STATE_PATH = CONFIG_DIR / "storage_state.json"
DEFAULT_LOGIN_URL = "https://www.iledefrance-mobilites.fr/mon-compte"

FRENCH_MONTHS = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]


class AuthExpired(Exception):
    pass


def load_config(path=None):
    config_path = Path(path).expanduser() if path else DEFAULT_CONFIG_PATH
    if not config_path.exists():
        return {}
    with config_path.open("rb") as f:
        return tomllib.load(f)


def notify(title, message):
    if sys.platform == "darwin":
        script = f"display notification {json.dumps(message)} with title {json.dumps(title)}"
        subprocess.run(["osascript", "-e", script], check=False)
    else:
        print(f"[{title}] {message}")


def parse_month(text):
    year_str, month_str = text.split("-")
    return int(year_str), int(month_str)


def current_month():
    today = date.today()
    return today.year, today.month


def month_label(year, month):
    return f"{FRENCH_MONTHS[month - 1]} {year}"


def _looks_like_login(page):
    if page.locator('input[type="password"]').count() > 0:
        return True
    url = page.url.lower()
    return any(word in url for word in ("connexion", "login", "auth"))


def download_justificatif(page, cfg, year, month, output_path):
    page.goto(cfg["justificatif_page_url"])
    if _looks_like_login(page):
        raise AuthExpired(page.url)

    download_text = cfg.get("selectors", {}).get("download_link_text", "Télécharger")
    label = month_label(year, month)

    row = page.get_by_text(label, exact=False).first
    row.wait_for(timeout=10_000)
    container = row.locator("xpath=ancestor::*[self::li or self::tr or self::div][1]")
    link = container.get_by_text(download_text, exact=False).first

    with page.expect_download() as dl_info:
        link.click()
    dl_info.value.save_as(output_path)


def cmd_bootstrap(args):
    cfg = load_config(args.config)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(cfg.get("login_url", DEFAULT_LOGIN_URL))

        print("A browser window opened.")
        print("Log into your Île-de-France Mobilités account, then come back here.")
        input("Press Enter once you're logged in... ")

        context.storage_state(path=str(STATE_PATH))
        browser.close()

    print(f"Session saved to {STATE_PATH}")


def cmd_fetch(args):
    cfg = load_config(args.config)
    if not STATE_PATH.exists():
        sys.exit("No saved session found. Run `navigo.py bootstrap` first.")

    justificatif_url = cfg.get("justificatif_page_url")
    if not justificatif_url or "CHANGE_ME" in justificatif_url:
        sys.exit("Set justificatif_page_url in your config.toml (see config.example.toml).")

    year, month = parse_month(args.month) if args.month else current_month()
    output_dir = Path(cfg.get("output_dir", "~/Navigo-justificatifs")).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{year:04d}-{month:02d}.pdf"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed)
        context = browser.new_context(storage_state=str(STATE_PATH))
        page = context.new_page()
        try:
            download_justificatif(page, cfg, year, month, output_path)
        except AuthExpired:
            notify("Navigo justificatif", "Session expired — run `navigo.py bootstrap` again.")
            sys.exit("Session expired. Run `navigo.py bootstrap` again.")
        except Exception as exc:
            notify("Navigo justificatif", f"Download failed: {exc}")
            print(f"Failed on {page.url!r} ({page.title()!r}): {exc}", file=sys.stderr)
            print("Tip: re-run with --headed to watch it, and adjust [selectors] in config.toml.", file=sys.stderr)
            sys.exit(1)
        finally:
            browser.close()

    if not output_path.read_bytes().startswith(b"%PDF"):
        sys.exit(f"Downloaded file doesn't look like a PDF: {output_path}")

    notify("Navigo justificatif", f"Downloaded {output_path.name}")
    print(f"Saved {output_path}")


def cmd_prefill(args):
    cfg = load_config(args.config)
    hr_form = cfg.get("hr_form")
    if not hr_form:
        sys.exit("No [hr_form] section in config.toml — nothing to prefill.")

    year, month = parse_month(args.month) if args.month else current_month()
    output_dir = Path(cfg.get("output_dir", "~/Navigo-justificatifs")).expanduser()
    pdf_path = output_dir / f"{year:04d}-{month:02d}.pdf"

    values = {
        "month": month_label(year, month).capitalize(),
        "amount": hr_form.get("amount", ""),
        "name": hr_form.get("name", ""),
    }
    params = {key: str(value).format(**values) for key, value in hr_form.get("fields", {}).items()}
    url = f"{hr_form['base_url']}?{urlencode(params)}&usp=pp_url"

    webbrowser.open(url)
    if pdf_path.exists() and sys.platform == "darwin":
        subprocess.run(["open", "-R", str(pdf_path)], check=False)

    print(f"Opened prefilled form. Attach {pdf_path} and submit manually.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", help="Path to config.toml (default: ~/.navigo-justificatif/config.toml)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("bootstrap", help="One-time interactive login; saves your session.")

    p_fetch = sub.add_parser("fetch", help="Download one month's justificatif PDF.")
    p_fetch.add_argument("--month", help="YYYY-MM, defaults to the current month.")
    p_fetch.add_argument("--headed", action="store_true", help="Show the browser (for debugging selectors).")

    p_prefill = sub.add_parser("prefill", help="Open the HR form prefilled and reveal the PDF.")
    p_prefill.add_argument("--month", help="YYYY-MM, defaults to the current month.")

    args = parser.parse_args()
    {"bootstrap": cmd_bootstrap, "fetch": cmd_fetch, "prefill": cmd_prefill}[args.command](args)


if __name__ == "__main__":
    main()
