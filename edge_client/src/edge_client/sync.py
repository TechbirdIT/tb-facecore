"""Sync worker and offline-queue flush."""

from __future__ import annotations

import logging

from edge_client.matcher import Matcher

logger = logging.getLogger(__name__)


def sync_faces(client, store, model_version: str) -> Matcher:
    """Pull incremental face data, upsert to cache, return a fresh Matcher.

    On fetch failure, rebuild the Matcher from the last-good cache.
    """
    try:
        rows = client.fetch_face_data(since=store.max_modified())
        if rows:
            store.upsert_faces(rows)
    except Exception:
        logger.exception("face sync failed; using last-good cache")
    return Matcher(store.all_faces(), model_version=model_version)


def flush_queue(client, store) -> None:
    """Post pending check-ins in order; stop at the first failure."""
    for item in store.pending_checkins():
        try:
            client.post_checkin(item["device_id"], item["timestamp"], item["edge_id"])
        except Exception:
            logger.warning("flush stopped; Frappe still unreachable")
            return
        store.delete_checkin(item["id"])
