# TODO

## Prioritario

- [x] **GitHub Actions secrets** — todos añadidos en el repo
- [ ] **Primer deploy via CI** — commitear y pushear a `master` para disparar el workflow
- [ ] **Auditar y rotar SA key** si la del repo es la real (~30min)
- [ ] **Mover IDs de Drive/Sheets a Secret Manager / env** — actualmente hardcodeados en `packages/biwenger_tools/web/BUILD.bazel:13-19`

## Técnico

- [x] **Import incorrecto** — `web/routes/admin.py:8` importa `get_file_metadata` desde `core.utils`; debería ser `from core.sdk.gcp` (la función ya está ahí)
- [x] **Default `--platforms` en `.bazelrc`** — `--test_output=errors` como default de test; `--config=gcp` para builds de imagen
- [x] **Pin `Dockerfile.base` por digest SHA** — `python:3.12-slim@sha256:4386a385...`
- [x] **`TEMPORADA_ACTUAL` duplicado** — centralizado en `env.TEMPORADA_ACTUAL` del `deploy.yml`; ambos config leen `os.getenv`
- [ ] **Separar Selenium de imagen base** — `Dockerfile.base` instala Selenium (~150MB) que solo usa `teams_analyzer`; pendiente de decidir el futuro de ese módulo

## Producto

- [ ] **Sección VAR en web** — revisar y conectar trigger manual del AI scraper o cron job
- [ ] **Deploy teams_analyzer a GCP** — si confirma coste $0
- [ ] **Nuevo proyecto Google para fotos**

## Arquitectura (medio plazo)

- [ ] **Migración CSV → Firestore** — ver `memory/project_firestore_migration.md` para el plan completo (~16h, $0/mes)
- [ ] **Definir estado de teams_analyzer** — deprecar con EOL, archivar en rama, o recuperar y actualizar
