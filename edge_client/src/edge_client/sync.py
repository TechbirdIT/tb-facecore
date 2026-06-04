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


def flush_queue(client, store, edge_id: str) -> None:
    """Post pending events in order; stop at first connection failure.

    4xx rejects are logged and dropped so one bad item cannot block the queue.
    Legacy checkin_queue rows (pre-event-contract) drain through post_event
    with zero scores.
    """
    for item in store.pending_events():
        try:
            client.post_event(
                edge_id, item["device_id"], item["timestamp"],
                item["similarity"], item["liveness"],
            )
        except CheckinRejectedError:
            logger.exception("event rejected by server; dropping %s", item)
        except Exception:
            logger.warning("flush stopped; Frappe unreachable")
            return
        store.delete_event(item["id"])

    for item in store.pending_checkins():  # legacy queue
        try:
            client.post_event(
                item["edge_id"], item["device_id"], item["timestamp"], 0.0, 0.0
            )
        except CheckinRejectedError:
            logger.exception("legacy check-in rejected; dropping %s", item)
        except Exception:
            return
        store.delete_checkin(item["id"])
