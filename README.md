# navigo-justificatif

Download your monthly Île-de-France Mobilités (Navigo) justificatif d'achat
automatically, and optionally get it renamed and staged for your HR
reimbursement form so all that's left is to attach it and hit submit.

Drives a real Chrome browser via Playwright: log in once by hand, then reuse
that session every month. `fetch` briefly opens a visible Chrome window each
run (Cloudflare blocks headless Chrome on this site).

## Setup

Requires Google Chrome installed.

```sh
uv sync
mkdir -p ~/.navigo-justificatif
cp config.example.toml ~/.navigo-justificatif/config.toml
```

Edit `~/.navigo-justificatif/config.toml`:
- `justificatif_page_url`: log into your IDFM account, go to "Mon espace" >
  "Mon Navigo" > your contract > "Obtenir mon attestation de forfait", and
  paste that URL.
- `[hr_form]`: optional — delete it if you don't want the `prefill` step
  (only useful if your HR form is a plain file upload; see the comments in
  `config.example.toml`).

Everything personal (config, session, downloaded PDFs) lives under
`~/.navigo-justificatif/` and a configurable output folder — never in this repo.

## Usage

```sh
uv run python navigo.py bootstrap   # one-time: log in, press Enter when done
uv run python navigo.py fetch       # monthly: download this month's justificatif
uv run python navigo.py prefill     # optional: rename PDF, open the HR form, attach & submit by hand
```

Pass `--month YYYY-MM` to `fetch`/`prefill` for a specific month. If your
session expires, `fetch` sends a macOS notification telling you to re-run
`bootstrap` instead of failing silently.

## Scheduling on macOS

See [`launchd/dev.tbobm.navigo-justificatif.plist`](launchd/dev.tbobm.navigo-justificatif.plist)
for a ready-to-install job that runs `fetch` then `prefill` on the 10th of
each month — install/verify/uninstall steps are in its header comment.

## Scope, on purpose

- Only ever fetches **one month at a time**.
- The HR form's file attachment and final submit are **manual** — the form
  has no other fields, and a human should eyeball the request before submitting.
- No retry queue: a failed run notifies you and you re-run it by hand.

## License

MIT — see [LICENSE](LICENSE).

<details>
<summary>Why a browser, and why not headless?</summary>

No Navigo/IDFM API exists for personal purchase receipts. An earlier project,
[Navigogo](https://github.com/Scout22/Navigogo) (2022), solved this with a raw
`requests` session and a long-lived cookie — no browser at all. Its endpoint
is dead, but the same app now lives behind Cloudflare, which a bare HTTP
client can't get past. This tool uses Playwright to hold an authenticated
session (`storage_state`), then replays Navigogo's original technique almost
exactly: read the CSRF token out of the "attestation" page's hidden input,
then POST the desired month/year straight to `/attestation/attestation.pdf`
— no clicking, no datepicker interaction.

Cloudflare reliably blocks headless Chrome on this site even with
anti-fingerprint hardening, so `fetch` always opens a real, visible window —
a brief popup once a month. (One quirk found the hard way: the site's month
fields are 0-indexed, JS `Date.getMonth()` style.)

</details>
