"""Constants describing the Lloros league itself.

At the package level rather than in `api/` or `web/`, because both read
them: the api arbitrates the draft, the web publishes the order on the
rulebook page. They were duplicated once and the copies drifted.

Generic values shared with other packages (`MADRID_TZ`) stay in
`core.constants`; nothing here would mean anything to another package.
"""

# Biwenger league ID. Single value for now — if we ever need to operate
# multiple leagues, this becomes per-config.
LEAGUE_ID = "340703"

# Stable user_id → real-name mapping. Biwenger lets users rename their team
# at will, so the team `name` field drifts; the numeric `id` is stable, so
# this is the source of truth when attributing a row to a real person
# (palmares, post-rollover reports). Per-season team names live in
# `palmares/{season}/standings_table` — don't duplicate them as comments
# here, they drift on every rollover.
LEAGUE_MEMBERS: dict[int, str] = {
    7728610: "Fabio",
    1376351: "Lucena",
    12449616: "Pablo",
    1372802: "Jorge",
    7728598: "Javi",
    7727371: "Ruben",
    13753285: "Manu",
    13945871: "Alberto",
}

# League accounts that do not compete (e.g. the cronista, who only posts
# board messages): excluded from squad iteration, manager pickers, clausulazo
# candidates and the end-of-season palmares. Their board messages still flow
# into comunicados/participacion via the scraper.
NON_PLAYING_MEMBER_IDS: frozenset[int] = frozenset({13945871})

# Draft pick order for the current season, by `LEAGUE_MEMBERS` name. Inverse
# to the previous season's final standings, with the reglamento's adjustments
# for newcomers, so it changes on every rollover.
DRAFT_ORDER_NAMES: tuple[str, ...] = (
    "Ruben",
    "Javi",
    "Jorge",
    "Manu",
    "Pablo",
    "Lucena",
    "Fabio",
)

# H2H league fixture base (reglamento art. 3.1, Anexo II). Seven rounds — one
# per resting president — repeated five times to cover the 35 matchdays the
# competition is played over. The organisation fixes it before the season, so
# it is code rather than data: the rulebook annex must render without a
# network fetch, and the web's H2H page uses the same list as the skeleton it
# overlays scores onto.
#
# Names are the ones the reglamento and the organiser's spreadsheet print,
# which are not the `LEAGUE_MEMBERS` spellings (`Lillo`/`Lucen`/`Rubén` vs
# `Jorge`/`Lucena`/`Ruben`).
H2H_ROUNDS: tuple[dict, ...] = (
    {
        "p1": ("Fabio", "Rubén"),
        "p2": ("Lillo", "Pablo"),
        "p3": ("Javi", "Lucen"),
        "descansa": "Manu",
    },
    {
        "p1": ("Manu", "Rubén"),
        "p2": ("Fabio", "Pablo"),
        "p3": ("Lillo", "Javi"),
        "descansa": "Lucen",
    },
    {
        "p1": ("Lucen", "Rubén"),
        "p2": ("Manu", "Javi"),
        "p3": ("Fabio", "Lillo"),
        "descansa": "Pablo",
    },
    {
        "p1": ("Pablo", "Rubén"),
        "p2": ("Lucen", "Lillo"),
        "p3": ("Manu", "Fabio"),
        "descansa": "Javi",
    },
    {
        "p1": ("Javi", "Rubén"),
        "p2": ("Pablo", "Fabio"),
        "p3": ("Lucen", "Manu"),
        "descansa": "Lillo",
    },
    {
        "p1": ("Lillo", "Rubén"),
        "p2": ("Javi", "Manu"),
        "p3": ("Pablo", "Lucen"),
        "descansa": "Fabio",
    },
    {
        "p1": ("Fabio", "Lucen"),
        "p2": ("Lillo", "Manu"),
        "p3": ("Javi", "Pablo"),
        "descansa": "Rubén",
    },
)


# The reglamento and Biwenger spell three managers differently, and both are
# right where they live: `H2H_ROUNDS` quotes the articles, `LEAGUE_MEMBERS`
# mirrors the game. Nothing crossed between them until the palmarés had to name
# a champion, so the drift was harmless — and then was not.
#
# A table rather than normalisation: `Rubén`/`Ruben` is an accent, but
# `Lillo`/`Jorge` are two different names, and a rule that solves one while
# silently failing the other is worse than no rule.
H2H_NAME_ALIASES: dict[str, str] = {
    "Lillo": "Jorge",
    "Lucen": "Lucena",
    "Rubén": "Ruben",
}

_MEMBER_IDS_BY_NAME = {name: member_id for member_id, name in LEAGUE_MEMBERS.items()}


def resolve_h2h_name(name: str) -> str | None:
    """A reglamento spelling as its `LEAGUE_MEMBERS` name, or None.

    None rather than the input: a caller that cannot find the manager must say
    so. Returning the unknown name unchanged would put a stranger in the
    standings and look like it worked.
    """
    resolved = H2H_NAME_ALIASES.get(name, name)
    return resolved if resolved in _MEMBER_IDS_BY_NAME else None


def h2h_member_id(name: str) -> int | None:
    """A reglamento spelling as a Biwenger manager id, or None."""
    resolved = resolve_h2h_name(name)
    return _MEMBER_IDS_BY_NAME.get(resolved) if resolved else None


# The competition runs over the first 35 official LaLiga matchdays (art. 3.1).
H2H_MATCHDAYS = 35
