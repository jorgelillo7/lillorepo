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

- [x] **Import incorrecto** — `web/routes/admin.py:8` importa `get_file_metadata` desde `core.utils`; debería ser `from core.sdk.gcp` (la función ya está ahí)
- [x] **Default `--platforms` en `.bazelrc`** — `--test_output=errors` como default de test; `--config=gcp` para builds de imagen
- [x] **Pin `Dockerfile.base` por digest SHA** — `python:3.12-slim@sha256:4386a385...`
- [x] **`TEMPORADA_ACTUAL` duplicado** — centralizado en `env.TEMPORADA_ACTUAL` del `deploy.yml`; ambos config leen `os.getenv`
- [x] **Selenium fuera del teams_analyzer** — v4.2 reemplaza Selenium + Analítica Fantasy por la API privada de Jornada Perfecta (1 request HTTP en vez de 600 acciones de browser).
- [x] **Arreglar target Docker de teams_analyzer** — migrado al patrón de `scraper_job` (`@python_with_deps` + `entrypoint.sh` propio + capas de código separadas). Añadido `push_image_to_gcp` y `load_image_to_docker_local`. `bazel build //...` ahora pasa entero por primera vez tras la migración a bzlmod.
- [ ] **Reconstruir `Dockerfile.base`** — en curso en PR #4. Sincroniza la lista con `requirements_lock.txt` (drop selenium/pytz/trio*) y reempuja el digest a `MODULE.bazel`. Bloqueante implícito para Fase A (deploy del analyzer) porque la imagen actual está al límite del free tier de Artifact Registry.
- [ ] **Arreglar `scripts/clean-images-artifact.sh`** — en curso en PR #4. El script no borraba nada por dos bugs (`get(digest)` vacío y `NOT TAGS:*` cogiendo hijos del manifest list actual). Sin el fix, subir más imágenes cruza el free tier de AR.

## Producto

- [ ] **Deploy teams_analyzer a GCP** — Cloud Run Job + Scheduler diario 16:00 Madrid. Ver Fase A en `.claude/plans/next_phases.md`. Requiere PR #4 mergeado.
- [ ] **teams_analyzer Fase 2** — webhook Telegram en el Flask web para `/analizar`. Ver Fase B en `.claude/plans/next_phases.md`.
- [ ] **teams_analyzer Fase 3** — auto-alineación. **Bloqueado por research previo** sobre multi-posición en la API de Biwenger. Ver Fase C en `.claude/plans/next_phases.md`.
- [ ] **Sección VAR en web** — revisar y conectar trigger manual del AI scraper o cron job
- [ ] **Nuevo proyecto Google para fotos**

## Arquitectura (medio plazo)

- [x] **Domain models aplicados** — `LeagueMessage`, `Participation`, `Clausulazo`, `JusticeEntry` con `from_csv_row`/`to_csv_row` ya se usan en scraper (escritura) y web (lectura). El call site del CSV-as-DB queda contenido en una capa: facilita la futura migración a Firestore.
- [ ] **Migración CSV → Firestore** — los modelos de dominio están listos para que el cambio sea localizado en lecturas/escrituras GCP en lugar de tocar todos los call sites. Sin urgencia, ver project_pitch.md para narrativa.
- [ ] **Bumps de dependencias** — ver Fase D en `.claude/plans/next_phases.md`. `rules_python` 0.40→2.0 y `platforms` 0.0.10→1.1 son los únicos urgentes (warnings activos en cada `bazel build`).
