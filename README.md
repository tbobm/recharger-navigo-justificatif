# navigo-justificatif

Download your monthly Île-de-France Mobilités (Navigo) justificatif d'achat
automatically, and optionally get it renamed and staged for your HR
reimbursement form so all that's left is to attach it and hit submit.

No Navigo/IDFM API exists for personal purchase receipts, so this drives a
real (Playwright) browser: log in once by hand, then reuse that session
every month.

## Why a browser at all?

An earlier project, [Navigogo](https://github.com/Scout22/Navigogo) (2022),
did this with a raw `requests` session and a long-lived cookie — no browser
at all. Its endpoint (`jegeremacartenavigo.fr`) is dead, but the same
Symfony app now lives at `jegeremacartenavigo.iledefrance-mobilites.fr`
behind Cloudflare, which a bare HTTP client can't get past. So this tool
uses Playwright just to establish and hold that authenticated session
(`storage_state`, replayed on every run). Once on the "attestation" page, the
actual download replays Navigogo's original technique almost exactly: read
the CSRF token out of the page's hidden `attestation[_token]` input, then
POST the desired month/year straight to `/attestation/attestation.pdf`
through Playwright's request API (which shares the browser session's
cookies) — no clicking, no datepicker interaction.

**Why not headless?** Cloudflare reliably blocks headless Chrome on this
site, even with the anti-fingerprint hardening below. `fetch` always opens a
real, visible Chrome window — a brief popup once a month is a fine trade-off
for a personal script. (One quirk found the hard way: the site's month
fields are 0-indexed, JS `Date.getMonth()` style — `navigo.py` already
accounts for this.)

## Setup

Requires Google Chrome installed (this drives it directly via Playwright's
`channel="chrome"` — no separate browser download needed).

```sh
uv sync
uv run pre-commit install  # optional, for contributing
mkdir -p ~/.navigo-justificatif
cp config.example.toml ~/.navigo-justificatif/config.toml
```

Edit `~/.navigo-justificatif/config.toml`:
- `justificatif_page_url`: log into your IDFM account, go to "Mon espace" >
  "Mon Navigo" > your contract > "Obtenir mon attestation de forfait", and
  paste that URL (looks like
  `https://www.jegeremacartenavigo.iledefrance-mobilites.fr/attestation/<id>`).
- `[hr_form]`: optional, only makes sense if your HR form's only real input
  is a file upload with a naming convention (see `config.example.toml`).
  Delete the whole section if you don't want the `prefill` step.

This config file, your session, and any downloaded PDF all live under
`~/.navigo-justificatif/` and a configurable output folder — nothing
personal ever goes into this repo (`.gitignore` covers all of it).

## Usage

```sh
# One-time: opens a real browser window, you log in, press Enter when done.
uv run python navigo.py bootstrap

# Monthly: downloads the current month's justificatif (briefly opens Chrome).
uv run python navigo.py fetch
# or a specific month:
uv run python navigo.py fetch --month 2026-08

# Optional: rename a copy of the PDF to the HR form's required convention,
# open the form, reveal the renamed file in Finder, then you attach it and
# submit by hand (the form has no text fields to prefill, and a human
# should eyeball the reimbursement request before submitting anyway).
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
- The HR form's file attachment and final submit are **manual** — the form
  has no fields to script beyond the file itself, and a human should
  eyeball the reimbursement request before submitting anyway.
- No retry queue: a failed run notifies you and you re-run it by hand.

## License

MIT — see [LICENSE](LICENSE).
