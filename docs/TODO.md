# TODO

> 📌 **Para retomar trabajo en una sesión nueva**, leer
> [`.claude/plans/next_phases.md`](../.claude/plans/next_phases.md). Tiene
> el plan ordenado por fases (A → B → C → D), con comandos exactos y
> decisiones ya tomadas.

## Prioritario

- [x] **GitHub Actions secrets** — todos añadidos en el repo
- [x] **Primer deploy via CI** — disparado tras los primeros pushes a `master`
- [x] **Eliminar GitHub Secrets obsoletos** — `COMUNICADOS_CSV_URL`, `PALMARES_CSV_URL`, `PARTICIPACION_CSV_URL` borrados (2026-05-04).
- [ ] **Auditar y rotar SA key** si la del repo es la real (~30min)
- [ ] **Mover IDs de Drive/Sheets a Secret Manager / env** — actualmente hardcodeados en `packages/biwenger_tools/web/BUILD.bazel:13-19`

## Técnico

- [x] **Import incorrecto** — `web/routes/admin.py:8` importa `get_file_metadata` desde `core.utils`; debería ser `from core.sdk.gcp`
- [x] **Default `--platforms` en `.bazelrc`**
- [x] **Pin `Dockerfile.base` por digest SHA**
- [x] **`TEMPORADA_ACTUAL` duplicado** — centralizado en `env.TEMPORADA_ACTUAL` del `deploy.yml`
- [x] **Selenium fuera del teams_analyzer** — v4.2 usa API privada de Jornada Perfecta
- [x] **Arreglar target Docker de teams_analyzer** — migrado al patrón de `scraper_job`
- [x] **Reconstruir `Dockerfile.base`** — PR #6. Libs actualizadas (gunicorn 26, black 26, pytest 9, etc.) digest actualizado en `MODULE.bazel`.
- [x] **Arreglar `scripts/clean-images-artifact.sh`** — PR #4. Bugs `get(digest)` y `NOT TAGS:*` corregidos.
- [x] **Bump Bazel modules** — `rules_python` 0.40→2.0, `platforms` 0.0.10→1.1 (PR #6)
- [x] **Bump GitHub Actions** — checkout v6, setup-python v6, setup-bazel 0.19, etc. (PR #6)

## Producto

- [x] **Deploy teams_analyzer a GCP** — Cloud Run Job + Scheduler 16:00 Madrid (PR #6, 2026-05-05)
- [ ] **Telegram bot `/analizar`** — **PR #7 abierto pero NO mergear**. Arquitectura revisada: webhook en servicio dedicado `biwenger-telegram-bot` (no en el web app). Ver Fase B en `.claude/plans/next_phases.md`.
- [ ] **teams_analyzer `/alinear`** — auto-alineación. **Bloqueado por research** sobre multi-posición en la API de Biwenger. Ver Fase C en `.claude/plans/next_phases.md`.
- [ ] **Sección VAR en web** — revisar y conectar trigger manual del AI scraper o cron job
- [ ] **Nuevo proyecto Google para fotos**

## Arquitectura (medio plazo)

- [x] **Domain models aplicados** — `LeagueMessage`, `Participation`, `Clausulazo`, `JusticeEntry`
- [ ] **Migración CSV → Firestore** — domain models listos, sin urgencia
- [ ] **`rules_oci` 2.3.0→2.3.1** — no está en BCR todavía; reintentar en próximo PR
- [ ] **Python 3.12→3.14** — sin urgencia hasta Oct 2028
