# External APIs — unofficial specs

Reverse-engineered OpenAPI specs for the third-party APIs this monorepo
consumes. Source of truth for behaviour is always the SDK code
(`core/sdk/`); these specs are a human-readable map of what we've seen
in the wild.

## Files

| File | What |
|---|---|
| `biwenger-api.yaml` | Biwenger backend used by `core/sdk/biwenger.py`. Covers auth, account, market, offers (inbox + decisions), squad, lineup, league reports and the cf-base player DB. |

## How to view

Pick one — they all eat the same YAML.

### Quick (no install)

Paste the file content into the online viewer:
- <https://editor.swagger.io/>

### Locally with Docker (recommended)

```bash
docker run -p 8080:8080 \
  -e SWAGGER_JSON=/spec/biwenger-api.yaml \
  -v "$(pwd)/docs/external:/spec" \
  swaggerapi/swagger-ui
```

Then open <http://localhost:8080>. Stop with `Ctrl-C`.

### VS Code

Install the extension **Swagger Viewer** (Arjun G). Open the YAML and
press `Shift+Alt+P` → "Preview Swagger".

### Insomnia / Bruno / Postman

Each one has an "Import OpenAPI" option that takes the YAML directly.
Useful when you want to actually make requests against Biwenger from a
tool other than the SDK.

## Editorial rules

- **Only document what we've verified live.** Speculative endpoints we
  haven't called don't go here.
- Every path entry carries `x-verified-at: YYYY-MM-DD` with the last
  date a real capture matched the spec. If you change a request shape
  in the SDK, bump that date here too.
- The `Owner.price` field is the **acquisition price** (what the user
  paid), NOT the live market value. See the spec description — this
  trips people up because the field name suggests otherwise.
- The disclaimer at the top of the spec is non-negotiable. This is not
  an official Biwenger API and we are not authorised to redistribute it.

## Why bother

Without this file, every time we need to remember "wait, does
`/offers` GET return the inbox or just history?" the answer lives only
in `core/sdk/biwenger.py` docstrings + the head of whoever discovered
it last. This is the index.
