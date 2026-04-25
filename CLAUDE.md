# CLAUDE.md — lillorepo

Monorepo Bazel con proyectos Python orientados a Google Cloud. Actualmente contiene `biwenger_tools`; la arquitectura está pensada para crecer con más packages.

## Estructura

```
/core           Librerías compartidas (SDK Biwenger, GCP, Telegram; utils)
/packages       Proyectos autocontenidos
  biwenger_tools/
    scraper_job/    Scraper de mensajes de la liga → CSV → Google Drive
    teams_analyzer/ Análisis de equipos Biwenger → CSV → Telegram
    web/            Flask app en Cloud Run para visualizar datos
/docker         Configuraciones Docker
/docs           Documentación (operations.md = referencia de comandos)
/scripts        Scripts de utilidad (limpieza GCP, costes)
/tools          Extensiones y herramientas Bazel
/platforms      Definiciones de plataformas (linux_amd64, etc.)
```

## Stack

- **Build:** Bazel (bazelisk)
- **Lenguaje:** Python 3
- **Cloud:** GCP — Cloud Run, Cloud Run Jobs, Secret Manager, Artifact Registry
- **Otros:** Flask, Selenium, Docker

## Comandos clave

Ver `docs/operations.md` para referencia completa. Resumen rápido:

```bash
# Build completo
bazel build //...

# Tests (cualquier módulo)
bazel test //packages/biwenger_tools/web:web_tests --test_output=streamed --test_arg=-v
bazel test //packages/biwenger_tools/scraper_job:scraper_job_tests --test_output=streamed --test_arg=-v
bazel test //packages/biwenger_tools/teams_analyzer:teams_analyzer_tests --test_output=streamed --test_arg=-v
bazel test //core:core_tests --test_output=streamed --test_arg=-v

# Run local
bazel run //packages/biwenger_tools/web:web_local
bazel run //packages/biwenger_tools/scraper_job:scraper_job_local
bazel run //packages/biwenger_tools/teams_analyzer:teams_analyzer_local

# Deploy (web)
bazel run //packages/biwenger_tools/web:push_image_to_gcp --platforms=//platforms:linux_amd64
cd packages/biwenger_tools/web/ && ./deploy.sh
```

## Gestión de dependencias Python

Sistema de tres niveles: `[módulo]/requirements.txt` → `requirements.in` (autogenerado) → `requirements_lock.txt` (lock para Bazel).

Nunca editar `requirements.in` ni `requirements_lock.txt` a mano. Flujo:
1. Editar `[módulo]/requirements.txt`
2. Regenerar `requirements.in` con el script de concatenación
3. `pip-compile requirements.in -o requirements_lock.txt`
4. Añadir dep en el `BUILD.bazel` del módulo (`@pypi//nombre_lib`)

## Secretos

- **Local:** archivos `.env` en cada módulo (no commitear)
- **Producción:** Google Secret Manager

## Convenciones

- Linter: Flake8 (`max-line-length = 88`, compatible con Black)
- Formateador: Black (format on save en VS Code)
- Targets Bazel siguen el patrón `//packages/{package}/{módulo}:{target}`
- Los guiones en nombres de librerías PyPI se convierten a guiones bajos en Bazel (`@pypi//nombre_lib`)

## Notas para Claude

- Este repo crece con nuevos packages en `/packages/`. Al añadir uno, replicar la estructura de `biwenger_tools` como referencia.
- Los `BUILD.bazel` son la fuente de verdad de dependencias para Bazel.
- Ver `AGENTS.md` para contexto sobre los agentes del proyecto.
- **Commits:** always write commit messages in English. Do not add a `Co-Authored-By` line.
