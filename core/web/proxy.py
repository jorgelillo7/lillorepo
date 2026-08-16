"""Trust the Cloud Run front end's forwarded headers.

Cloud Run terminates TLS and forwards the original scheme in
`X-Forwarded-Proto`. Flask does not read it by default, so every absolute URL
it builds comes out as `http://`: the sitemap advertised 82 URLs that each
answered a 302, and `url_for(..., _external=True)` would hand Google Sign-In
an http redirect URI it refuses.

Scheme and host only, one hop — Cloud Run is always the single proxy in front
of these services. `x_for` stays 0 because nothing here reads the client IP
from the WSGI environ; the rate limiters parse `X-Forwarded-For` themselves.
"""

from werkzeug.middleware.proxy_fix import ProxyFix


def trust_proxy(app):
    """Honour X-Forwarded-Proto/Host from exactly one upstream proxy."""
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=0, x_proto=1, x_host=1, x_prefix=0)
    return app
