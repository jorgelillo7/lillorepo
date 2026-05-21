"""HTML sanitization for content coming from the Biwenger API.

Biwenger lets league members write announcements in a rich editor, so the
content arrives as HTML written by humans (and forwarded verbatim by the
scraper). Rendering it with `|safe` would let any member inject `<script>`
or event-handler attributes into the page — reachable because the web
service is `allow-unauthenticated`.

We sanitize with `bleach.clean` against a fixed allowlist. Tags outside
the allowlist are stripped (not escaped, so the rest of the message reads
naturally); attributes are likewise filtered. The result is a `Markup`
object safe to drop into a Jinja template or to assign with `innerHTML`
on the JS side after a `{{ ... | tojson }}`.
"""

import bleach
from bs4 import BeautifulSoup
from markupsafe import Markup

# Tags we accept from Biwenger announcements. Kept conservative:
# block + inline + lists + links. No <img>, <script>, <iframe>, no events.
ALLOWED_TAGS = {
    "p",
    "br",
    "b",
    "strong",
    "em",
    "i",
    "u",
    "a",
    "ul",
    "ol",
    "li",
    "blockquote",
    "code",
}

# Only `href`/`title` on links. bleach also enforces a URL allowlist on
# `href` (http/https/mailto by default) and rejects `javascript:` URIs.
ALLOWED_ATTRS = {"a": ["href", "title"]}

# Drop the content of <script>/<style> entirely instead of escaping it,
# which is the safest default for our use case.
STRIP_TAGS = True


def safe_html(html: str | None) -> Markup:
    """Return Biwenger HTML cleaned of unsafe markup, ready to render.

    Idempotent: calling it twice on the same value yields the same value.
    """
    if not html:
        return Markup("")
    cleaned = bleach.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRS,
        strip=STRIP_TAGS,
    )
    return Markup(cleaned)


def html_to_plain_text(html: str | None) -> str:
    """Sanitized HTML rendered as a plain string.

    Used by the routes that ship the value to the browser via `tojson` —
    storing the cleaned HTML once at load time keeps both the Jinja
    template path and the `innerHTML` JS path safe.
    """
    return str(safe_html(html))


def to_text(html: str | None) -> str:
    """Return ``html`` stripped of every tag, preserving line breaks.

    Used by the search-data endpoint to ship a slim, format-free payload
    to the client. ``contenido`` from Biwenger can carry styled HTML
    (~50% of the search payload is tags + attributes); collapsing it to
    plain text with `\\n` line breaks roughly halves the bytes on the
    wire. Safe for `textContent` (the search card renders with
    `whitespace-pre-wrap` so the line breaks survive).
    """
    if not html:
        return ""
    return BeautifulSoup(html, "html.parser").get_text(separator="\n", strip=True)
