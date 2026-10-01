"""Expose a binary shipped inside a pip wheel as a `bazel run` target.

Some tools (Ruff) ship a compiled binary in the wheel's `.data/scripts/` and
declare no console-script entry point, so `py_console_script_binary` cannot
wrap them. rules_python installs that binary at `bin/<name>` in the wheel's
`:data` filegroup; this rule picks it out and marks it executable, keeping the
version the lock pins.
"""

def _whl_bin_impl(ctx):
    matches = [f for f in ctx.files.data if f.path.endswith("/bin/" + ctx.attr.binary)]
    if len(matches) != 1:
        fail("expected exactly one bin/%s in %s, found %d" % (
            ctx.attr.binary,
            ctx.attr.data,
            len(matches),
        ))
    out = ctx.actions.declare_file(ctx.label.name)
    ctx.actions.symlink(output = out, target_file = matches[0], is_executable = True)
    return [DefaultInfo(executable = out, runfiles = ctx.runfiles(files = [matches[0]]))]

whl_bin = rule(
    implementation = _whl_bin_impl,
    attrs = {
        "data": attr.label(mandatory = True, allow_files = True),
        "binary": attr.string(mandatory = True),
    },
    executable = True,
)
