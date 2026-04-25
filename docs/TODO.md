
- investigate avoiding Python package installs on GCP at every execution :O
- review VAR section in web → trigger AI scraper or cron job manually
- clean up AI-generated comments
- deploy teams-analyzer to GCP → if we hit $0 cost
- GitHub Actions :O
- Firestore?
- new Google project for photos
- agents?

---

# Audit técnico del repo (2026-04-25)

## Bazel / Build — Sólido

**Bien:**
- Migración Bzlmod completa y limpia, sin WORKSPACE residual
- Macro `biwenger_service.bzl` elimina duplicación: capas OCI separadas (local con secretos / GCP sin ellos)
- Lock file reproducible (requirements.in → requirements_lock.txt)
- Bazel 9.1.0, rules_oci 2.3, rules_pkg 1.2, rules_python 0.40 — todo actualizado

**Mejorar:**
- `.bazelrc` muy escueto — añadir `--test_output=errors` y `--platforms=//platforms:linux_amd64` como default para no pasarlo siempre en builds de imagen

---

## Seguridad — Riesgos reales

| Prioridad | Problema | Dónde |
|-----------|----------|-------|
| **Crítico** | `verify=False` en todas las requests HTTP | `core/sdk/biwenger.py:37,49,100` |
| **Alto** | IDs de Drive/Sheets hardcodeados en BUILD | `packages/biwenger_tools/web/BUILD.bazel:13-19` |
| **Alto** | Verificar si `biwenger-tools-sa.json` en scraper_job es la clave real y rotarla | `packages/biwenger_tools/scraper_job/` |
| **Medio** | `SECRET_KEY` de Flask — confirmar que viene de Secret Manager, no hardcodeado | `web/config.py` |

El `verify=False` es el más urgente — expone credenciales de Biwenger a ataques MITM en producción.

---

## Observabilidad — Punto ciego

Todo el codebase usa `print()`. En Cloud Run / Cloud Run Jobs los logs son texto plano ilegible: sin niveles, sin request IDs, sin correlación entre llamadas.

**Fix concreto:**
- Añadir `python-json-logger` a requirements
- Emitir JSON estructurado a stdout (Cloud Logging lo indexa automáticamente)
- Middleware en Flask que propague el header `x-request-id`

---

## Calidad de código — Web App

- `web/app.py` tiene 549 líneas con bloques try-except repetidos en varios routes — refactorizar en Blueprints (`comunicados`, `admin`, etc.)
- Los servicios de Drive/Sheets se inicializan en el import (`app.py:35-54`). Si GCP falla al arrancar, la app sube en estado degradado silenciosamente → mejor forzar el error en startup con el **app factory pattern**
- Validación de season con `"-" in season_from_url` es frágil → mejor regex `^20\d{2}-\d{2}$`
- `core/sdk/gcp.py`: `get_file_metadata()` hace una query Drive por archivo (N+1). No duele con 5 ficheros, pero no escala

---

## CI/CD — No existe

No hay `.github/workflows` ni `cloudbuild.yaml`. Deploys 100% manuales:
- No hay gate de tests antes de pushear imagen
- No hay linting automático
- No hay escaneo de vulnerabilidades en imágenes

**Mínimo viable:**
1. GitHub Actions: `bazel test` + `flake8` en cada PR
2. Cloud Build trigger en `main` para push de imagen automático

---

## Docker / Contenedores — Bien planteado, un detalle

**Bien:** imagen base pre-construida (`python-with-deps`) reduce cold starts y tamaño de capas. Separación local/GCP en la macro es elegante.

**Mejorar:** `docker/Dockerfile.base` usa `FROM python:3.12-slim` por tag, no por digest → para reproducibilidad total usar `python:3.12-slim@sha256:...`

---

## teams_analyzer — Estado ambiguo

Está en el repo, tiene BUILD.bazel, pero excluido de modernización y sin deploy. Hay que elegir:
- Documentarlo como deprecado con fecha de EOL
- Moverlo a rama archivada
- Recuperarlo y actualizarlo (deploy a GCP si $0 cost — ya está en el TODO de arriba)

---

## Docs — Punto fuerte

`CLAUDE.md` y `operations.md` están muy bien. Lo que falta:
- Diagrama de arquitectura (mermaid en docs/)
- Runbook de fallos comunes ("Cloud Run Job timeout", "CSV upload falla")

---

## Ranking por impacto

| # | Acción | Esfuerzo estimado |
|---|--------|-------------------|
| 1 | Fix `verify=False` en `core/sdk/biwenger.py` | 1h |
| 2 | Structured logging con JSON a stdout | 4h |
| 3 | Auditar y rotar SA key si es la real | 30min |
| 4 | Mover IDs de Drive/Sheets a Secret Manager / env | 1h |
| 5 | CI/CD básico con GitHub Actions | 3h |
| 6 | Refactor `web/app.py` en Blueprints | 3h |
| 7 | App factory pattern en Flask | 2h |
| 8 | Pin `Dockerfile.base` por digest SHA | 15min |
| 9 | Default `--platforms` en `.bazelrc` | 5min |
| 10 | Definir estado de teams_analyzer | 30min |
