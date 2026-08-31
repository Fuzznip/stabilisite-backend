"""Boss of the week on the new event schema.

Configuration lives entirely in the database: a botw event owns bosses, each
boss owns a KC challenge and one challenge per collection log drop, and each of
those carries its own point value. Scoring is per player, so progress is written
to player-owned ChallengeStatus rows (team_id NULL).

The legacy handler in boss_of_the_week_handler.py still serves old
BOSS_OF_THE_WEEK events in public.events and is unrelated to this one.
"""
import fnmatch
import logging
from datetime import datetime, timezone

from app import db
from event_handlers.event_handler import (
    EventSubmission, NotificationAuthor, NotificationField, NotificationResponse
)
from helper.user_lookup import resolve_user
from models.new_events import (
    Action, BotwBoss, Challenge, ChallengeProof, ChallengeStatus, Event, Trigger,
)
from services.botw_service import player_points
from sqlalchemy import text


def botw_event_handler(submission: EventSubmission) -> list[NotificationResponse]:
    """Score a submission against every botw event currently running.

    Overlapping events are legitimate — a new week can start before the previous
    one closes, and a one-off side event can run alongside the weekly. Scoring
    only the first match would silently hand every submission to whichever row
    the database happened to return, so each active event is scored
    independently and contributes its own notification.
    """
    now = datetime.now(timezone.utc)

    events = Event.query.filter(
        Event.start_date <= now,
        Event.end_date >= now,
        Event.type == 'botw',
    ).all()

    if not events:
        logging.info("[BOTW] No active event, skipping")
        return []

    user = resolve_user(submission.rsn, submission.id)
    if not user:
        logging.warning(f"[BOTW] user not found: rsn={submission.rsn}, discord_id={submission.id}")
        return []

    notifications: list[NotificationResponse] = []
    for event in events:
        # One event failing must not cost the others their score; each is
        # committed on its own inside _score_event.
        try:
            notifications.extend(_score_event(event, submission, user, now))
        except Exception:
            logging.exception(f"[BOTW] scoring failed for event {event.id}")
            db.session.rollback()

    return notifications


def _score_event(event, submission: EventSubmission, user, now) -> list[NotificationResponse]:
    """Score the submission against one event. Commits its own work."""
    logging.info(f"[BOTW] Matched — event={event.name!r} ({event.id})")

    bosses = BotwBoss.query.filter_by(event_id=event.id).all()
    container_ids = [b.challenge_id for b in bosses if b.challenge_id]
    if not container_ids:
        logging.info(f"[BOTW] event {event.id} has no bosses configured")
        return []

    boss_by_container = {b.challenge_id: b for b in bosses if b.challenge_id}

    challenges = Challenge.query.filter(
        Challenge.parent_challenge_id.in_(container_ids),
        Challenge.trigger_id.isnot(None),
    ).all()
    if not challenges:
        return []

    triggers = Trigger.query.filter(
        Trigger.id.in_({c.trigger_id for c in challenges})
    ).all()
    triggers_by_id = {t.id: t for t in triggers}

    action, already_scored = _resolve_action(submission, user, container_ids, now)
    if already_scored:
        logging.warning(f"[BOTW] duplicate request_id={submission.request_id!r}, skipping")
        return []

    submission_trigger_lower = submission.trigger.lower()
    submission_source_lower = submission.source.lower() if submission.source else ""

    scored: list[tuple[BotwBoss, Trigger, int]] = []

    for challenge in challenges:
        trigger = triggers_by_id.get(challenge.trigger_id)
        if not trigger:
            continue

        trigger_source_lower = trigger.source.lower() if trigger.source else ""
        name_match = fnmatch.fnmatch(submission_trigger_lower, trigger.name.lower())
        source_match = (not trigger_source_lower) or (trigger_source_lower == submission_source_lower)

        if not (name_match and source_match):
            continue

        if challenge.min_quantity_per_action is not None and submission.quantity < challenge.min_quantity_per_action:
            continue

        # A KC submission carries the player's total kill count, not one kill,
        # so KC challenges are seeded with count_per_action=1.
        if challenge.count_per_action is not None:
            increment = challenge.count_per_action
        elif challenge.min_quantity_per_action is not None:
            increment = 1
        else:
            increment = submission.quantity or 1

        status = _get_or_create_status(user.id, challenge.id)

        db.session.execute(
            text("UPDATE new_stability.challenge_statuses SET quantity = quantity + :qty, updated_at = NOW() WHERE id = :cs_id"),
            {"qty": increment, "cs_id": str(status.id)},
        )
        db.session.add(ChallengeProof(
            challenge_status_id=status.id,
            action_id=action.id,
            img_path=submission.img_path,
        ))

        boss = boss_by_container[challenge.parent_challenge_id]
        scored.append((boss, trigger, increment * (challenge.value or 0)))

    db.session.commit()

    if not scored:
        return []

    return _build_notifications(event, user, submission, scored)


def _resolve_action(submission: EventSubmission, user, container_ids, now) -> tuple[Action, bool]:
    """Get the Action for this submission, and whether we already scored it.

    Other handlers write the same action rows, and `actions.request_id` is
    globally unique — so when a conquest or bingo event is running alongside
    this one, the action for a submission already exists by the time we get
    here. Inserting a second one would abort the transaction and silently drop
    the score. Reuse it instead, and detect real duplicates by checking whether
    that action already produced proofs against *this* event's challenges.
    """
    existing = Action.query.filter_by(request_id=submission.request_id).first() if submission.request_id else None

    if existing:
        already_scored = db.session.query(
            ChallengeProof.query
            .join(ChallengeStatus, ChallengeStatus.id == ChallengeProof.challenge_status_id)
            .join(Challenge, Challenge.id == ChallengeStatus.challenge_id)
            .filter(
                ChallengeProof.action_id == existing.id,
                Challenge.parent_challenge_id.in_(container_ids),
            )
            .exists()
        ).scalar()
        return existing, bool(already_scored)

    action = Action(
        player_id=user.id,
        type=submission.type,
        name=submission.trigger,
        source=submission.source,
        quantity=submission.quantity,
        value=submission.totalValue,
        date=now,
        request_id=submission.request_id,
    )
    db.session.add(action)
    db.session.flush()
    return action, False


def _get_or_create_status(player_id, challenge_id) -> ChallengeStatus:
    status = ChallengeStatus.query.filter_by(
        player_id=player_id,
        challenge_id=challenge_id,
    ).first()

    if not status:
        status = ChallengeStatus(
            player_id=player_id,
            team_id=None,
            challenge_id=challenge_id,
            quantity=0,
            completed=False,
        )
        db.session.add(status)
        db.session.flush()

    return status


def _build_notifications(event, user, submission, scored) -> list[NotificationResponse]:
    if all(trigger.type == 'KC' for _, trigger, _ in scored):
        return []

    earned = sum(points for _, _, points in scored)
    total = player_points(event.id, user.id)

    title = f"{submission.rsn} received {submission.trigger}!"

    return [NotificationResponse(
        threadId=event.thread_id,
        title=title,
        color=0xFF0055,
        description=f"Worth **{earned}** {'point' if earned == 1 else 'points'}.",
        author=NotificationAuthor(name=submission.rsn, icon_url=user.discord_avatar_url),
        fields=[NotificationField(name="Total Points", value=str(total), inline=True)],
        thumbnailImage=submission.img_path,
    )]
