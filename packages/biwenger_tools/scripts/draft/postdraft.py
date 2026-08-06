"""Post-draft report: the league's drafts compared, sent to the group.

Runs once, after the draft closes. Two rankings the group actually argues
about — what each squad is worth today against what it cost, and how much it
projects — then one message per manager and a top three.

    PYTHONPATH=. python3 packages/biwenger_tools/scripts/draft/postdraft.py \\
        --season 26-27 [--gif URL] [--write]

Read-only by default: it prints every message it would send. `--write` sends.

Lives here rather than in the draft skill because it posts to the group, and
the skill's scripts never move shared state — they only produce analysis for a
human to decide with.

Costs one public Biwenger request (the competition payload, for today's prices
and injury status). Never the per-player endpoint: this is a report, and the
whole league shares that budget.
"""

import argparse
import csv
import os
import statistics
import sys
import unicodedata
from collections import defaultdict

import requests

from core.sdk import firestore as fs
from core.sdk.jp import fetch_all_players, get_predict_rate
from core.sdk.telegram import send_telegram_animation, send_telegram_message
from packages.biwenger_tools.api import config
from packages.biwenger_tools.api.logic import league_compare
from packages.biwenger_tools.api.logic.player_matching import (
    build_jp_index,
    find_player_match,
)
from packages.biwenger_tools.api.player_formatting import SCORE_SF

COMPETITION_URL = "https://cf.biwenger.com/api/v2/competitions/la-liga/data?lang=es"
HEADERS = {"User-Agent": "Mozilla/5.0"}
DEFAULT_GIF = (
    "https://i.pinimg.com/originals/17/34/c6/1734c6d90261a0cf763e58c2bd5744f1.gif"
)

# One per manager, so a reader finds their own message at a glance.
ICONS = ["🦅", "🐍", "🦊", "🐺", "🦁", "🐢", "🦈"]


def _norm(text):
    text = unicodedata.normalize("NFKD", (text or "").strip().lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def _eur(amount):
    return f"{(amount or 0) / 1_000_000:.2f}M".replace(".", ",")


def _wait(seconds):
    if seconds is None:
        return "—"
    minutes = seconds / 60
    return f"{minutes:.0f} min" if minutes < 60 else f"{minutes / 60:.1f} h"


def load_picks(season):
    return [
        p
        for p in fs.query(f"draft/{season}/picks")
        if p.get("status") == "applied" and p.get("global_pick")
    ]


def load_market():
    """`{player id: biwenger player}` — today's price and injury status."""
    response = requests.get(COMPETITION_URL, headers=HEADERS, timeout=30)
    response.raise_for_status()
    data = (response.json().get("data")) or {}
    return {int(p["id"]): p for p in (data.get("players") or {}).values()}


def _frozen_projection(path):
    """`{normalised name: SF}` from the ranked CSV — the draft-day snapshot."""
    if not path or not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return {
            _norm(r["name"]): int(r["sofascore"] or 0)
            for r in csv.DictReader(fh)
            if r.get("sofascore")
        }


def load_projection(path, picks):
    """`(scores, source)` — today's Jornada Perfecta if it answers, else the
    draft-day CSV.

    Today is the interesting number: it already knows who got injured and who
    lost his place, which is exactly what the group wants to argue about. The
    frozen CSV is only a fallback, and the report says which one it used so
    nobody compares two different questions.
    """
    try:
        players = fetch_all_players(config.JP_AUTH_TOKEN)
        index = build_jp_index(
            list(players.values()) if isinstance(players, dict) else players
        )
        scores = {}
        for pick in picks:
            match = find_player_match(pick["player_name"], index)
            if match:
                scores[_norm(pick["player_name"])] = (
                    get_predict_rate(match, SCORE_SF) or 0
                )
        if scores:
            return scores, "hoy"
    except Exception as exc:  # noqa: BLE001 — a report must not die on JP
        print(
            f"JP no responde ({type(exc).__name__}); uso el CSV congelado.",
            file=sys.stderr,
        )
    return _frozen_projection(path), "el día del draft"


def summarise(picks, market, projection):
    """One record per manager: cost, value today, projection, injuries, waits."""
    by_manager = defaultdict(list)
    for pick in picks:
        by_manager[pick.get("manager_name") or "?"].append(pick)

    out = {}
    for manager, own in by_manager.items():
        prices = [(market.get(int(p["player_id"])) or {}) for p in own]
        waits = [
            p["waited_seconds"] for p in own if p.get("waited_seconds") is not None
        ]
        cost = sum(p.get("price") or 0 for p in own)
        value = sum(row.get("price") or 0 for row in prices)
        injured = [
            p["player_name"]
            for p, row in zip(own, prices)
            if row.get("status") == "injured"
        ]
        best = max(own, key=lambda p: projection.get(_norm(p["player_name"]), 0))
        out[manager] = {
            "picks": own,
            "cost": cost,
            "value": value,
            "gain": value - cost,
            "projection": sum(projection.get(_norm(p["player_name"]), 0) for p in own),
            "injured": injured,
            "median_wait": statistics.median(waits) if waits else None,
            "total_wait": sum(waits) if waits else 0,
            "star": best["player_name"],
            "priciest": max(own, key=lambda p: p.get("price") or 0),
        }
    return out


def _ranks(summary, key):
    """`{manager: position}`, 1 = best, ranking on `key` descending."""
    order = sorted(summary, key=lambda m: -summary[m][key])
    return {manager: i + 1 for i, manager in enumerate(order)}


def best_drafts(summary):
    """Managers ordered by the sum of both ranks.

    Deliberately not a weighted score: any weighting between "the market likes
    your squad" and "your squad projects points" would be invented. Adding the
    two positions treats them as equally valid readings and can be explained in
    one line, which is what a group chat argument needs.
    """
    by_gain = _ranks(summary, "gain")
    by_projection = _ranks(summary, "projection")
    return (
        sorted(
            summary,
            key=lambda m: (by_gain[m] + by_projection[m], by_projection[m]),
        ),
        by_gain,
        by_projection,
    )


def jab(manager, summary, slowest, fastest):
    """A line of teasing, always derived from the data — never invented."""
    record = summary[manager]
    if manager == slowest:
        return (
            f"⏳ El que nos hizo esperar: {_wait(record['median_wait'])} de mediana "
            f"por pick, {_wait(record['total_wait'])} en total."
        )
    if manager == fastest:
        return (
            f"⚡ Picaba antes de que terminaras de leer el turno: "
            f"{_wait(record['median_wait'])} de mediana."
        )
    if record["injured"]:
        names = ", ".join(record["injured"])
        return f"🏥 Fichó a {names} y se lesionó antes de empezar la liga."
    if record["gain"] < 0:
        return "📉 Único que vale menos de lo que pagó. El mercado ha opinado."
    priciest = record["priciest"]
    return (
        f"💸 Su capricho: {priciest['player_name']} por "
        f"{_eur(priciest.get('price'))}."
    )


def render(summary, season, source):
    """The messages to send, in order."""
    order, by_gain, by_projection = best_drafts(summary)
    slowest = max(summary, key=lambda m: summary[m]["median_wait"] or 0)
    fastest = min(summary, key=lambda m: summary[m]["median_wait"] or 1e9)

    messages = [
        league_compare.render(
            summary,
            title=(
                "🎬 🏆 <b>EL GRAN CIERRE DEL DRAFT "
                f"{season}</b> 🏆 🎬\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Se apagan las luces, se recogen los cromos y alguien ya está "
                "arrepintiéndose. Los números, que no perdonan:"
            ),
            note=(
                "El valor es el precio de hoy en Biwenger contra lo que "
                f"pagaste. La proyección es la de Jornada Perfecta de {source}: "
                "ordena plantillas, no adivina la temporada."
            ),
        )
    ]

    for icon, manager in zip(ICONS, sorted(summary)):
        record = summary[manager]
        # Only the projection wants thousands dots; applying the swap to the
        # whole message turned every euro decimal comma into a full stop.
        sf = f"{record['projection']:,}".replace(",", ".")
        messages.append(
            f"{icon} <b>{manager}</b>\n"
            f"Gastó {_eur(record['cost'])} · vale {_eur(record['value'])} "
            f"({_eur(record['gain'])})\n"
            f"Proyección {sf} SF · {by_projection[manager]}º de {len(summary)}\n"
            f"Su mejor ficha por proyección: {record['star']}\n"
            f"{jab(manager, summary, slowest, fastest)}"
        )

    podium = "\n".join(
        f"{medal} <b>{m}</b> — {by_gain[m]}º en valor, "
        f"{by_projection[m]}º en proyección"
        for medal, m in zip(("🥇", "🥈", "🥉"), order[:3])
    )
    messages.append(
        f"🏆 <b>Los tres mejores drafts</b>\n\n{podium}\n\n"
        "<i>Suma de las dos posiciones. Sin ponderar: cualquier peso entre "
        "«el mercado te valora» y «tu plantilla puntúa» me lo estaría "
        "inventando.</i>"
    )
    return messages


def run(season="26-27", ranked="", gif=DEFAULT_GIF, write=False, echo=print):
    """Build the report and, with `write`, post it. Returns a process exit code.

    Split from `main` so `close.py` can chain it: closing the draft and telling
    the group how everyone did are the same gesture a day apart, and a second
    command nobody remembers is a command nobody runs.
    """
    ranked = ranked or os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        ".claude",
        "skills",
        "draft",
        season,
        "draft-ranked.csv",
    )
    picks = load_picks(season)
    if not picks:
        echo(f"No hay picks aplicados en draft/{season}/picks.")
        return 1

    projection, source = load_projection(ranked, picks)
    summary = summarise(picks, load_market(), projection)
    messages = render(summary, season, source)

    echo(f"{len(picks)} picks · {len(summary)} managers · proyección de {source}\n")
    for message in messages:
        echo("─" * 60)
        echo(message)
    echo("─" * 60)

    if not write:
        echo("\nEnsayo — nada enviado. Repite con --write.")
        return 0

    token, chat = config.TELEGRAM_BOT_TOKEN, _league_chat()
    if not (token and chat):
        echo("Sin credenciales de Telegram.")
        return 1
    if gif:
        send_telegram_animation(
            token, chat, gif, "🎬 Se acabó el draft. Que empiece el juicio."
        )
    sent = sum(bool(send_telegram_message(token, chat, m)) for m in messages)
    echo(f"\nEnviados {sent}/{len(messages)} mensajes.")
    return 0 if sent == len(messages) else 1


def _league_chat() -> str:
    """The supergroup the seven presidents read. Falls back to the owner's
    private chat when the group is not configured, so a half-set-up
    environment still gets the message instead of silently dropping it."""
    return config.TELEGRAM_DRAFT_CHAT_ID or config.TELEGRAM_CHAT_ID


def main():
    ap = argparse.ArgumentParser(description="Post-draft report to the group")
    ap.add_argument("--season", default="26-27")
    ap.add_argument("--gif", default=DEFAULT_GIF, help="'' para no mandar ninguno")
    ap.add_argument(
        "--ranked",
        default="",
        help="CSV rankeado; por defecto <skill>/<temporada>/draft-ranked.csv",
    )
    ap.add_argument("--write", action="store_true", help="enviar (por defecto: ensayo)")
    args = ap.parse_args()
    return run(season=args.season, ranked=args.ranked, gif=args.gif, write=args.write)


if __name__ == "__main__":
    raise SystemExit(main())
