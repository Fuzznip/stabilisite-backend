import logging

from app import db
from event_handlers.event_handler import EventSubmission, NotificationResponse
from models.models import Users, CollectionLogDrop


def _resolve_member(submission: EventSubmission) -> Users | None:
    """Best-effort match of a Dink submission to a clan member.

    Prefer the discord id (unique), then the RuneScape name, then alt/previous
    names (accounts get renamed and Dink keys by current RSN).
    """
    if submission.id:
        user = Users.query.filter_by(discord_id=str(submission.id)).first()
        if user:
            return user

    rsn = (submission.rsn or "").strip()
    if not rsn:
        return None

    user = Users.query.filter(Users.runescape_name.ilike(rsn)).first()
    if user:
        return user

    # alt_names / previous_names are Postgres String arrays.
    return Users.query.filter(
        db.or_(
            Users.alt_names.any(rsn),
            Users.previous_names.any(rsn),
        )
    ).first()


def collection_log_handler(submission: EventSubmission) -> list[NotificationResponse]:
    """Persist any collection-log-eligible item a player received.

    stabiliserver forwards these with type == "CLOG" for every dropped item whose
    id is in the collection log catalog, so we simply record each one. We keep
    every instance (duplicates included) to support per-member counts and dates.
    """
    if submission.type != "CLOG":
        return []

    if submission.item_id is None:
        logging.warning(f"[CLOG] submission missing item_id, skipping: rsn={submission.rsn!r} trigger={submission.trigger!r}")
        return []

    member = _resolve_member(submission)

    drop = CollectionLogDrop(
        discord_id=member.discord_id if member else None,
        rsn=submission.rsn,
        item_id=int(submission.item_id),
        item_name=submission.trigger,
        source=submission.source,
        quantity=submission.quantity or 1,
        value=submission.totalValue or 0,
        screenshot=submission.img_path,
    )
    db.session.add(drop)
    db.session.commit()

    logging.info(
        f"[CLOG] recorded item_id={submission.item_id} ({submission.trigger!r}) "
        f"rsn={submission.rsn!r} member={'yes' if member else 'no'}"
    )
    # No Discord notification for v1 (the website is the surface).
    return []
