"""Idempotent catalog sync: merges the in-repo dataset into Firestore.

Merge semantics (safe to re-run monthly as the dataset grows):
- Water not in Firestore      → created.
- Exists and NOT verified     → dataset wins, but user-owned fields
                                (photo_url, added_by, verified) are preserved.
- Exists and verified=True    → untouched (a checked bottle beats the dataset);
                                counted so the summary shows drift.

Optional Telegram notification when something changed: set
TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID (missing creds → silent skip).

    bazel run //packages/be_water/web:sync_local
"""

import os

from core.sdk import firestore
from core.sdk.telegram import send_telegram_message
from core.utils import get_logger
from packages.be_water.web import config  # noqa: F401  (sets FIRESTORE_PROJECT)
from packages.be_water.web.domain import Water
from packages.be_water.web.repository import WATERS
from packages.be_water.web.seed_data import SEED_WATERS

logger = get_logger(__name__)


def _dataset_water(raw: dict) -> Water:
    return Water(
        id=raw["id"],
        name=raw["name"],
        brand=raw.get("brand", raw["name"]),
        spring=raw.get("spring", ""),
        province=raw.get("province", ""),
        community=raw.get("community", ""),
        sparkling=raw.get("sparkling", False),
        minerals=raw.get("minerals", {}),
        photo_url=raw.get("photo_url"),
        added_by="seed",
        # Dataset entries backed by a bottle-label photo carry verified=True.
        verified=raw.get("verified", False),
    )


def sync_catalog() -> dict:
    existing = dict(firestore.list_documents(WATERS))
    created, updated, unchanged, kept_verified = [], [], [], []

    for raw in SEED_WATERS:
        water = _dataset_water(raw)
        current = existing.get(water.id)
        if current is None:
            firestore.set_document(WATERS, water.id, water.to_firestore())
            created.append(water.name)
            continue
        if current.get("verified"):
            # Verified docs are data-frozen, but a dataset photo may still
            # fill an empty photo_url (enrichment, never replacement).
            if water.photo_url and not current.get("photo_url"):
                enriched = dict(current)
                enriched["photo_url"] = water.photo_url
                firestore.set_document(WATERS, water.id, enriched)
                updated.append(water.name)
            else:
                kept_verified.append(water.name)
            continue
        merged = water.to_firestore()
        merged["photo_url"] = current.get("photo_url") or merged["photo_url"]
        merged["label_photo_url"] = (
            current.get("label_photo_url") or merged["label_photo_url"]
        )
        merged["added_by"] = current.get("added_by") or merged["added_by"]
        if merged == current:
            unchanged.append(water.name)
        else:
            firestore.set_document(WATERS, water.id, merged)
            updated.append(water.name)

    summary = {
        "created": created,
        "updated": updated,
        "unchanged": len(unchanged),
        "kept_verified": kept_verified,
        "dataset_size": len(SEED_WATERS),
    }
    # "created" is a reserved LogRecord attribute — prefix the extra keys.
    logger.info(
        "Catalog sync finished.", extra={f"sync_{k}": v for k, v in summary.items()}
    )
    _maybe_notify(summary)
    return summary


def _maybe_notify(summary: dict) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not (token and chat_id):
        return
    if not (summary["created"] or summary["updated"]):
        return
    lines = ["💧 <b>Catálogo Be Water sincronizado</b>"]
    if summary["created"]:
        lines.append(
            f"🆕 Nuevas ({len(summary['created'])}): " + ", ".join(summary["created"])
        )
    if summary["updated"]:
        lines.append(
            f"♻️ Actualizadas ({len(summary['updated'])}): "
            + ", ".join(summary["updated"])
        )
    if summary["kept_verified"]:
        lines.append(f"🔒 Verificadas intactas: {len(summary['kept_verified'])}")
    send_telegram_message(bot_token=token, chat_id=chat_id, text="\n".join(lines))


def main() -> None:
    summary = sync_catalog()
    print(
        f"Sync done: +{len(summary['created'])} nuevas, "
        f"{len(summary['updated'])} actualizadas, "
        f"{summary['unchanged']} sin cambios, "
        f"{len(summary['kept_verified'])} verificadas intactas."
    )


if __name__ == "__main__":
    main()
