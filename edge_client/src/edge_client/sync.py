"""Sync worker and offline-queue flush."""

from __future__ import annotations

import logging

from edge_client.frappe_client import CheckinRejectedError
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
    """Post pending check-ins in order; stop at the first connection failure.

    A validation reject (4xx) is logged with its payload and dropped so one
    bad item cannot block the queue.
    """
    for item in store.pending_checkins():
        try:
            client.post_checkin(item["device_id"], item["timestamp"], item["edge_id"])
        except CheckinRejectedError:
            logger.exception("check-in rejected by server; dropping %s", item)
        except Exception:
            logger.warning("flush stopped; Frappe unreachable")
            return
        store.delete_checkin(item["id"])
