"""Google Sign-In verification (Google Identity Services).

The GIS button POSTs a signed JWT credential; google-auth verifies the
signature against Google's keys and the audience against our client id.
No new dependencies — google-auth already ships with the service.
"""

import google.auth.transport.requests
from google.oauth2 import id_token

from packages.be_water.web import config


class GoogleAuthError(Exception):
    """Credential missing, expired, or minted for another client id."""


def verify_google_credential(credential: str) -> dict:
    """Returns {"email", "name", "picture"} for a valid GIS credential."""
    if not credential or not config.GOOGLE_CLIENT_ID:
        raise GoogleAuthError("Sign-In is not configured.")
    try:
        claims = id_token.verify_oauth2_token(
            credential,
            google.auth.transport.requests.Request(),
            config.GOOGLE_CLIENT_ID,
        )
    except ValueError as exc:
        raise GoogleAuthError(str(exc)) from exc
    if not claims.get("email_verified"):
        raise GoogleAuthError("Email not verified by Google.")
    return {
        "email": claims["email"].lower(),
        "name": claims.get("name", ""),
        "picture": claims.get("picture", ""),
    }
