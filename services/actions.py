"""Action resolution shared by v2 handlers.

Several handlers see the same submission, and `actions.request_id` is globally
unique. conquest_handler inserts an Action for every submission before it checks
any trigger, so by the time another handler runs the row already exists and a
second insert aborts the transaction. Reuse it instead, and detect a real replay
by asking whether that action already produced proofs against *this* event's
challenges.
"""
from app import db
from models.new_events import Action, Challenge, ChallengeProof, ChallengeStatus


def resolve_action(submission, user, now, challenge_ids, by_parent: bool = False):
    """Get the Action for this submission, and whether we already scored it.

    `challenge_ids` scopes the replay check to one event. Set `by_parent` when
    the scoring challenges are *children* of the ids you pass (botw's boss
    containers); leave it False when the ids are the scoring challenges
    themselves (clog slots).

    Returns (action, already_scored).
    """
    existing = (
        Action.query.filter_by(request_id=submission.request_id).first()
        if submission.request_id else None
    )

    if existing:
        scope = (
            Challenge.parent_challenge_id.in_(challenge_ids)
            if by_parent else Challenge.id.in_(challenge_ids)
        )
        already_scored = db.session.query(
            ChallengeProof.query
            .join(ChallengeStatus, ChallengeStatus.id == ChallengeProof.challenge_status_id)
            .join(Challenge, Challenge.id == ChallengeStatus.challenge_id)
            .filter(ChallengeProof.action_id == existing.id, scope)
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
