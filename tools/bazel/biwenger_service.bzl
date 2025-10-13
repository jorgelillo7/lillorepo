load("@rules_python//python:defs.bzl", "py_library", "py_binary", "py_test")
load("@rules_pkg//pkg:tar.bzl", "pkg_tar")
load("@rules_oci//oci:defs.bzl", "oci_image", "oci_push", "oci_tarball")
load("@pypi//:requirements.bzl", "requirement")

def biwenger_service(
        name,
        main,
        repository,
        deps = [],
        secrets = [],
        srcs = None,
        extra_env = {},
        enable_tests = True):
    """
    Macro simplificada para servicios Python con OCI images.
    """

    if srcs == None:
        srcs = native.glob(["**/*.py"], exclude = ["tests/**/*.py"])

    pkg_dir = "/app/packages/biwenger_tools/" + name
    templates = native.glob(["templates/**/*.html"])
    static_files = native.glob(["static/**/*"])

    # ============================================================
    # 1️⃣ LIBRERÍA PRINCIPAL
    # ============================================================
    py_library(
        name = name + "_lib",
        srcs = srcs,
        data = templates + static_files + secrets,
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


    # Código de la aplicación
    pkg_tar(
        name = name + "_code_layer",
        # 👇 1. Añade el entrypoint.sh a los sources
        srcs = srcs + ["entrypoint.sh"],
        files = dict(template_map, **static_map),
        package_dir = pkg_dir,
        # 👇 2. Dale permisos de ejecución
        mode = "0755",
    )

    # Código + secretos (solo local)
    pkg_tar(
        name = name + "_code_with_secrets_layer",
        srcs = srcs + secrets + ["entrypoint.sh"],
        # 👇 Y CAMBIO AQUÍ TAMBIÉN
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
        entrypoint = ["/app/packages/biwenger_tools/" + name + "/entrypoint.sh"],  # ✅ usa tu script
        workdir = "/app",
    )

    oci_tarball(
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
        entrypoint = ["/app/packages/biwenger_tools/" + name + "/entrypoint.sh"],
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
                data = secrets,
                deps = [
                    ":" + name + "_lib",
                    requirement("pytest"),
                ],
            )