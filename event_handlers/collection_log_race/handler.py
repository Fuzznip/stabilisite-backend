"""Collection log race: scoring a drop against a team's collection log.

A slot completes the first time any member of a team receives the item. Later
drops of the same item by that team are ignored outright — no points, no proof,
no notification — which is what keeps ChallengeStatus.quantity meaning "1 = the
team has this".

Scoring rides on ordinary DROP triggers through the event whitelist. It must not
use the CLOG submission type: those come from Dink's LOOT notifier filtered by
the same whitelist, so they are not an independent feed, and Dink's real
COLLECTION notifier only fires on a player's *first* time getting a slot — which
would silently skip anyone who already owns it personally.
"""
import logging
from datetime import datetime, timezone

from app import db
from event_handlers.event_handler import (
    EventSubmission, NotificationAuthor, NotificationField, NotificationResponse
)
from helper.user_lookup import resolve_user
from models.new_events import (
    Challenge, ChallengeProof, ChallengeStatus, ClogSlot, Event, Team, TeamMember, Trigger,
)
from services.actions import resolve_action
from services.challenge_evaluator import ChallengeEvaluator
from services.clog_service import progress


def collection_log_race_handler(submission: EventSubmission) -> list[NotificationResponse]:
    """Score a submission against every running collection log race."""
    # A KC submission carries a cumulative kill count, never an item.
    if submission.type == 'KC':
        return []

    now = datetime.now(timezone.utc)
    events = Event.query.filter(
        Event.start_date <= now,
        Event.end_date >= now,
        Event.type == 'clog',
    ).all()

    if not events:
        return []

    user = resolve_user(submission.rsn, submission.id)
    if not user:
        logging.warning(f"[CLOG RACE] user not found: rsn={submission.rsn}, discord_id={submission.id}")
        return []

    notifications: list[NotificationResponse] = []
    for event in events:
        # One event failing must not cost the others their score.
        try:
            notifications.extend(_score_event(event, submission, user, now))
        except Exception:
            logging.exception(f"[CLOG RACE] scoring failed for event {event.id}")
            db.session.rollback()

    return notifications


def _score_event(event, submission, user, now) -> list[NotificationResponse]:
    team = (
        Team.query
        .join(TeamMember, TeamMember.team_id == Team.id)
        .filter(Team.event_id == event.id, TeamMember.user_id == user.id)
        .first()
    )
    if not team:
        logging.info(f"[CLOG RACE] {submission.rsn} has no team in event {event.id}")
        return []

    # Exact lowercased name match, not fnmatch: slot names come from the game
    # cache and a wildcard would let one slot swallow another ("Dragon axe" vs
    # "Dragon axe (or)").
    rows = (
        db.session.query(ClogSlot, Challenge)
        .join(Challenge, Challenge.id == ClogSlot.challenge_id)
        .join(Trigger, Trigger.id == Challenge.trigger_id)
        .filter(
            ClogSlot.event_id == event.id,
            db.func.lower(Trigger.name) == submission.trigger.lower(),
        )
        .first()
    )
    if not rows:
        return []

    slot, challenge = rows

    existing = ChallengeStatus.query.filter_by(
        team_id=team.id, challenge_id=challenge.id,
    ).first()
    if existing and existing.completed:
        logging.info(f"[CLOG RACE] {team.name} already has {slot.name!r}, ignoring")
        return []

    # Replay detection is scoped to every slot challenge in THIS event, not just
    # the one that matched. `actions.request_id` is globally unique, so a
    # replayed request_id arriving with a different item name reuses the same
    # action row — scoping to the matched challenge alone would miss it and score
    # the item twice. A scalar subquery keeps this one round trip rather than
    # materialising all ~406 ids per submission.
    event_slot_challenges = (
        db.session.query(Challenge.id)
        .join(ClogSlot, ClogSlot.challenge_id == Challenge.id)
        .filter(ClogSlot.event_id == event.id)
        .scalar_subquery()
    )
    action, already_scored = resolve_action(submission, user, now, event_slot_challenges)
    if already_scored:
        logging.warning(f"[CLOG RACE] duplicate request_id={submission.request_id!r}, skipping")
        return []

    if not existing:
        existing = ChallengeStatus(
            team_id=team.id, player_id=None, challenge_id=challenge.id,
            quantity=0, completed=False,
        )
        db.session.add(existing)
        db.session.flush()

    # Add the proof PENDING, before update_challenge_status is called: its
    # internal commit is what persists the action, the status update and this
    # proof together in one transaction. Committing the proof separately, after
    # that call, would leave a window where a completed-but-unproven status
    # could survive a later failure with no way to repair it (the
    # existing.completed early-return above would just skip it forever).
    db.session.add(ChallengeProof(
        challenge_status_id=existing.id,
        action_id=action.id,
        img_path=submission.img_path,
    ))

    status = ChallengeEvaluator.update_challenge_status(str(challenge.id), str(team.id), 1)
    if status is None:
        # The pending proof (and, for a fresh slot, the status row flushed just
        # above) must not ride along on a later event's commit — every event in
        # the handler's loop shares this session.
        db.session.rollback()
        logging.error(f"[CLOG RACE] could not update status for challenge {challenge.id}")
        return []

    return _build_notification(event, team, user, submission, slot, challenge)


def _build_notification(event, team, user, submission, slot, challenge) -> list[NotificationResponse]:
    # stabiliserver builds its webhook URL as f"...?thread_id={thread_id}", so a
    # None would post to "?thread_id=None" and be dropped. Scoring is unaffected.
    if not event.thread_id:
        logging.info(f"[CLOG RACE] {team.name} completed {slot.name!r} (event has no thread)")
        return []

    standings = progress(event.id)['standings']
    row = next((s for s in standings if s['team_id'] == str(team.id)), None)
    points = int(challenge.value or 0)

    return [NotificationResponse(
        threadId=event.thread_id,
        title=f"{submission.rsn} completed {slot.name}!",
        color=0x3BA55D,
        description=f"Worth **{points}** {'point' if points == 1 else 'points'} for **{team.name}**.",
        author=NotificationAuthor(name=submission.rsn, icon_url=user.discord_avatar_url),
        fields=[
            NotificationField(name="Team Points", value=str(row['points'] if row else points), inline=True),
            NotificationField(name="Slots", value=str(row['slots_completed'] if row else 1), inline=True),
        ],
        thumbnailImage=submission.img_path,
    )]
