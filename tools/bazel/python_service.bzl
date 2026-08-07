"""Bazel macro for the repo's Python services: library, binary, OCI image, push.

The public API is three symbols. `python_service` orchestrates; `service` and
`image` build the validated structs it takes:

    python_service(
        name = "api",
        package = "biwenger_tools",
        repository = "europe-southwest1-docker.pkg.dev/…/api",
        service = service(
            main = "app.py",
            deps = ["@pypi//matplotlib"],
            secrets = [".env"],
        ),
        image = image(env = {"PORT": "8080"}),
    )

Arguments are keyword-only and type-checked at load time, so a string where a
list belongs fails with the parameter name instead of surfacing as an analysis
error in a generated target several hundred lines away.
"""

load("@rules_python//python:defs.bzl", "py_library", "py_binary", "py_test")
load("@rules_pkg//pkg:tar.bzl", "pkg_tar")
load("@rules_pkg//pkg:mappings.bzl", "pkg_files", "strip_prefix")
load("@rules_oci//oci:defs.bzl", "oci_image", "oci_load", "oci_push")
load("@pypi//:requirements.bzl", "requirement")

# ---------------------------------------------------------------------------
# Type checks — every failure names the parameter, so the message is actionable
# from the BUILD file that caused it.
# ---------------------------------------------------------------------------

def _ensure_str(param, value, required = False):
    if value == None:
        if required:
            fail("`{}` is required".format(param))
        return None
    if type(value) != "string":
        fail("`{}` must be a string, got {}".format(param, type(value)))
    return value

def _ensure_str_list(param, value):
    if type(value) != "list":
        fail("`{}` must be a list, got {}".format(param, type(value)))
    for item in value:
        if type(item) != "string":
            fail("`{}` must contain only strings, got a {}".format(param, type(item)))
    return value

def _ensure_str_dict(param, value):
    if type(value) != "dict":
        fail("`{}` must be a dict, got {}".format(param, type(value)))
    for key, item in value.items():
        if type(key) != "string" or type(item) != "string":
            fail("`{}` must map strings to strings".format(param))
    return value

def _ensure_bool(param, value):
    if type(value) != "bool":
        fail("`{}` must be True or False, got {}".format(param, type(value)))
    return value

def _ensure_kind(param, value, kind):
    if value == None:
        fail("`{}` is required — build it with `{}(…)`".format(param, kind))
    if not hasattr(value, "_kind") or value._kind != kind:
        fail("`{}` must be a `{}(…)` struct".format(param, kind))
    return value

# ---------------------------------------------------------------------------
# Constructors
# ---------------------------------------------------------------------------

def service(*, main, srcs = None, deps = [], secrets = [], enable_tests = True):
    """What the service is made of.

    Args:
        main:         Entry point (e.g. `"app.py"`).
        srcs:         Python sources; defaults to every `.py` outside `tests/`.
        deps:         Bazel deps beyond the base set every service gets.
        secrets:      Files baked into the **local** image only, never into GCP's.
        enable_tests: Generate `<name>_tests` when a `tests/` directory exists.
    """
    return struct(
        _kind = "service",
        main = _ensure_str("service.main", main, required = True),
        srcs = srcs if srcs == None else _ensure_str_list("service.srcs", srcs),
        deps = _ensure_str_list("service.deps", deps),
        secrets = _ensure_str_list("service.secrets", secrets),
        enable_tests = _ensure_bool("service.enable_tests", enable_tests),
    )

def image(*, env = {}):
    """Image-level settings.

    Args:
        env: Extra environment variables, merged over the defaults.
    """
    return struct(_kind = "image", env = _ensure_str_dict("image.env", env))

# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def python_service(*, name, package, repository, service, image = None):
    """Library, local binary, OCI images (local + GCP), push target and tests.

    Args:
        name:       Service name, and the module directory (e.g. `"web"`).
        package:    Directory under `/packages/` (e.g. `"biwenger_tools"`).
        repository: Destination OCI repository in Artifact Registry.
        service:    A `service(…)` struct.
        image:      An `image(…)` struct; defaults to no extra environment.
    """
    name = _ensure_str("name", name, required = True)
    package = _ensure_str("package", package, required = True)
    repository = _ensure_str("repository", repository, required = True)
    svc = _ensure_kind("service", service, "service")

    # `image` the parameter shadows `image` the constructor inside this
    # function, so the default is built literally rather than by calling it.
    img = image if image != None else struct(_kind = "image", env = {})
    img = _ensure_kind("image", img, "image")

    srcs = svc.srcs
    if srcs == None:
        srcs = native.glob(["**/*.py"], exclude = ["tests/**/*.py"])

    pkg_dir = "/app/packages/" + package + "/" + name
    templates = native.glob(["templates/**/*.html"], allow_empty = True)
    static_files = native.glob(["static/**/*"], allow_empty = True)

    # ============================================================
    # 1️⃣ LIBRERÍA PRINCIPAL
    # ============================================================
    py_library(
        name = name + "_lib",
        # The draft skill's scripts import the api's pure engine so the rule
        # for a legal squad has one definition instead of two.
        visibility = ["//visibility:public"],
        srcs = srcs,
        data = templates + static_files,
        deps = svc.deps + [
            requirement("flask"),
            requirement("gunicorn"),
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
        main = svc.main,
        srcs = [svc.main],
        data = templates + static_files + svc.secrets,
        deps = [":" + name + "_lib"],
    )

    template_map = {f: f for f in native.glob(["templates/**/*"], allow_empty = True)}
    static_map = {f: f for f in native.glob(["static/**/*"], allow_empty = True)}

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
        srcs = [":" + name + "_code_files"] + svc.secrets + ["entrypoint.sh"],
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
            **img.env
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
            **img.env
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
    if svc.enable_tests:
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
