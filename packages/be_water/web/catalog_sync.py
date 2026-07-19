"""Idempotent catalog sync: merges the in-repo dataset into Firestore.

Merge semantics (safe to re-run monthly as the dataset grows):
- Water not in Firestore      → created.
- Exists and NOT verified     → dataset wins, but user-owned fields
                                (photo_url, added_by, verified) and
                                label-backed minerals (verified_fields)
                                are preserved.
- Exists and verified=True    → untouched (a checked bottle beats the dataset);
                                counted so the summary shows drift.

Optional Telegram notification when something changed: creds come from the
TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID env vars (local runs) or from the
consolidated Secret Manager JSON (the monthly Cloud Run Job); missing creds
→ silent skip.

    bazel run //packages/be_water/web:sync_local
"""

import os

from core.sdk import firestore
from core.sdk.telegram import send_telegram_message
from core.utils import get_logger
from packages.be_water.web import config  # also sets FIRESTORE_PROJECT
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
        label_photo_url=raw.get("label_photo_url"),
        verified_fields=list(raw.get("verified_fields", [])),
        mentions=list(raw.get("mentions", [])),
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
            # Verified docs are data-frozen, but dataset photos may still
            # fill empty photo slots (enrichment, never replacement).
            enriched = dict(current)
            changed = False
            for extra_field in ("photo_url", "label_photo_url", "mentions"):
                dataset_value = getattr(water, extra_field)
                if dataset_value and not current.get(extra_field):
                    enriched[extra_field] = dataset_value
                    changed = True
            if changed:
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
        merged["verified_fields"] = sorted(
            set(merged.get("verified_fields", []))
            | set(current.get("verified_fields", []) or [])
        )
        # Label-backed values beat the dataset: a mineral someone verified
        # against a bottle keeps its current value even though unverified
        # docs otherwise take the dataset's numbers.
        current_minerals = current.get("minerals") or {}
        merged["minerals"] = dict(merged["minerals"])
        for label_field in current.get("verified_fields", []) or []:
            if label_field in current_minerals:
                merged["minerals"][label_field] = current_minerals[label_field]
        merged["added_by"] = current.get("added_by") or merged["added_by"]
        merged["added_at"] = current.get("added_at") or merged["added_at"]
        if merged == current:
            unchanged.append(water.name)
        else:
            firestore.set_document(WATERS, water.id, merged)
            updated.append(water.name)

    # Firestore docs the dataset knows nothing about: genuinely new waters
    # worth adding to the dataset — or a typo'd name that slugged into a
    # near-duplicate doc. Either way a human should look at them.
    dataset_ids = {raw["id"] for raw in SEED_WATERS}
    user_only = sorted(
        f"{doc.get('name', doc_id)} ({doc.get('added_by', '?')})"
        for doc_id, doc in existing.items()
        if doc_id not in dataset_ids
    )

    summary = {
        "created": created,
        "updated": updated,
        "unchanged": len(unchanged),
        "kept_verified": kept_verified,
        "user_only": user_only,
        "dataset_size": len(SEED_WATERS),
    }
    # "created" is a reserved LogRecord attribute — prefix the extra keys.
    logger.info(
        "Catalog sync finished.", extra={f"sync_{k}": v for k, v in summary.items()}
    )
    _maybe_notify(summary)
    return summary


def _maybe_notify(summary: dict) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip() or config.TELEGRAM_BOT_TOKEN
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip() or config.TELEGRAM_CHAT_ID
    if not (token and chat_id):
        return
    if not (summary["created"] or summary["updated"] or summary["user_only"]):
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
    if summary["user_only"]:
        lines.append(
            f"👀 Solo de usuarios, no en el dataset "
            f"({len(summary['user_only'])}): " + ", ".join(summary["user_only"])
        )
    send_telegram_message(bot_token=token, chat_id=chat_id, text="\n".join(lines))


def main() -> None:
    summary = sync_catalog()
    print(
        f"Sync done: +{len(summary['created'])} nuevas, "
        f"{len(summary['updated'])} actualizadas, "
        f"{summary['unchanged']} sin cambios, "
        f"{len(summary['kept_verified'])} verificadas intactas, "
        f"{len(summary['user_only'])} solo de usuarios."
    )


if __name__ == "__main__":
    main()
