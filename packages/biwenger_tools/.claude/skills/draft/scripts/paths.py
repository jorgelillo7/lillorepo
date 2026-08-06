"""Where a season's files live. One resolver, so two runs cannot disagree.

Every script writes into `<skill>/<season>/` under a fixed name. The season is
the folder, never the filename: that is what makes `diff -r 25-26 26-27`
compare like with like, and what makes a clean re-run produce the same tree it
produced last year.

Set `DRAFT_OUT_ROOT` to send the whole run somewhere else. That is the rehearsal
switch — it exercises the real default names instead of a hand-typed path, which
is the only way the check means anything:

    DRAFT_OUT_ROOT=/tmp/ensayo  # …run the phases…
    diff -r packages/.../skills/draft/26-27 /tmp/ensayo/26-27
"""

import os

RANKED = "draft-ranked.csv"
REAL_POINTS = "draft-real-points.csv"
ARCHETYPES = "arquetipos.md"
DECISION = "decision.md"
AVAILABILITY = "disponibilidad.md"
AVAILABILITY_CSV = "disponibilidad.csv"
EXCLUSIONS = "exclusiones.txt"
CACHE = ".cache"

_SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def season_dir(season: str) -> str:
    """The folder holding everything that season produced. Created on demand."""
    root = os.getenv("DRAFT_OUT_ROOT") or _SKILL
    path = os.path.join(root, season)
    os.makedirs(path, exist_ok=True)
    return path


def season_path(season: str, name: str) -> str:
    """`<season folder>/<name>`, for the constants above."""
    return os.path.join(season_dir(season), name)
