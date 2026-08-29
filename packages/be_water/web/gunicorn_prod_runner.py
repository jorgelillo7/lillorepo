"""Gunicorn launcher for be-water on Cloud Run.

Relies on PYTHONPATH=/app set by entrypoint.sh, so the canonical module path
`packages.be_water.web.app:app` resolves without sys.path tricks.
"""

from core.serving.gunicorn import run

# The add flow calls Gemini twice in one request: the studio photo (90 s) and
# then the label OCR (45 s, one retry, 2 s backoff — 92 s). Up to 182 s
# against gunicorn's 30 s default, so the worker was SIGKILLed every time and
# the route's own `except` branches — the ones that keep the photo and offer
# the form to fill by hand — could never run. Cloud Run's request timeout is
# 300 s, which is the real ceiling.
run("packages.be_water.web.app:app", timeout=240)
