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
load("@rules_pkg//pkg:mappings.bzl", "pkg_attributes", "pkg_files", "strip_prefix")
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

def service(
        *,
        main,
        srcs = None,
        deps = [],
        core_deps = ["//core"],
        package_srcs = [],
        secrets = [],
        test_deps = [],
        enable_tests = True):
    """What the service is made of.

    Args:
        main:         Entry point (e.g. `"app.py"`).
        srcs:         Python sources; defaults to every `.py` outside `tests/`.
        deps:         Bazel deps beyond the base set every service gets.
        core_deps:    Which slices of `//core` to link. Defaults to the whole
                      umbrella so nothing moves unless a package asks; name the
                      granular targets (`//core:telegram`) to link only those.
                      This does NOT shrink the image while `Dockerfile.base`
                      pip-installs every dependency — it scopes the build graph.
        package_srcs: Files one level up, shared by the package's modules. They
                      ship at `/app/packages/<package>/`, which is where the
                      module's own imports of them resolve. Without this a
                      Bazel-only dep passes the tests and the container fails
                      at import, because the code layer copies the module
                      directory alone.
        secrets:      Files baked into the **local** image only, never into GCP's.
        test_deps:    Extra deps for the test target, beyond the library and pytest.
        enable_tests: Generate `<name>_tests` when a `tests/` directory exists.
    """
    return struct(
        _kind = "service",
        main = _ensure_str("service.main", main, required = True),
        srcs = srcs if srcs == None else _ensure_str_list("service.srcs", srcs),
        deps = _ensure_str_list("service.deps", deps),
        core_deps = _ensure_str_list("service.core_deps", core_deps),
        package_srcs = _ensure_str_list("service.package_srcs", package_srcs),
        secrets = _ensure_str_list("service.secrets", secrets),
        test_deps = _ensure_str_list("service.test_deps", test_deps),
        enable_tests = _ensure_bool("service.enable_tests", enable_tests),
    )

def job(
        *,
        main,
        srcs = None,
        deps = [],
        core_deps = ["//core"],
        package_srcs = [],
        secrets = [],
        test_deps = [],
        enable_tests = True):
    """What a Cloud Run **Job** is made of. Same fields as `service`.

    The difference is not cosmetic: a job runs to completion and never listens,
    so its image gets no `PORT`. Declaring one on a workload that cannot serve
    invites the reader to look for an HTTP handler that does not exist.
    """
    return struct(
        _kind = "job",
        main = _ensure_str("job.main", main, required = True),
        srcs = srcs if srcs == None else _ensure_str_list("job.srcs", srcs),
        deps = _ensure_str_list("job.deps", deps),
        core_deps = _ensure_str_list("job.core_deps", core_deps),
        package_srcs = _ensure_str_list("job.package_srcs", package_srcs),
        secrets = _ensure_str_list("job.secrets", secrets),
        test_deps = _ensure_str_list("job.test_deps", test_deps),
        enable_tests = _ensure_bool("job.enable_tests", enable_tests),
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
    """An HTTP service: library, local binary, OCI images, push target, tests.

    Args:
        name:       Service name, and the module directory (e.g. `"web"`).
        package:    Directory under `/packages/` (e.g. `"biwenger_tools"`).
        repository: Destination OCI repository in Artifact Registry.
        service:    A `service(…)` struct.
        image:      An `image(…)` struct; defaults to no extra environment.
    """
    _python_workload(
        name = name,
        package = package,
        repository = repository,
        spec = _ensure_kind("service", service, "service"),
        image = image,
        serves_http = True,
    )

def python_job(*, name, package, repository, job, image = None):
    """A Cloud Run Job. Same targets as `python_service`, minus `PORT`.

    Args:
        name:       Job name, and the module directory (e.g. `"scraper_job"`).
        package:    Directory under `/packages/` (e.g. `"biwenger_tools"`).
        repository: Destination OCI repository in Artifact Registry.
        job:        A `job(…)` struct.
        image:      An `image(…)` struct; defaults to no extra environment.
    """
    _python_workload(
        name = name,
        package = package,
        repository = repository,
        spec = _ensure_kind("job", job, "job"),
        image = image,
        serves_http = False,
    )

def _python_workload(*, name, package, repository, spec, image, serves_http):
    """Everything both workload kinds share. `serves_http` decides `PORT`."""
    name = _ensure_str("name", name, required = True)
    package = _ensure_str("package", package, required = True)
    repository = _ensure_str("repository", repository, required = True)
    svc = spec

    # `image` the parameter shadows `image` the constructor inside this
    # function, so the default is built literally rather than by calling it.
    img = image if image != None else struct(_kind = "image", env = {})
    img = _ensure_kind("image", img, "image")

    # Built key by key rather than as a literal so `PORT` can be omitted for a
    # job while the insertion order stays exactly what it was for a service —
    # the OCI config records env as an ordered list, and reordering it would
    # rewrite every service image for no reason.
    local_env = {}
    gcp_env = {}
    if serves_http:
        local_env["PORT"] = "8080"
        gcp_env["PORT"] = "8080"
    gcp_env["PYTHONPATH"] = "/app"
    local_env["PYTHONUNBUFFERED"] = "1"
    gcp_env["PYTHONUNBUFFERED"] = "1"

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
        ] + svc.core_deps,
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

    # Ficheros compartidos a nivel de paquete (un nivel por encima del módulo).
    # Van a /app/packages/<package>/, que es donde los resuelven los imports
    # del módulo: la capa de código de arriba sólo copia el módulo, así que sin
    # esta capa un fichero compartido pasa los tests y rompe el contenedor.
    # A dep on a package-level label without the matching `package_srcs` is
    # the one direction that fails silently: the sandbox resolves it and the
    # image does not, so tests pass and the container dies at import. The
    # reverse (shipped but not linked) fails loudly in the tests. Catch the
    # quiet one at analysis time.
    package_label = "//packages/" + package + ":"
    if not svc.package_srcs:
        for dep in svc.deps:
            if dep.startswith(package_label):
                fail(
                    ("`{}` depends on {} but declares no `package_srcs`. " +
                     "The code layer copies this module's directory alone, so " +
                     "that file would be missing from the image and the " +
                     "container would fail at import while every test passes. " +
                     "Add the file to `package_srcs` as well as `deps`.")
                        .format(name, dep),
                )

    package_layers = []
    if svc.package_srcs:
        pkg_files(
            name = name + "_package_files",
            srcs = svc.package_srcs,
            strip_prefix = strip_prefix.from_root("packages/" + package),
            # On `pkg_files`, not on the enclosing `pkg_tar`: these attributes
            # win over the tar's `mode`, so setting it there silently ships
            # everything 0644 and a shared shell helper dies on Permission
            # denied.
            attributes = pkg_attributes(mode = "0755"),
        )
        pkg_tar(
            name = name + "_package_layer",
            srcs = [":" + name + "_package_files"],
            package_dir = "/app/packages/" + package,
        )
        package_layers = [":" + name + "_package_layer"]

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
        ] + package_layers + [
            ":" + name + "_code_with_secrets_layer",
        ],
        env = dict(local_env, **img.env),
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
        ] + package_layers + [
            ":" + name + "_code_layer",
        ],
        env = dict(gcp_env, **img.env),
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
                ] + svc.test_deps,
            )
