# 🛠️ OPERATIONS - Biwenger Tools

This guide centralises commands and workflows for **development, testing, deployment, and maintenance** of the Biwenger tools.

📜 Index

- [🛠️ OPERATIONS - Biwenger Tools](#️-operations---biwenger-tools)
  - [📋 Prerequisites](#-prerequisites)
  - [🚀 Project Modules](#-project-modules)
    - [1. Biwenger Web App](#1-biwenger-web-app)
    - [2. Scraper Job](#2-scraper-job)
    - [3. Teams Analyzer](#3-teams-analyzer)
    - [Extra. Core](#extra-core)
  - [📦 How to Add or Update Python Dependencies](#-how-to-add-or-update-python-dependencies)
    - [Step 1: Add the library to the module's `requirements.txt`](#step-1-add-the-library-to-the-modules-requirementstxt)
    - [Step 2: Regenerate the central `requirements.in`](#step-2-regenerate-the-central-requirementsin)
    - [Step 3: Regenerate the Lock File](#step-3-regenerate-the-lock-file)
    - [Step 4: Use the new library in `BUILD.bazel`](#step-4-use-the-new-library-in-buildbazel)
    - [Step 5: Verify with Bazel](#step-5-verify-with-bazel)
  - [🔐 Secrets Management](#-secrets-management)
    - [Examples: creating secrets in GCP](#examples-creating-secrets-in-gcp)
    - [Updating a secret (e.g. token.json)](#updating-a-secret-eg-tokenjson)
  - [💅 Linter and Auto-formatter (VS Code)](#-linter-and-auto-formatter-vs-code)
  - [🧹 GCP Cleanup and Cost Control](#-gcp-cleanup-and-cost-control)
    - [Artifact Registry](#artifact-registry)
  - [⚠️ Important Notes](#️-important-notes)


## 📋 Prerequisites

Before you start, make sure you have the following installed:

  * **Python 3.x**
  * **Visual Studio Code** with the [Bazel (The Bazel Team)](https://marketplace.visualstudio.com/items?itemName=BazelBuild.vscode-bazel) extension.
  * **Command-line tools:**
    ```bash
      brew install bazelisk
      brew install buildifier
    ```
  * **Google Cloud deployment:**
  ```bash
    gcloud auth login
    gcloud config set project biwenger-tools
    gcloud auth configure-docker europe-southwest1-docker.pkg.dev
  ```

**Important note:** Bazel manages all Python dependencies hermetically — no venv is needed to run, test, or build. A venv is only required for `pip-tools` (used to regenerate the lock file) and for IDE integration (linting, autocomplete).

  ```bash
    # Only needed for dependency management and IDE support
    python3 -m venv venv
    source venv/bin/activate
    pip install pip-tools
  ```

## 🚀 Project Modules

Commands for running each component.

### 1\. Biwenger Web App

  * **🏠 Run locally (development server):**

    ```bash
      bazel run //packages/biwenger_tools/web:web_local
    ```
  * **🧪 Tests:**
    ```
      bazel test //packages/biwenger_tools/web:web_tests --test_output=streamed --test_arg=-v
      bazel test //packages/biwenger_tools/web:web_tests --test_output=streamed --test_arg=-v --cache_test_results=no

      pytest packages/biwenger_tools/web/tests/
    ```

  * **🐳 Run with Docker locally:**

    Useful for validating the production container (gunicorn + entrypoint.sh) before deploying.

    ```bash
      # Build and load the image into the local Docker daemon
      bazel run //packages/biwenger_tools/web:load_image_to_docker_local

      # Start the container
      docker run --rm -p 8080:8080 bazel/web:local
    ```

    > **Tip:** If `Ctrl+C` does not stop the container, use `docker ps` to find the container ID and then `docker kill <container_id>`.

  * **☁️ Deploy to production:**

    ```bash
      # Package and push the image to GCP
      bazel run //packages/biwenger_tools/web:push_image_to_gcp --platforms=//platforms:linux_amd64

      # Run the deploy script
      cd packages/biwenger_tools/web/
      ./deploy.sh
    ```

    URL: https://biwenger-summary-pjpqofuevq-no.a.run.app/25-26/

### 2\. Scraper Job

  * **Run locally:**

    ```bash
        bazel run //packages/biwenger_tools/scraper_job:scraper_job_local
    ```

  * **Tests:**

    ```bash
      # Run tests with Bazel (verbose output)
      bazel test //packages/biwenger_tools/scraper_job:scraper_job_tests --test_output=streamed --test_arg=-v

      # Force test run ignoring cache
      bazel test //packages/biwenger_tools/scraper_job:scraper_job_tests --test_output=streamed --test_arg=-v --cache_test_results=no

      # Run tests directly with pytest (requires venv activated)
      pytest packages/biwenger_tools/scraper_job/tests/
    ```

  * **Run with Docker locally:**

    Useful for validating the exact Cloud Run Job container before deploying.

    ```bash
        # Build and load the image into the local Docker daemon (secrets included)
        bazel run //packages/biwenger_tools/scraper_job:load_image_to_docker_local

        # Start the container
        docker run --rm bazel/scraper_job:local
    ```

  * **Deploy to production (Cloud Run Job):**

      * **Build and push the image to GCP:**
        ```bash
            bazel run //packages/biwenger_tools/scraper_job:push_image_to_gcp --platforms=//platforms:linux_amd64
        ```
      * **Create the Job (first time only):**
        ```bash
          gcloud run jobs create biwenger-scraper-data \
              --image europe-southwest1-docker.pkg.dev/biwenger-tools/biwenger-docker/scraper_job \
              --region europe-southwest1 \
              --set-secrets="/gdrive_sa/biwenger-tools-sa.json=biwenger-tools-sa-regional:latest" \
              --set-secrets="/biwenger_email/biwenger-email=biwenger-email-regional:latest" \
              --set-secrets="/biwenger_password/biwenger-password=biwenger-password-regional:latest" \
              --set-secrets="/gdrive_folder_id/gdrive-folder-id=gdrive-folder-id-regional:latest"
        ```
      * **Update the Job (when changing the image or secrets):**
        ```bash
          gcloud run jobs update biwenger-scraper-data \
              --image europe-southwest1-docker.pkg.dev/biwenger-tools/biwenger-docker/scraper_job \
              --region europe-southwest1 \
              --update-env-vars TEMPORADA_ACTUAL=25-26
        ```
      * **Execute the Job manually:**
        ```bash
          gcloud run jobs execute biwenger-scraper-data --region europe-southwest1
        ```

### 3\. Teams Analyzer

  * **Setup:** Make sure you have a `.env` file with Biwenger and Telegram credentials.

  * **Run locally:**

    ```bash
        bazel run //packages/biwenger_tools/teams_analyzer:teams_analyzer_local

        # Get output files for debugging
        bazel run --spawn_strategy=local //packages/biwenger_tools/teams_analyzer:teams_analyzer_local
        open bazel-bin/packages/biwenger_tools/teams_analyzer/teams_analyzer_local.runfiles/_main/packages/biwenger_tools/teams_analyzer

        analitica_fantasy_data_backup.csv
        squads_export.csv
    ```
  * **Tests:**

    ```bash
      # Run tests with Bazel (verbose output)
      bazel test //packages/biwenger_tools/teams_analyzer:teams_analyzer_tests --test_output=streamed --test_arg=-v

      # Force test run ignoring cache
      bazel test //packages/biwenger_tools/teams_analyzer:teams_analyzer_tests --test_output=streamed --test_arg=-v --cache_test_results=no

      # Run tests directly with pytest (requires venv activated)
      pytest packages/biwenger_tools/teams_analyzer/tests/
    ```

  * **Run with Docker locally:**

    ```bash
      bazel run //packages/biwenger_tools/teams_analyzer:load_image_to_docker_local
      docker run --rm --shm-size=2g bazel/teams_analyzer:local
    ```
  * **Deploy to production:**
    Pending

### Extra\. Core

  * **Tests:**
    ```
      bazel test //core:core_tests --test_output=streamed --test_arg=-v
      bazel test //core:core_tests --test_output=streamed --test_arg=-v --cache_test_results=no

      pytest core/tests/
    ```

-----

## 📦 How to Add or Update Python Dependencies

The project uses a three-level system to manage dependencies, keeping modules isolated and guaranteeing 100% reproducible builds.

1.  **`[module]/requirements.txt`** (e.g. `core/requirements.txt`): The **starting point and source of truth**. This is where you, as a developer, add or remove the libraries a specific module needs.
2.  **`requirements.in`**: An **intermediate, auto-generated file**. It consolidates the lists from all modules into a single place for the next tool. **Never edit this file by hand.**
3.  **`requirements_lock.txt`**: The **final, locked file** generated by the computer. It contains the exact list of all libraries (direct and indirect) with their versions and hashes — what Bazel uses. **Never edit this file by hand.**

The workflow for adding a new library (using `numpy` in the `core` module as an example):

### Step 1: Add the library to the module's `requirements.txt`

Decide that the `core` module needs `numpy`. Open `core/requirements.txt` and add it.

**File: `core/requirements.txt`**

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

### Step 2: Regenerate the central `requirements.in`

Run this command from the project root. It will pick up the changes you made in `core/requirements.txt` and update the central file.

```bash
{
  for req_file in core/requirements.txt \
    packages/biwenger_tools/scraper_job/requirements.txt \
    packages/biwenger_tools/teams_analyzer/requirements.txt \
    packages/biwenger_tools/web/requirements.txt; do
    echo; echo "# From: $req_file"; cat "$req_file"
  done
} > requirements.in
```

-----

### Step 3: Regenerate the Lock File

This command reads the `requirements.in` you just generated and resolves all dependencies, creating the final `requirements_lock.txt`.

*(Remember to have `pip-tools` installed: `pip install pip-tools`)*

```bash
pip-compile requirements.in -o requirements_lock.txt
```

-----

### Step 4: Use the new library in `BUILD.bazel`

Now that the library is available to Bazel, go to `core/BUILD.bazel` and add it to the `deps` list of the **most specific sub-target** that needs it.

`core/BUILD.bazel` exposes granular targets — use the right one to avoid bloating other packages:

| Target | When to add here |
|---|---|
| `//core:gcp` | Library used by `sdk/gcp.py` or `utils.py` |
| `//core:telegram` | Library used by `sdk/telegram.py` |
| `//core:biwenger` | Library used by `sdk/biwenger.py` |
| `//core` (umbrella) | Shared by all of the above |

Remember that Bazel converts hyphens (-) to underscores (_). For numpy, the name is the same.

**File: `core/BUILD.bazel`** (example: adding `numpy` to the `gcp` target)

```python
py_library(
    name = "gcp",
    srcs = ["sdk/gcp.py", "utils.py"],
    deps = [
        ":_init",
        "@pypi//google_api_python_client",
        # ... (other dependencies)
        # Add the new dependency
        "@pypi//numpy",
    ],
    visibility = ["//visibility:public"],
)
```

-----

### Step 5: Verify with Bazel

Finally, run a Bazel command to confirm everything works.

  ```bash
  bazel build //...

  ```

If the command completes successfully, you have added the dependency in a clean, isolated, and reproducible way.



## 🔐 Secrets Management

  * **Local development:** Use `.env` files at the root of each module.
  * **Production:** Use **Google Secret Manager**.

### Examples: creating secrets in GCP
```bash
# Create a secret from a file (e.g. service account)
gcloud secrets create biwenger-tools-sa-regional \
  --data-file="biwenger-tools-sa.json" \
  --replication-policy="user-managed" \
  --locations="$REGION"

# Create secrets from the command line
echo -n "YOUR_EMAIL@gmail.com" | gcloud secrets create biwenger-email-regional \
  --data-file=- \
  --replication-policy="user-managed" \
  --locations="$REGION"

echo -n "YOUR_PASSWORD" | gcloud secrets create biwenger-password-regional \
  --data-file=- \
  --replication-policy="user-managed" \
  --locations="$REGION"

echo -n "DRIVE_FOLDER_ID" | gcloud secrets create gdrive-folder-id-regional \
  --data-file=- \
  --replication-policy="user-managed" \
  --locations="$REGION"
```

### Updating a secret (e.g. token.json):
```bash
gcloud secrets versions add token_json --data-file="token.json"
```

---
## 💅 Linter and Auto-formatter (VS Code)

Configure **Flake8** (linter) and **Black** (formatter) for clean, consistent code.

1.  **Install the extensions:**

      * `ms-python.python`
      * `ms-python.black-formatter`

2.  **Select the Python Interpreter:**

      * Open the command palette (`Ctrl+Shift+P` or `Cmd+Shift+P`).
      * Search for and select `Python: Select Interpreter`.
      * Choose the interpreter from your virtual environment (`./venv/bin/python`).

3.  **Configure `settings.json`:**

      * Open the command palette and search for `Preferences: Open Workspace Settings (JSON)`.
      * Add the following configuration:

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

4.  **(Optional) Configure Flake8:**

      * Create a `.flake8` file at the project root to align its rules with Black.

    <!-- end list -->

    ```ini
    [flake8]
    max-line-length = 88
    ignore = E203, W503
    exclude = .git,__pycache__,.venv,venv,*.md
    ```

Once configured, VS Code will flag errors and auto-format your code on save.


## 🧹 GCP Cleanup and Cost Control

### Artifact Registry

  * **Create the Docker repository (first time only):**

    ```bash
    gcloud artifacts repositories create biwenger-docker \
        --repository-format=docker \
        --location=europe-southwest1 \
        --description="Docker images for Biwenger Tools"
    ```

  * **List images in the repository:**

    ```bash
    gcloud artifacts docker images list europe-southwest1-docker.pkg.dev/biwenger-tools/biwenger-docker
    ```

  * **Clean up old images (script):**

    ```bash
    cd scripts/
    ./clean-images-artifact.sh
    ```

    > This script deletes all old images, keeping only the one tagged `latest`.

  * **Review costs (script):**

    ```bash
    cd scripts/
    ./check-gcp-costs.sh
    ```

    > This script compares **Artifact Registry** and **Cloud Run** usage against the GCP *Free Tier*.

    * **Clean local Docker containers:**
    ```
     docker image prune -f
     ```

-----

## 🗓️ Cambio de temporada

El cambio de temporada es **manual e intencional** — ocurre cuando se resetea la liga en Biwenger (una vez al año).

### Pasos

1. **`deploy.yml`** — actualizar `TEMPORADA_ACTUAL` en el bloque `env:` global:
   ```yaml
   TEMPORADA_ACTUAL: "26-27"
   ```

2. **`packages/biwenger_tools/web/config.py`** — añadir la nueva temporada a `TEMPORADAS_DISPONIBLES`:
   ```python
   TEMPORADAS_DISPONIBLES = ["24-25", "25-26", "26-27"]
   ```

3. **`.env` locales** — actualizar `TEMPORADA_ACTUAL` en `web/.env` y `scraper_job/.env`.

4. **Commit + push a `master`** → el CI despliega ambos servicios automáticamente con la nueva temporada.

> Si necesitas cambiar la temporada en producción **sin redeploy**:
> ```bash
> gcloud run services update biwenger-summary --update-env-vars TEMPORADA_ACTUAL=26-27 --region europe-southwest1
> gcloud run jobs update biwenger-scraper-data --update-env-vars TEMPORADA_ACTUAL=26-27 --region europe-southwest1
> ```

---

## ⚠️ Important Notes

  * **Do not commit** the credentials file `biwenger-tools-sa.json`.
  * If a deployment fails, check the **logs in the GCP console** (Cloud Run, Cloud Build, etc.).
  * Make sure you have a `.env` file configured in each module for local development.
