"""HTML sanitization for content coming from the Biwenger API.

Biwenger lets league members write announcements in a rich editor, so the
content arrives as HTML written by humans (and forwarded verbatim by the
scraper). Rendering it with `|safe` lets any member inject `<script>` or
event-handler attributes into the page — which is reachable because the
web service is `allow-unauthenticated`.

We sanitize by stripping the markup entirely with BeautifulSoup (already a
dep for the scraper, no new package) and re-rendering as plain text with
HTML line breaks. The trade-off is loss of formatting (bold, links, lists)
in exchange for a guaranteed-safe output. If we ever need rich formatting
back, swap this for `bleach.clean(html, tags=ALLOWED, attrs=ALLOWED_ATTRS)`.
"""

from bs4 import BeautifulSoup
from markupsafe import Markup, escape


def html_to_plain_text(html: str | None) -> str:
    """Extract the text content from arbitrary HTML.

    Block-level tags (<p>, <li>, ...) and <br> are turned into newlines so
    the visual structure of the message is preserved when re-rendered.
    """
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    return soup.get_text(separator="\n", strip=True)


def safe_html(html: str | None) -> Markup:
    """Jinja filter: render sanitized HTML.

    Returns a `Markup` (already escaped) with `\n` converted to `<br>` so
    paragraph breaks survive. Safe to drop into `{{ ... | safe_html }}`.
    """
    text = html_to_plain_text(html)
    lines = [escape(line) for line in text.split("\n")]
    return Markup("<br>".join(lines))
