# Next phases — pickup notes for a fresh session

This file is the entry point for any session continuing work in this repo.
Reads in 3 minutes; tells you what's done, what's next, and which decisions
are already taken.

## State on 2026-05-10

- **`master`**: clean. PRs #15–#20 merged.
- **JP API**: alive, token unchanged.
- **All packages in CI**: web, scraper_job, teams_analyzer, telegram_bot, chucknorris_bot.
- **Python**: 3.13 (PR #18).
- **Deuda técnica**: prácticamente cero. No hay work pendiente urgente.

## What shipped this sprint

### Chuck Norris Bot ✅ (PR #17)
- `packages/chucknorris_bot/bot` — Python/Flask rewrite del bot original de 2015 (Node.js/Heroku).
- Cloud Run Service `chucknorris-bot`, europe-southwest1, proyecto biwenger-tools.
- Bot: @ChuckNorrisJokesBot. Landing page dark-mode. CI wired.

### Python 3.13 ✅ (PR #18)
- Toolchain, Dockerfile.base (nueva imagen pushed), deploy.yml, digest MODULE.bazel actualizados.

### VAR panel — scraper on-demand ✅ (PR #19)
- `POST /admin/run-scraper` lanza `biwenger-scraper-data` Cloud Run Job vía ADC (roles/run.developer ya en la SA).
- Panel rediseñado: 4 cards (header, scraper controls, ficheros, sistema).
- SA: `biwenger-tools-sa@biwenger-tools.iam.gserviceaccount.com`, gitignoreada, no rotación necesaria.

### Web UI 2.0 ✅ (PR #20)
- Sticky nav con hamburger en móvil. Season selector como pill en desktop.
- Nueva sección `/mercado` (Clausulazos + Tabla de Justicia, split de Salseo).
- Salseo simplificado a 2 tabs (Crónicas + Datos). Búsqueda con botón ✕ y contador.
- Participación: columna Total, medallas 🥇🥈🥉, barra de progreso, cards en móvil.
- Tabla de Justicia: filas expandibles (click = desglose quién atacó a quién).
- Lloros Awards: auto-carga primera tab. Reglamento: acordeón. Palmarés: badge dorado campeón.
- VAR link en footer siempre visible. 23 tests, lint limpio, CI verde.

---

## Pending work

### 1. Firestore migration (~16h, $0/mes) — DEFERRED
La única tarea grande pendiente. Deferred indefinidamente por el usuario (2026-05-10).
Domain models en `core/domain/models.py` ya mapean directo a Firestore.

Estructura de colecciones decidida:
```
comunicados/{season}/messages/{id_hash}
clausulazos/{season}/transfers/{auto_id}
tabla_justicia/{season}/teams/{equipo}
participacion/{season}/authors/{autor}
palmares/{auto_id}
```

Orden de ataque cuando se retome:
1. `core/sdk/firestore.py` — CRUD helpers, ADC auth
2. `scraper_job` — escribir a Firestore en vez de CSV → Drive
3. `web` — leer de Firestore en vez de Drive CSVs
4. Borrar secrets `gdrive-folder-id-regional` y `biwenger-tools-sa-regional`

### 2. Nuevo proyecto Google para fotos (sin urgencia)
Mencionado como TODO pero sin spec. Sin blockers técnicos.

---

## Closed / won't do

- **Auditar y rotar SA key** — gitignoreada, nunca subida. No hay riesgo.
- **Mover IDs de Drive/Sheets a Secret Manager** — mueren con Firestore.
- **Phase D dependencies** — todo al día (2026-05-10).

---

## Decisions already taken (don't reopen)

- Telegram bot → Cloud Run Service dedicado, no el Flask web.
- Output (teams, market) → PNG via `sendPhoto`. No texto/CSV.
- Auto-lineup capitán → precio < 3M estricto, mayor SF. Fallback: más barato con precio conocido.
- Chuck Norris bot → mismo proyecto GCP (`biwenger-tools`). Secrets regionales.
- Webhook helpers → `core/sdk/telegram.py`, no duplicados por bot.
- Firestore migration → deferred; stack CSV/Drive permanece hasta que se retome explícitamente.
- Web UI → Tailwind CDN + vanilla JS, sin frameworks. Misma paleta verde #38a169.

---

## Logistics for a fresh session

1. `cd /Users/jorge/Projects/lillorepo`
2. `git checkout master && git pull --ff-only`
3. Read `CLAUDE.md` (root) + `.claude/CLAUDE.md`.
4. Read this file.
5. No hay "next action" urgente — preguntar al usuario qué quiere hacer.

```bash
# Full test sweep
bazel test //core:core_tests \
  //packages/biwenger_tools/web:web_tests \
  //packages/biwenger_tools/scraper_job:scraper_job_tests \
  //packages/biwenger_tools/teams_analyzer:teams_analyzer_tests \
  //packages/biwenger_tools/telegram_bot:telegram_bot_tests \
  //packages/chucknorris_bot/bot:bot_tests

# Lint (same as CI)
python3 -m flake8 core/ packages/ && python3 -m black --check core/ packages/
```

Do **not**:
- Commit directly to `master`.
- Touch `requirements_lock.txt` by hand.
- Add `Co-Authored-By` to commit messages.
- Bump dependencies in the same PR as a feature.
