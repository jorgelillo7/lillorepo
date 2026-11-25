"""`tailwind_css`: compile a package's Tailwind CSS with the pinned standalone CLI."""

def tailwind_css(*, name, out, config = "tailwind.config.js", input = "tailwind.input.css", srcs = []):
    """Writes minified CSS to `out` from `input`, scanning `srcs` as the config's content.

    The config must use `content: { relative: true, files: [...] }`, so its
    globs resolve against the config file inside the sandbox.
    """
    native.genrule(
        name = name,
        srcs = [config, input, "//tools/bazel:tailwind_dark_palette.js"] + srcs,
        outs = [out],
        tools = ["//tools/bazel:tailwindcss"],
        cmd = "BROWSERSLIST_IGNORE_OLD_DATA=1 $(execpath //tools/bazel:tailwindcss) --config $(execpath {config}) --input $(execpath {input}) --output $@ --minify".format(
            config = config,
            input = input,
        ),
    )
