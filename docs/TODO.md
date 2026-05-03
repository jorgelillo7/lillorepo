# TODO

## Prioritario

- [x] **GitHub Actions secrets** — todos añadidos en el repo
- [x] **Primer deploy via CI** — disparado tras los primeros pushes a `master`
- [ ] **Auditar y rotar SA key** si la del repo es la real (~30min)
- [ ] **Mover IDs de Drive/Sheets a Secret Manager / env** — actualmente hardcodeados en `packages/biwenger_tools/web/BUILD.bazel:13-19`
- [ ] **Eliminar GitHub Secrets obsoletos**: `COMUNICADOS_CSV_URL`, `PALMARES_CSV_URL`, `PARTICIPACION_CSV_URL` ya no las lee el código (v4.2 las purgó del workflow). Borrarlas en *Settings → Secrets and variables → Actions*.

## Técnico

- [x] **Import incorrecto** — `web/routes/admin.py:8` importa `get_file_metadata` desde `core.utils`; debería ser `from core.sdk.gcp` (la función ya está ahí)
- [x] **Default `--platforms` en `.bazelrc`** — `--test_output=errors` como default de test; `--config=gcp` para builds de imagen
- [x] **Pin `Dockerfile.base` por digest SHA** — `python:3.12-slim@sha256:4386a385...`
- [x] **`TEMPORADA_ACTUAL` duplicado** — centralizado en `env.TEMPORADA_ACTUAL` del `deploy.yml`; ambos config leen `os.getenv`
- [x] **Selenium fuera del teams_analyzer** — v4.2 reemplaza Selenium + Analítica Fantasy por la API privada de Jornada Perfecta (1 request HTTP en vez de 600 acciones de browser).
- [ ] **Reconstruir `Dockerfile.base`** — todavía instala `selenium`, `webdriver-manager`, `trio*`, `pytz`. La imagen actual en GCP funciona porque está pineada por digest, pero la siguiente regeneración debe partir del `requirements_lock.txt` actual (sin esas deps) y empujar un nuevo digest a `MODULE.bazel`.
- [ ] **Arreglar target Docker de teams_analyzer** — `packages/biwenger_tools/teams_analyzer:teams_analyzer_image_local` referencia `@debian_base_image` (no definido en `MODULE.bazel`). Migrar al patrón `python_service` o `@python_with_deps` antes de poder hacer rebuild + push a GCP.

## Producto

- [ ] **Sección VAR en web** — revisar y conectar trigger manual del AI scraper o cron job
- [ ] **Deploy teams_analyzer a GCP** — bloqueado por el target Docker roto (ver "Técnico")
- [ ] **Nuevo proyecto Google para fotos**

## Arquitectura (medio plazo)

- [x] **Domain models aplicados** — `LeagueMessage`, `Participation`, `Clausulazo`, `JusticeEntry` con `from_csv_row`/`to_csv_row` ya se usan en scraper (escritura) y web (lectura). El call site del CSV-as-DB queda contenido en una capa: facilita la futura migración a Firestore.
- [ ] **Migración CSV → Firestore** — el plan original (`memory/project_firestore_migration.md`) ya no existe; los modelos de dominio están listos para que el cambio sea localizado en lecturas/escrituras GCP en lugar de tocar todos los call sites.
- [ ] **teams_analyzer Fase 2** — bot interactivo en Telegram (`/analizar`, `/alinear`). Ver `.claude/plans/teams_analyzer_rewrite.md`.
- [ ] **teams_analyzer Fase 3** — auto-alineación vía `PUT /api/v2/user`. Ver el mismo plan.
