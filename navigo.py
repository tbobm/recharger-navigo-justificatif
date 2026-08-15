#!/usr/bin/env python3
"""Download your monthly Île-de-France Mobilités (Navigo) justificatif, and
optionally prefill an HR reimbursement form with it.

Three commands:
  bootstrap  one-time interactive login, saves your session
  fetch      download one month's justificatif PDF (opens a visible browser
             window briefly — Cloudflare blocks headless Chrome on this site)
  prefill    rename the PDF per the HR form's naming convention, open the
             form and reveal the file, so you can attach it and submit

Credit: the "save a session once, reuse it" idea and the single-month
download shape follow github.com/Scout22/Navigogo (2022), adapted here for
the current site and driven through a real browser session (Playwright)
instead of a raw cookie, since the site now sits behind Cloudflare bot
protection.
"""

import argparse
import json
import subprocess
import sys
import tomllib
import webbrowser
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright

CONFIG_DIR = Path.home() / ".navigo-justificatif"
DEFAULT_CONFIG_PATH = CONFIG_DIR / "config.toml"
STATE_PATH = CONFIG_DIR / "storage_state.json"
DEFAULT_LOGIN_URL = "https://www.iledefrance-mobilites.fr/mon-compte"


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


def launch_browser(p):
    # Cloudflare (which fronts iledefrance-mobilites.fr) fingerprints Playwright's
    # bundled Chromium as a bot. Driving real, installed Chrome plus suppressing
    # the navigator.webdriver tell is enough to pass as this is our own account
    # with valid credentials, not an attempt to get past someone else's access
    # control. Headless Chrome still gets blocked even with this hardening, so
    # this always launches a real, visible window — a brief popup once a month
    # is an acceptable trade-off for a personal script.
    return p.chromium.launch(
        channel="chrome",
        headless=False,
        args=["--disable-blink-features=AutomationControlled", "--start-maximized"],
    )


def new_context(browser, **kwargs):
    # Without no_viewport, Playwright pins the page to a fixed viewport (1280x720)
    # regardless of the real window size, leaving the rest of the window blank.
    kwargs.setdefault("no_viewport", True)
    context = browser.new_context(**kwargs)
    context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return context


def _looks_like_login(page):
    if page.locator('input[type="password"]').count() > 0:
        return True
    url = page.url.lower()
    return any(word in url for word in ("connexion", "login", "auth"))


def download_justificatif(context, page, cfg, year, month, output_path):
    # The "attestation" form (same Symfony app Navigogo targeted in 2022, now
    # under iledefrance-mobilites.fr) exposes its CSRF token as a plain hidden
    # input and posts x-www-form-urlencoded to a fixed relative action. No
    # need to touch the datepicker widget or click anything — just replay the
    # POST with our own month/year, riding on the already-authenticated,
    # Cloudflare-cleared browser session's cookies.
    page.goto(cfg["justificatif_page_url"])
    if _looks_like_login(page):
        raise AuthExpired(page.url)

    form = page.locator('form[name="attestation"]')
    token = form.locator('input[name="attestation[_token]"]').input_value()
    action_url = urljoin(page.url, form.get_attribute("action"))

    # The site's moisDebut/moisFin are 0-indexed (JS Date.getMonth() style:
    # 0=January..11=December), confirmed by its own default value being "7"
    # while the page was loaded in August. Our `month` argument is 1-indexed.
    month_0indexed = str(month - 1)

    response = context.request.post(
        action_url,
        headers={"Referer": page.url},
        form={
            "attestation[type]": "monthly",
            "attestation[moisDebut]": month_0indexed,
            "attestation[moisFin]": month_0indexed,
            "attestation[anneeDebut]": str(year),
            "attestation[anneeFin]": str(year),
            "attestation[_token]": token,
        },
    )
    body = response.body()
    if not response.ok or not body.startswith(b"%PDF"):
        raise ValueError(f"Unexpected response (status {response.status}), first bytes: {body[:80]!r}")
    output_path.write_bytes(body)


def cmd_bootstrap(args):
    cfg = load_config(args.config)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = launch_browser(p)
        context = new_context(browser)
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
        browser = launch_browser(p)
        context = new_context(browser, storage_state=str(STATE_PATH))
        page = context.new_page()
        try:
            download_justificatif(context, page, cfg, year, month, output_path)
        except AuthExpired:
            notify("Navigo justificatif", "Session expired — run `navigo.py bootstrap` again.")
            sys.exit("Session expired. Run `navigo.py bootstrap` again.")
        except Exception as exc:
            notify("Navigo justificatif", f"Download failed: {exc}")
            print(f"Failed on {page.url!r} ({page.title()!r}): {exc}", file=sys.stderr)
            sys.exit(1)
        finally:
            browser.close()

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
    if not pdf_path.exists():
        sys.exit(f"No downloaded PDF for {year:04d}-{month:02d}. Run `navigo.py fetch` first.")

    # The HR form has no text fields to prefill via URL — just a single
    # required file upload, with a strict naming convention it asks for
    # (MOIS_ANNEE_NOM_MENSUEL.pdf). Get that part right automatically and
    # hand off the actual attach + submit, which needs a human anyway.
    renamed_path = output_dir / f"{month:02d}_{year % 100:02d}_{hr_form['surname'].upper()}_MENSUEL.pdf"
    renamed_path.write_bytes(pdf_path.read_bytes())

    webbrowser.open(hr_form["base_url"])
    if sys.platform == "darwin":
        subprocess.run(["open", "-R", str(renamed_path)], check=False)

    print(f"Opened the HR form. Attach {renamed_path} and submit manually.")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--config", help="Path to config.toml (default: ~/.navigo-justificatif/config.toml)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("bootstrap", help="One-time interactive login; saves your session.")

    p_fetch = sub.add_parser("fetch", help="Download one month's justificatif PDF.")
    p_fetch.add_argument("--month", help="YYYY-MM, defaults to the current month.")

    p_prefill = sub.add_parser("prefill", help="Open the HR form prefilled and reveal the PDF.")
    p_prefill.add_argument("--month", help="YYYY-MM, defaults to the current month.")

    args = parser.parse_args()
    {"bootstrap": cmd_bootstrap, "fetch": cmd_fetch, "prefill": cmd_prefill}[args.command](args)


if __name__ == "__main__":
    main()
