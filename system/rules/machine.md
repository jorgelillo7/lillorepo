# This Mac

- **`pip3`, never `pip`** (not on PATH).
- **Wary of wrapper installers** (`npx <aggregator>`, `curl | bash`), even
  from big vendors: the official source is fine, the delivery channel matters.
  Prefer a small script under `scripts/` doing `git clone` or
  `curl raw.githubusercontent.com` straight from the official origin
  (lillorepo `scripts/sync-google-skills.sh` is the pattern).
