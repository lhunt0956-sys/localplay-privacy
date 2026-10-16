# AGENTS.md

## Cursor Cloud specific instructions

This repo has two loosely-coupled products; there is no long-running server or database.

- **LocalPlay privacy page** — `index.html`, a self-contained static HTML page (inline CSS, no build). Open it directly or serve statically (e.g. `python3 -m http.server 8000` from the repo root, then visit `/index.html`).
- **Hunt news-bot** — a Python 3.12 batch CLI in `news-bot/` that fetches RSS feeds + A-share market data, filters/translates/summarizes, and writes a daily digest (`latest.html`, `latest.md`, `latest.json`, dated files) into `news/`. It can also push to messaging channels. See `news-bot/README.md` for details.

### Environment / running

- Python deps are installed into a virtualenv at `.venv` (repo root) by the startup update script. Activate with `source .venv/bin/activate` or call binaries directly, e.g. `.venv/bin/python`.
- The base VM image does **not** ship `python3-venv`/`python3-pip`; they are installed via `apt` (a system dependency, kept out of the update script). If `python3 -m venv` fails on a fresh pod, run `sudo apt-get update && sudo apt-get install -y python3-venv python3-pip`.
- Run the bot from inside `news-bot/` (its imports are flat, e.g. `from digest import ...`):
  - Dry run (prints digest, writes no files; exits 1 if nothing fetched): `cd news-bot && ../.venv/bin/python main.py --dry-run`
  - Generate files without touching committed `news/`: `../.venv/bin/python main.py --out-dir /tmp/news-out`
  - Full run writing to `../news/`: `../.venv/bin/python main.py` (add `--push` to send to channels)

### Gotchas

- The bot needs outbound internet (RSS feeds + Sina/EastMoney endpoints). Individual feed failures are non-fatal and surfaced as warnings (e.g. a `36氪: 解析失败` parse warning is expected/harmless).
- All push channels (`PUSHPLUS_TOKEN`, `TELEGRAM_*`, `WEBHOOK_URL`, `SMTP_*`) are optional and self-skip when their env vars are unset, so a no-secret run exercises the full pipeline end-to-end.
- Avoid running plain `python main.py` (no `--out-dir`) unless you intend to overwrite the committed `news/` digest files.
- There are no automated tests, linters, or a build step configured in this repo.
