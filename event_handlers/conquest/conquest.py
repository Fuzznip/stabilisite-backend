import logging
from datetime import datetime, timezone

from app import db
from event_handlers.event_handler import (
    EventSubmission, NotificationAuthor, NotificationField, NotificationResponse
)
from models.models import Users
from models.new_events import (
    Action, Challenge, ChallengeProof, ChallengeStatus,
    Event, EventLog, Region, Team, TeamMember,
    Territory, Trigger,
)
from services.conquest_service import (
    broadcast_delta,
    check_green_log,
    recalculate_team_points,
    update_region_control,
    update_territory_control,
)
from sqlalchemy import func, text


def conquest_handler(submission: EventSubmission) -> list[NotificationResponse]:
    logging.info(
        f"[CONQUEST] submission: rsn={submission.rsn}, trigger={submission.trigger!r}, "
        f"source={submission.source!r}, type={submission.type}, qty={submission.quantity}"
    )

    now = datetime.now(timezone.utc)
    event = Event.query.filter(
        Event.start_date <= now,
        Event.end_date >= now,
        Event.type == 'conquest',
    ).first()

    if not event:
        return []

    # Resolve user: try rsn → discord_id → alt_names
    user = None
    if submission.rsn:
        normalized = submission.rsn.replace("_", " ").replace("-", " ")
        user = Users.query.filter(
            func.lower(func.replace(func.replace(Users.runescape_name, "_", " "), "-", " ")) == normalized.lower()
        ).first()
    if not user and submission.id:
        user = Users.query.filter_by(discord_id=submission.id).first()
    if not user and submission.rsn:
        user = Users.query.filter(
            text("lower(replace(replace(:rsn, '_', ' '), '-', ' ')) = ANY(SELECT lower(replace(replace(x, '_', ' '), '-', ' ')) FROM unnest(alt_names) x)")
        ).params(rsn=submission.rsn).first()

    if not user:
        logging.warning(f"[CONQUEST] user not found: rsn={submission.rsn}, discord_id={submission.id}")
        return []

    # Idempotency guard
    if submission.request_id:
        if Action.query.filter_by(request_id=submission.request_id).first():
            logging.warning(f"[CONQUEST] duplicate request_id={submission.request_id!r}, skipping")
            return []

    # Record action first (always, regardless of team membership)
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
    db.session.commit()

    # Resolve team membership
    team_member = TeamMember.query.join(Team).filter(
        Team.event_id == event.id,
        TeamMember.user_id == user.id,
    ).first()

    if not team_member:
        logging.info(f"[CONQUEST] {submission.rsn} has no team in event {event.id}")
        return []

    team = Team.query.get(team_member.team_id)

    # Batch-load all territories for this event, keyed by challenge_id
    regions = Region.query.filter_by(event_id=event.id).all()
    region_ids = [r.id for r in regions]
    region_by_id = {r.id: r for r in regions}

    territories = Territory.query.filter(Territory.region_id.in_(region_ids)).all() if region_ids else []
    territory_by_id = {t.id: t for t in territories}
    territory_by_challenge_id = {t.challenge_id: t for t in territories if t.challenge_id}

    challenge_ids = list(territory_by_challenge_id.keys())
    challenges = Challenge.query.filter(Challenge.id.in_(challenge_ids)).all() if challenge_ids else []
    trigger_ids = list({c.trigger_id for c in challenges if c.trigger_id})
    triggers = Trigger.query.filter(Trigger.id.in_(trigger_ids)).all() if trigger_ids else []
    triggers_by_id = {t.id: t for t in triggers}

    # Normalize submission for matching
    submission_trigger_lower = submission.trigger.lower()
    submission_source_lower = submission.source.lower() if submission.source else ""

    new_log_entries: list[EventLog] = []

    for challenge in challenges:
        if not challenge.trigger_id:
            continue

        trigger = triggers_by_id.get(challenge.trigger_id)
        if not trigger:
            continue

        trigger_name_lower = trigger.name.lower()
        trigger_source_lower = trigger.source.lower() if trigger.source else ""

        name_match = trigger_name_lower == submission_trigger_lower
        source_match = (not trigger_source_lower) or (trigger_source_lower == submission_source_lower)

        if not (name_match and source_match):
            continue

        # Get or create challenge status
        challenge_status = ChallengeStatus.query.filter_by(
            team_id=team.id,
            challenge_id=challenge.id,
        ).first()

        if not challenge_status:
            challenge_status = ChallengeStatus(
                team_id=team.id,
                challenge_id=challenge.id,
                quantity=0,
                completed=False,
            )
            db.session.add(challenge_status)
            db.session.flush()

        old_completions = challenge_status.quantity // challenge.quantity

        # Atomic quantity increment to avoid race conditions
        increment = challenge.count_per_action if challenge.count_per_action is not None else submission.quantity
        db.session.execute(
            text("UPDATE new_stability.challenge_statuses SET quantity = quantity + :qty, updated_at = NOW() WHERE id = :cs_id"),
            {"qty": increment, "cs_id": str(challenge_status.id)},
        )
        db.session.flush()
        db.session.refresh(challenge_status)

        new_completions = challenge_status.quantity // challenge.quantity
        challenge_status.completed = new_completions > 0

        # Record proof
        db.session.add(ChallengeProof(
            challenge_status_id=challenge_status.id,
            action_id=action.id,
            img_path=submission.img_path,
        ))

        if new_completions <= old_completions:
            continue

        # New completion threshold crossed — run conquest logic
        territory = territory_by_challenge_id[challenge.id]
        region = region_by_id[territory.region_id]

        log = EventLog(
            event_id=event.id,
            team_id=team.id,
            type='CHALLENGE_COMPLETED',
            entity_type='challenge',
            entity_id=challenge.id,
            meta={'completionCount': new_completions, 'challengeName': trigger.name},
        )
        db.session.add(log)
        db.session.flush()
        new_log_entries.append(log)

        territory_result = update_territory_control(territory.id, db.session)

        if territory_result['changed']:
            new_team_id = territory_result['new_team_id']
            prev_team_id = territory_result['previous_team_id']

            territory_log = EventLog(
                event_id=event.id,
                team_id=new_team_id,
                type='TERRITORY_CONTROL',
                entity_type='territory',
                entity_id=territory.id,
                meta={'previousTeamId': str(prev_team_id) if prev_team_id else None},
            )
            db.session.add(territory_log)
            db.session.flush()
            new_log_entries.append(territory_log)

            region_result = update_region_control(region.id, db.session)

            if region_result['changed']:
                new_region_team_id = region_result['new_team_id']
                prev_region_team_id = region_result['previous_team_id']

                region_log = EventLog(
                    event_id=event.id,
                    team_id=new_region_team_id,
                    type='REGION_CONTROL',
                    entity_type='region',
                    entity_id=region.id,
                    meta={'previousTeamId': str(prev_region_team_id) if prev_region_team_id else None},
                )
                db.session.add(region_log)
                db.session.flush()
                new_log_entries.append(region_log)

        if check_green_log(team.id, region.id, db.session):
            green_log = EventLog(
                event_id=event.id,
                team_id=team.id,
                type='GREEN_LOG',
                entity_type='region',
                entity_id=region.id,
                meta={},
            )
            db.session.add(green_log)
            db.session.flush()
            new_log_entries.append(green_log)

    # Recalculate points for every team in the event
    all_teams = Team.query.filter_by(event_id=event.id).all()
    for t in all_teams:
        recalculate_team_points(t.id, event.id, db.session)

    db.session.commit()

    if new_log_entries:
        broadcast_delta(event.id, [entry.serialize() for entry in new_log_entries])

    return _build_notifications(event, team, submission, new_log_entries)


def _build_notifications(event, team, submission, log_entries: list[EventLog]) -> list[NotificationResponse]:
    if not log_entries:
        return []

    db.session.refresh(team)

    territory_changes = [e for e in log_entries if e.type == 'TERRITORY_CONTROL']
    region_changes = [e for e in log_entries if e.type == 'REGION_CONTROL']
    green_logs = [e for e in log_entries if e.type == 'GREEN_LOG']

    desc_parts = [f"Completed a challenge: **{submission.trigger}**"]
    if territory_changes:
        desc_parts.append(f"Captured {len(territory_changes)} {'territory' if len(territory_changes) == 1 else 'territories'}!")
    if region_changes:
        desc_parts.append(f"Seized control of {len(region_changes)} {'region' if len(region_changes) == 1 else 'regions'}!")
    if green_logs:
        desc_parts.append(f"Achieved Green Log on {len(green_logs)} {'region' if len(green_logs) == 1 else 'regions'}!")

    return [NotificationResponse(
        threadId=event.thread_id,
        title=f"{submission.rsn} — Conquest",
        color=0x2ECC71,
        description="\n".join(desc_parts),
        author=NotificationAuthor(name=team.name, icon_url=team.image_url),
        fields=[NotificationField(name="Team Points", value=str(team.points), inline=True)],
        thumbnailImage=submission.img_path,
    )]
