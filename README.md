# navigo-justificatif

Download your monthly Île-de-France Mobilités (Navigo) justificatif d'achat
automatically, and optionally prefill an HR reimbursement form so all that's
left is to attach the PDF and hit submit.

No Navigo/IDFM API exists for personal purchase receipts, so this drives a
real (Playwright) browser: log in once by hand, then reuse that session
headlessly every month.

## Why a browser, not a plain HTTP request?

An earlier project, [Navigogo](https://github.com/Scout22/Navigogo) (2022),
did this with a raw `requests` session and a long-lived cookie — no browser
at all. That's the leaner approach and the inspiration for the
bootstrap-once/run-headless shape here, but its endpoint
(`jegeremacartenavigo.fr`) is dead, and the current
`iledefrance-mobilites.fr` sits behind Cloudflare bot protection that a bare
HTTP client can't pass. Playwright's `storage_state` gives the same
"authenticate once, replay headlessly" model while still looking like a real
browser to Cloudflare.

## Setup

```sh
uv sync
uv run playwright install chromium
uv run pre-commit install  # optional, for contributing
mkdir -p ~/.navigo-justificatif
cp config.example.toml ~/.navigo-justificatif/config.toml
```

Edit `~/.navigo-justificatif/config.toml`:
- `justificatif_page_url`: log into your IDFM account manually once, go to
  where your purchases/attestations are listed, and paste that URL.
- `[hr_form]`: optional. Delete the whole section if you don't want the
  `prefill` step.

This config file, your session, and any downloaded PDF all live under
`~/.navigo-justificatif/` and a configurable output folder — nothing
personal ever goes into this repo (`.gitignore` covers all of it).

## Usage

```sh
# One-time: opens a real browser window, you log in, press Enter when done.
uv run python navigo.py bootstrap

# Monthly: headless download of the current month's justificatif.
uv run python navigo.py fetch
# or a specific month:
uv run python navigo.py fetch --month 2026-08

# If the download link isn't found, watch it happen and tune [selectors]
# in config.toml:
uv run python navigo.py fetch --headed --month 2026-08

# Optional: open the HR form prefilled, reveal the PDF in Finder, then you
# attach it and submit by hand (Google Forms blocks scripted file uploads
# and forces sign-in on submit, so this last step stays manual on purpose).
uv run python navigo.py prefill
```

If your session expires, `fetch` fires a macOS notification telling you to
re-run `bootstrap` — a scheduled job should never fail silently.

## Scheduling on macOS

An example `launchd` job is in [`launchd/`](launchd/com.example.navigo-justificatif.plist),
running `fetch` then `prefill` on the 15th of each month. See the comments in
that file for install steps.

## Scope, on purpose

- Only ever fetches **one month at a time** (matches how the site presents
  justificatifs, and how you'd submit them).
- The HR form's file attachment and final submit are **manual** — Google
  Forms doesn't allow scripted uploads without a fragile logged-in-Google
  automation, and a human should eyeball the reimbursement request anyway.
- No retry queue: a failed run notifies you and you re-run it by hand.

## License

MIT — see [LICENSE](LICENSE).
