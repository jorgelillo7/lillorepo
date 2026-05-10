# TODO

> 📌 **Para retomar trabajo en una sesión nueva**, leer
> [`.claude/plans/next_phases.md`](../.claude/plans/next_phases.md).

## Prioritario

- [x] **GitHub Actions secrets** — todos añadidos en el repo
- [x] **Primer deploy via CI** — disparado tras los primeros pushes a `master`
- [x] **Eliminar GitHub Secrets obsoletos** — `COMUNICADOS_CSV_URL`, `PALMARES_CSV_URL`, `PARTICIPACION_CSV_URL` borrados (2026-05-04).
- [x] **Auditar y rotar SA key** — SA key está gitignoreada, nunca se subió. No hay riesgo (2026-05-10).
- [ ] **Mover IDs de Drive/Sheets a Secret Manager / env** — actualmente hardcodeados en `packages/biwenger_tools/web/BUILD.bazel:13-19` (mueren con la migración Firestore)

## Técnico

- [x] **Import incorrecto** — `web/routes/admin.py:8` importa `get_file_metadata` desde `core.utils`; debería ser `from core.sdk.gcp` (la función ya está ahí)
- [x] **Default `--platforms` en `.bazelrc`** — `--test_output=errors` como default de test; `--config=gcp` para builds de imagen
- [x] **Pin `Dockerfile.base` por digest SHA** — `python:3.12-slim@sha256:4386a385...`
- [x] **`TEMPORADA_ACTUAL` duplicado** — centralizado en `env.TEMPORADA_ACTUAL` del `deploy.yml`; ambos config leen `os.getenv`
- [x] **Selenium fuera del teams_analyzer** — v4.2 reemplaza Selenium + Analítica Fantasy por la API privada de Jornada Perfecta (1 request HTTP en vez de 600 acciones de browser).
- [x] **Arreglar target Docker de teams_analyzer** — migrado al patrón de `scraper_job` (`@python_with_deps` + `entrypoint.sh` propio + capas de código separadas). Añadido `push_image_to_gcp` y `load_image_to_docker_local`. `bazel build //...` ahora pasa entero por primera vez tras la migración a bzlmod.
- [x] **Reconstruir `Dockerfile.base`** — hecho: sin Selenium/pytz/trio*, digest actualizado en `MODULE.bazel`.
- [x] **Arreglar `scripts/clean-images-artifact.sh`** — hecho: bugs `get(digest)` y `NOT TAGS:*` corregidos.

## Producto

- [x] **Deploy teams_analyzer a GCP** — Cloud Run Job `biwenger-teams-analyzer` corriendo diario a las 16:00 Madrid. CI auto-despliega.
- [x] **Telegram bot interactivo** — Cloud Run Service dedicado (`biwenger-telegram-bot`). Comandos: `/analizar`, `/myteam`, `/mercado`, `/alinear`, `/help`. Webhook con secret token.
- [x] **Auto-alineación `/alinear`** — `logic/lineup.py`, greedy sobre 12 formaciones, multi-posición vía `altPositions`, capitán < 3M. `BiwengerClient.set_lineup()` en core.
- [x] **Sección VAR en web** — botón "Forzar ejecución" del scraper + panel rediseñado (PR #19, 2026-05-10).
- [ ] **Nuevo proyecto Google para fotos**
- [x] **Chuck Norris bot** — @ChuckNorrisJokesBot desplegado en Cloud Run, en CI (PR #17, 2026-05-10).
- [x] **Web UI 2.0** — sticky nav, hamburger móvil, nueva sección Mercado, acordeón en Reglamento, medallas en Participación, desglose expandible en Tabla de Justicia (PR #20, 2026-05-10).

## Arquitectura (medio plazo)

- [x] **Domain models aplicados** — `LeagueMessage`, `Participation`, `Clausulazo`, `JusticeEntry` con `from_csv_row`/`to_csv_row` ya se usan en scraper (escritura) y web (lectura). El call site del CSV-as-DB queda contenido en una capa: facilita la futura migración a Firestore.
- [ ] **Migración CSV → Firestore** — los modelos de dominio están listos para que el cambio sea localizado en lecturas/escrituras GCP en lugar de tocar todos los call sites. Sin urgencia, ver project_pitch.md para narrativa.
- [x] **Bumps de dependencias (Phase D)** — todo al día a 2026-05-10. rules_python 2.0, platforms 1.1, GH Actions en major actual, libs Python todas en latest.
- [x] **Upgrade Python 3.12 → 3.13** — hecho en PR #18 (2026-05-10). Toolchain, Dockerfile.base y MODULE.bazel actualizados.
