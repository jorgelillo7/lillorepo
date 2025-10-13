# 🛠️ OPERATIONS - Biwenger Tools

Esta guía centraliza los comandos y flujos de trabajo para el **desarrollo, testing, despliegue y mantenimiento** de las herramientas de Biwenger.

📜 Índice

- [🛠️ OPERATIONS - Biwenger Tools](#️-operations---biwenger-tools)
  - [📋 Requisitos Previos](#-requisitos-previos)
  - [🚀 Módulos del Proyecto](#-módulos-del-proyecto)
    - [1. Biwenger Web App](#1-biwenger-web-app)
    - [2. Scraper Job](#2-scraper-job)
    - [3. Teams Analyzer](#3-teams-analyzer)
    - [Extra. Core](#extra-core)
  - [📦 Cómo Añadir o Actualizar Dependencias de Python](#-cómo-añadir-o-actualizar-dependencias-de-python)
    - [### Paso 1: Añade la librería al `requirements.txt` del Módulo](#-paso-1-añade-la-librería-al-requirementstxt-del-módulo)
    - [### Paso 2: Regenera el `requirements.in` Central](#-paso-2-regenera-el-requirementsin-central)
    - [### Paso 3: Regenera el Fichero de Lock](#-paso-3-regenera-el-fichero-de-lock)
    - [### Paso 4: Usa la Nueva Librería en el `BUILD.bazel`](#-paso-4-usa-la-nueva-librería-en-el-buildbazel)
    - [### Paso 5: Verifica con Bazel](#-paso-5-verifica-con-bazel)
  - [🔐 Gestión de Secretos](#-gestión-de-secretos)
    - [Ejemplos de creación de secretos en GCP](#ejemplos-de-creación-de-secretos-en-gcp)
    - [Para actualizar un secreto (ej. token.json):](#para-actualizar-un-secreto-ej-tokenjson)
  - [💅 Linter y Formateador Automático (VS Code)](#-linter-y-formateador-automático-vs-code)
  - [🧹 Limpieza y Control de Costes en GCP](#-limpieza-y-control-de-costes-en-gcp)
    - [Artifact Registry](#artifact-registry)
  - [⚠️ Notas Importantes](#️-notas-importantes)


## 📋 Requisitos Previos

Antes de empezar, asegúrate de tener instalado lo siguiente:

  * **Python 3.x**
  * **Visual Studio Code** con la extensión [Bazel (The Bazel Team)](https://marketplace.visualstudio.com/items?itemName=BazelBuild.vscode-bazel).
  * **Herramientas de línea de comandos:**
    ```bash
      brew install bazelisk
      brew install buildifier
    ```
  * **Despliegue en Google Cloud:**
  ```bash
    gcloud auth login
    gcloud config set project biwenger-tools
    gcloud auth configure-docker europe-southwest1-docker.pkg.dev
  ```

**Nota importante:** Se utiliza un único entorno virtual en la raíz del proyecto para simplificar la gestión de dependencias y evitar conflictos entre módulos.

  ```bash
    python3 -m venv venv
    source venv/bin/activate  # En Windows: .venv\Scripts\activate

    pip install -e core/requirements.txt
    pip install -r web/requirements.txt
    pip install -r scraper_job/requirements.txt
    pip install -r teams_analyzer/requirements.txt
    pip install pip-tools
  ```

## 🚀 Módulos del Proyecto

Aquí se describen los comandos para ejecutar cada componente

### 1\. Biwenger Web App

  * **🏠 Ejecutar en local (servidor de desarrollo):**

    ```bash
      bazel run //packages/biwenger_tools/web:web_local
    ```
  * **🧪 Tests:**
    ```
      bazel test //packages/biwenger_tools/web:web_tests --test_output=streamed --test_arg=-v
      bazel test //packages/biwenger_tools/web:web_tests --test_output=streamed --test_arg=-v --cache_test_results=no

      pytest packages/biwenger_tools/web/tests/
    ```

  * **🐳 Ejecutar con Docker localmente:**

    ```bash
      # Bajamos imagen base
      docker pull europe-southwest1-docker.pkg.dev/biwenger-tools/biwenger-docker/python-base:latest

      # Cargar la imagen en Docker
      bazel run //packages/biwenger_tools/web:load_image_to_docker_local

      # Iniciar el contenedor
      docker run --rm -p 8080:8080 bazel/web:local
    ```

    > **Consejo:** Si `Ctrl+C` no detiene el contenedor, usa `docker ps` para encontrar su ID y luego `docker kill <container_id>`.

  * **☁️ Desplegar en producción:**

    ```bash
      # Empaquetar y subir la imagen a GCP
      bazel run //packages/biwenger_tools/web:push_image_to_gcp --platforms=//platforms:linux_amd64

      # Ejecutar el script de despliegue
      cd packages/biwenger_tools/web/
      ./deploy.sh
    ```

    URL: https://biwenger-summary-pjpqofuevq-no.a.run.app/25-26/

### 2\. Scraper Job

  * **Ejecutar en local:**

    ```bash
        bazel run //packages/biwenger_tools/scraper_job:scraper_job_local
    ```

  * **Tests:**

    ```bash
      # Ejecutar tests con Bazel (salida detallada)
      bazel test //packages/biwenger_tools/scraper_job:scraper_job_tests --test_output=streamed --test_arg=-v

      # Forzar la ejecución de tests ignorando la caché
      bazel test //packages/biwenger_tools/scraper_job:scraper_job_tests --test_output=streamed --test_arg=-v --cache_test_results=no

      # Ejecutar tests directamente con pytest (requiere venv activado)
      pytest packages/biwenger_tools/scraper_job/tests/
    ```

  * **Ejecutar con Docker localmente:**

    ```bash
        # Cargar la imagen en Docker (con secretos locales incluidos)
        bazel run //packages/biwenger_tools/scraper_job:load_image_to_docker_local

        # Iniciar el contenedor
        docker run --rm bazel/scraper_job:local
    ```

  * **Desplegar en producción (Cloud Run Job):**

      * **Construir y subir la imagen a GCP:**
        ```bash
            bazel run //packages/biwenger_tools/scraper_job:push_image_to_gcp --platforms=//platforms:linux_amd64
        ```
      * **Crear el Job (solo la primera vez):**
        ```bash
          gcloud run jobs create biwenger-scraper-data \
              --image europe-southwest1-docker.pkg.dev/biwenger-tools/biwenger-docker/scraper_job \
              --region europe-southwest1 \
              --set-secrets="/gdrive_sa/biwenger-tools-sa.json=biwenger-tools-sa-regional:latest" \
              --set-secrets="/biwenger_email/biwenger-email=biwenger-email-regional:latest" \
              --set-secrets="/biwenger_password/biwenger-password=biwenger-password-regional:latest" \
              --set-secrets="/gdrive_folder_id/gdrive-folder-id=gdrive-folder-id-regional:latest"
        ```
      * **Actualizar el Job (al cambiar la imagen o los secretos):**
        ```bash
          gcloud run jobs update biwenger-scraper-data \
              --image europe-southwest1-docker.pkg.dev/biwenger-tools/biwenger-docker/scraper_job \
              --region europe-southwest1
        ```
      * **Ejecutar el Job manualmente:**
        ```bash
          gcloud run jobs execute biwenger-scraper-data --region europe-southwest1
        ```

### 3\. Teams Analyzer

  * **Configuración:** Asegúrate de tener un archivo `.env` con las credenciales de Biwenger y Telegram.

  * **Ejecutar en local:**

    ```bash
        bazel run //packages/biwenger_tools/teams_analyzer:teams_analyzer_local

        #obtener los archivos para debug
        bazel run --spawn_strategy=local //packages/biwenger_tools/teams_analyzer:teams_analyzer_local
        open bazel-bin/packages/biwenger_tools/teams_analyzer/teams_analyzer_local.runfiles/_main/packages/biwenger_tools/teams_analyzer

        analitica_fantasy_data_backup.csv
        squads_export.csv
    ```
  * **Tests:**

    ```bash
      # Ejecutar tests con Bazel (salida detallada)
      bazel test //packages/biwenger_tools/teams_analyzer:teams_analyzer_tests --test_output=streamed --test_arg=-v

      # Forzar la ejecución de tests ignorando la caché
      bazel test //packages/biwenger_tools/teams_analyzer:teams_analyzer_tests --test_output=streamed --test_arg=-v --cache_test_results=no

      # Ejecutar tests directamente con pytest (requiere venv activado)
      pytest packages/biwenger_tools/teams_analyzer/tests/
    ```

  * **Ejecutar con Docker localmente:**

    ```bash
      bazel run //packages/biwenger_tools/teams_analyzer:load_image_to_docker_local
      docker run --rm --shm-size=2g bazel/teams_analyzer:local
    ```
  * **Desplegar en producción:**
    Pendiente

### Extra\. Core

  * **Tests:**
    ```
      bazel test //core:core_tests --test_output=streamed --test_arg=-v
      bazel test //core:core_tests --test_output=streamed --test_arg=-v --cache_test_results=no

      pytest core/tests/
    ```

-----

## 📦 Cómo Añadir o Actualizar Dependencias de Python

Nuestro proyecto usa un sistema de tres niveles para gestionar las dependencias, manteniendo los módulos aislados y garantizando builds 100% reproducibles.

1.  **`[módulo]/requirements.txt`** (ej: `core/requirements.txt`): Es el **punto de partida y la fuente de verdad**. Aquí es donde tú, como desarrollador, añades o quitas las librerías que necesita un módulo específico.
2.  **`requirements.in`**: Es un fichero **intermedio y autogenerado**. Consolida las listas de todos los módulos en un solo lugar para la siguiente herramienta. **Nunca debes editar este fichero a mano.**
3.  **`requirements_lock.txt`**: Es el **fichero final y bloqueado** que genera el ordenador. Contiene la lista exacta de todas las librerías (directas e indirectas) con sus versiones y hashes, que es lo que Bazel usa. **Nunca debes editar este fichero a mano.**

El flujo de trabajo para añadir una nueva librería (usaremos `numpy` en el módulo `core` como ejemplo) es el siguiente:

### \#\#\# Paso 1: Añade la librería al `requirements.txt` del Módulo

Decides que el módulo `core` necesita `numpy`. Abres `core/requirements.txt` y lo añades.

**Fichero: `core/requirements.txt`**

```diff
requests
google-api-python-client
google-auth-oauthlib
google-auth
pytz
python-dateutil
black
flake8
pytest
requests-mock
+ numpy
```

-----

### \#\#\# Paso 2: Regenera el `requirements.in` Central

Ahora, ejecuta este comando desde la raíz del proyecto. Recogerá los cambios que hiciste en `core/requirements.txt` y actualizará el fichero central.

```bash
{
  for req_file in core/requirements.txt scraper_job/requirements.txt teams_analyzer/requirements.txt web/requirements.txt; do
    echo; echo "# From: $req_file"; cat "$req_file";
  done
} > requirements.in
```

-----

### \#\#\# Paso 3: Regenera el Fichero de Lock

Este comando lee el `requirements.in` que acabas de generar y resuelve todas las dependencias, creando el `requirements_lock.txt` final.

*(Recuerda tener `pip-tools` instalado: `pip install pip-tools`)*

```bash
pip-compile requirements.in -o requirements_lock.txt
```

-----

### \#\#\# Paso 4: Usa la Nueva Librería en el `BUILD.bazel`

Ahora que la librería ya está disponible para Bazel, ve a `core/BUILD.bazel` y añádela a la lista de dependencias (`deps`) del `py_library`.

Recuerda que Bazel convierte los guiones (-) a guiones bajos (_). Para numpy, el nombre es el mismo.

**Fichero: `core/BUILD.bazel`**

```python
py_library(
    name = "core",
    srcs = glob(["*.py"]),
    deps = [
        "@pypi//requests",
        # ... (resto de dependencias)
        # Añadimos la nueva dependencia
        "@pypi//numpy",
    ],
    visibility = ["//visibility:public"],
)
```

-----

### \#\#\# Paso 5: Verifica con Bazel

Finalmente, ejecuta un comando de Bazel para confirmar que todo funciona.

  ```bash
  bazel build //...

  ```

Si el comando termina con éxito, has añadido la dependencia de forma limpia, aislada y reproducible.



## 🔐 Gestión de Secretos

  * **Desarrollo local:** Utiliza archivos `.env` en la raíz de cada módulo.
  * **Producción:** Usa **Google Secret Manager**.

### Ejemplos de creación de secretos en GCP
```bash
# Crear secreto desde un archivo (ej: service account)
gcloud secrets create biwenger-tools-sa-regional \
  --data-file="biwenger-tools-sa.json" \
  --replication-policy="user-managed" \
  --locations="$REGION"

# Crear secretos desde la línea de comandos
echo -n "TU_EMAIL@gmail.com" | gcloud secrets create biwenger-email-regional \
  --data-file=- \
  --replication-policy="user-managed" \
  --locations="$REGION"

echo -n "TU_CONTRASEÑA" | gcloud secrets create biwenger-password-regional \
  --data-file=- \
  --replication-policy="user-managed" \
  --locations="$REGION"

echo -n "ID_DE_LA_CARPETA_DE_DRIVE" | gcloud secrets create gdrive-folder-id-regional \
  --data-file=- \
  --replication-policy="user-managed" \
  --locations="$REGION"
```

### Para actualizar un secreto (ej. token.json):
```bash
gcloud secrets versions add token_json --data-file="token.json"
```

---
## 💅 Linter y Formateador Automático (VS Code)

Configura **Flake8** (linter) y **Black** (formateador) para mantener un código limpio y consistente.

1.  **Instala las extensiones:**

      * `ms-python.python`
      * `ms-python.black-formatter`

2.  **Selecciona el Intérprete de Python:**

      * Abre la paleta de comandos (`Ctrl+Shift+P` o `Cmd+Shift+P`).
      * Busca y selecciona `Python: Select Interpreter`.
      * Elige el intérprete de tu entorno virtual (`./venv/bin/python`).

3.  **Configura el `settings.json`:**

      * Abre la paleta de comandos y busca `Preferences: Open Workspace Settings (JSON)`.
      * Añade la siguiente configuración:

    <!-- end list -->

    ```json
    {
        "python.linting.enabled": true,
        "python.linting.flake8Enabled": true,
        "editor.defaultFormatter": "ms-python.black-formatter",
        "editor.formatOnSave": true,
        "editor.codeActionsOnSave": {
            "source.fixAll": "explicit"
        }
    }
    ```

4.  **(Opcional) Configura Flake8:**

      * Crea un archivo `.flake8` en la raíz del proyecto para alinear sus reglas con Black.

    <!-- end list -->

    ```ini
    [flake8]
    max-line-length = 88
    ignore = E203, W503
    exclude = .git,__pycache__,.venv,venv,*.md
    ```

Una vez configurado, VS Code te marcará errores y formateará tu código automáticamente al guardar.


## 🧹 Limpieza y Control de Costes en GCP

### Artifact Registry

  * **Crear el repositorio Docker (solo la primera vez):**

    ```bash
    gcloud artifacts repositories create biwenger-docker \
        --repository-format=docker \
        --location=europe-southwest1 \
        --description="Docker images for Biwenger Tools"
    ```

  * **Listar imágenes en el repositorio:**

    ```bash
    gcloud artifacts docker images list europe-southwest1-docker.pkg.dev/biwenger-tools/biwenger-docker
    ```

  * **Limpiar imágenes antiguas (script):**

    ```bash
    cd scripts/
    ./clean-images-artifact.sh
    ```

    > Este script elimina todas las imágenes antiguas, conservando solo la etiquetada como `latest`.

  * **Revisar costes (script):**

    ```bash
    cd scripts/
    ./check-gcp-costs.sh
    ```

    > Este script compara el uso de **Artifact Registry** y **Cloud Run** con el *Free Tier* de GCP.

    * **Limpiar contenedores docker:**
    ```
     docker image prune -f
     ```

-----

## ⚠️ Notas Importantes

  * **No subas a git** el archivo de credenciales `biwenger-tools-sa.json`.
  * Si un despliegue falla, revisa los **logs en la consola de GCP** (Cloud Run, Cloud Build, etc.).
  * Asegúrate de tener un archivo `.env` configurado en cada módulo para el desarrollo local.