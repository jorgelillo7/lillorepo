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
