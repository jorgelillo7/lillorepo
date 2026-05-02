load("@rules_python//python:defs.bzl", "py_library", "py_binary", "py_test")
load("@rules_pkg//pkg:tar.bzl", "pkg_tar")
load("@rules_pkg//pkg:mappings.bzl", "pkg_files", "strip_prefix")
load("@rules_oci//oci:defs.bzl", "oci_image", "oci_load", "oci_push")
load("@pypi//:requirements.bzl", "requirement")

def python_service(
        name,
        main,
        repository,
        package,
        deps = [],
        secrets = [],
        srcs = None,
        extra_env = {},
        enable_tests = True):
    """
    Macro genérica para servicios Python con OCI images.

    Args:
        name:         Nombre del servicio (e.g. "web").
        main:         Fichero de entrada (e.g. "app.py").
        repository:   Repositorio OCI de destino para GCP.
        package:      Nombre del paquete dentro de /packages/
                      (e.g. "biwenger_tools", "otro_proyecto").
        deps:         Dependencias adicionales al conjunto base.
        secrets:      Ficheros de secretos (incluidos solo en la imagen local).
        srcs:         Fuentes Python; por defecto todos los .py del módulo.
        extra_env:    Variables de entorno adicionales para la imagen OCI.
        enable_tests: Si True, genera el target *_tests cuando hay tests.
    """

    if srcs == None:
        srcs = native.glob(["**/*.py"], exclude = ["tests/**/*.py"])

    pkg_dir = "/app/packages/" + package + "/" + name
    templates = native.glob(["templates/**/*.html"])
    static_files = native.glob(["static/**/*"])

    # ============================================================
    # 1️⃣ LIBRERÍA PRINCIPAL
    # ============================================================
    py_library(
        name = name + "_lib",
        srcs = srcs,
        data = templates + static_files,
        deps = deps + [
            requirement("flask"),
            requirement("gunicorn"),
            requirement("pytz"),
            requirement("python-dateutil"),
            requirement("python-dotenv"),
            requirement("beautifulsoup4"),
            requirement("unidecode"),
            "//core",
        ],
    )

    # ============================================================
    # 2️⃣ BINARIO LOCAL
    # ============================================================
    py_binary(
        name = name + "_local",
        main = main,
        srcs = [main],
        data = templates + static_files + secrets,
        deps = [":" + name + "_lib"],
    )

    template_map = {f: f for f in native.glob(["templates/**/*"])}
    static_map = {f: f for f in native.glob(["static/**/*"])}

    # ============================================================
    # 3️⃣ CAPAS DE CÓDIGO
    # ============================================================

    # Core: copiar tar que ya tiene estructura preservada
    pkg_tar(
        name = name + "_core_layer",
        files = {
            "//core:core_srcs": "core_srcs.tar",
        },
        package_dir = "/app",
    )

    # Ficheros de código con estructura de directorios preservada
    pkg_files(
        name = name + "_code_files",
        srcs = srcs,
        strip_prefix = strip_prefix.from_pkg(),
    )

    # Código de la aplicación (sin secretos, para GCP)
    pkg_tar(
        name = name + "_code_layer",
        srcs = [":" + name + "_code_files", "entrypoint.sh"],
        files = dict(template_map, **static_map),
        package_dir = pkg_dir,
        mode = "0755",
    )

    # Código + secretos (para imagen local)
    pkg_tar(
        name = name + "_code_with_secrets_layer",
        srcs = [":" + name + "_code_files"] + secrets + ["entrypoint.sh"],
        files = dict(template_map, **static_map),
        package_dir = pkg_dir,
        mode = "0755",
    )

    # ============================================================
    # 4️⃣ IMAGEN LOCAL
    # ============================================================
    oci_image(
        name = name + "_image_local",
        base = "@python_with_deps",
        tars = [
            ":" + name + "_core_layer",
            ":" + name + "_code_with_secrets_layer",
        ],
        env = dict(
            {
                "PORT": "8080",
                "PYTHONUNBUFFERED": "1",
            },
            **extra_env,
        ),
        entrypoint = [pkg_dir + "/entrypoint.sh"],
        workdir = "/app",
    )

    oci_load(
        name = "load_image_to_docker_local",
        image = ":" + name + "_image_local",
        repo_tags = ["bazel/" + name + ":local"],
    )

    # ============================================================
    # 5️⃣ IMAGEN GCP
    # ============================================================
    oci_image(
        name = name + "_image_gcp",
        base = "@python_with_deps",
        tars = [
            ":" + name + "_core_layer",
            ":" + name + "_code_layer",
        ],
        env = dict(
            {
                "PORT": "8080",
                "PYTHONPATH": "/app",
                "PYTHONUNBUFFERED": "1",
            },
            **extra_env,
        ),
        entrypoint = [pkg_dir + "/entrypoint.sh"],
        workdir = "/app",
    )

    oci_push(
        name = "push_image_to_gcp",
        image = ":" + name + "_image_gcp",
        repository = repository,
        remote_tags = ["latest"],
    )

    # ============================================================
    # 6️⃣ TESTS
    # ============================================================
    if enable_tests:
        test_files = native.glob(["tests/**/*.py"])
        if test_files:
            py_test(
                name = name + "_tests",
                timeout = "short",
                srcs = test_files,
                main = "tests/main.py",
                deps = [
                    ":" + name + "_lib",
                    requirement("pytest"),
                ],
            )


def biwenger_service(**kwargs):
    """
    Alias de compatibilidad hacia atrás para python_service.
    Establece package='biwenger_tools' si no se indica otro valor.
    Usa python_service directamente en proyectos nuevos.
    """
    kwargs.setdefault("package", "biwenger_tools")
    python_service(**kwargs)
