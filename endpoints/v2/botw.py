import json

from app import app, db
from flask import jsonify, request
from helper.helpers import ModelEncoder
from models.new_events import BotwBoss, Challenge, Event
from services.botw_service import (
    catalog_pages,
    leaderboard,
    seed_boss,
    serialize_boss,
)


def _require_botw_event(event_id):
    """Return (event, None) or (None, error_response)."""
    event = Event.query.get(event_id)
    if not event:
        return None, (jsonify({'error': 'Event not found'}), 404)
    if event.type != 'botw':
        return None, (jsonify({'error': 'Event is not a boss of the week event'}), 400)
    return event, None


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------

@app.route('/v2/botw/catalog/pages', methods=['GET'])
def get_botw_catalog_pages():
    """Collection log pages available to seed a boss from."""
    pages = catalog_pages()
    category = request.args.get('category')
    if category:
        pages = [p for p in pages if p['category'].lower() == category.lower()]
    return jsonify({'data': pages, 'total': len(pages)}), 200


# ---------------------------------------------------------------------------
# Bosses
# ---------------------------------------------------------------------------

@app.route('/v2/events/<event_id>/botw/bosses', methods=['GET'])
def get_botw_bosses(event_id):
    event, err = _require_botw_event(event_id)
    if err:
        return err

    bosses = BotwBoss.query.filter_by(event_id=event_id).order_by(
        BotwBoss.display_order, BotwBoss.created_at
    ).all()
    return json.dumps({'data': [serialize_boss(b) for b in bosses]}, cls=ModelEncoder), 200


@app.route('/v2/events/<event_id>/botw/bosses', methods=['POST'])
def create_botw_boss(event_id):
    """Seed a boss: builds its KC challenge and one challenge per clog drop."""
    event, err = _require_botw_event(event_id)
    if err:
        return err

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON received'}), 400
    if not data.get('name'):
        return jsonify({'error': 'Missing required field: name'}), 400

    try:
        boss = seed_boss(
            event_id=event.id,
            name=data['name'],
            clog_page=data.get('clog_page'),
            kc_points=data.get('kc_points', 1),
            drop_points=data.get('drop_points', 1),
            drop_source=data.get('drop_source'),
            image_url=data.get('image_url'),
            display_order=data.get('display_order'),
        )
    except ValueError as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

    return json.dumps(serialize_boss(boss), cls=ModelEncoder), 201


@app.route('/v2/botw/bosses/<boss_id>', methods=['DELETE'])
def delete_botw_boss(boss_id):
    """Remove a boss and its challenge tree. Statuses cascade with it."""
    boss = BotwBoss.query.get(boss_id)
    if not boss:
        return jsonify({'error': 'Boss not found'}), 404

    container_id = boss.challenge_id
    db.session.delete(boss)
    db.session.flush()

    if container_id:
        # Bulk-delete rather than session.delete(container): the self-referencing
        # children relationship has no ORM cascade, so deleting the container
        # through the session nullifies parent_challenge_id on its children and
        # leaves them (and their statuses) orphaned in the table. Deleting the
        # rows directly lets the ON DELETE CASCADE FKs do the real work.
        Challenge.query.filter_by(parent_challenge_id=container_id).delete(synchronize_session=False)
        Challenge.query.filter_by(id=container_id).delete(synchronize_session=False)

    db.session.commit()

    return jsonify({'message': 'Boss deleted successfully'}), 200


@app.route('/v2/botw/bosses/<boss_id>/points', methods=['PUT'])
def update_botw_boss_points(boss_id):
    """Bulk point edit: {"points": {"<challenge_id>": 25, ...}}.

    A boss has 10-40 drops, so editing them one PUT at a time is impractical.
    """
    boss = BotwBoss.query.get(boss_id)
    if not boss:
        return jsonify({'error': 'Boss not found'}), 404

    data = request.get_json()
    if not data or 'points' not in data:
        return jsonify({'error': 'Missing required field: points'}), 400

    points = data['points']
    if not isinstance(points, dict):
        return jsonify({'error': 'points must be an object of challenge_id to value'}), 400

    challenges = Challenge.query.filter(
        Challenge.parent_challenge_id == boss.challenge_id,
        Challenge.id.in_(list(points.keys())),
    ).all() if points else []
    challenges_by_id = {str(c.id): c for c in challenges}

    unknown = [cid for cid in points if cid not in challenges_by_id]
    if unknown:
        return jsonify({'error': f'Challenges do not belong to this boss: {unknown}'}), 400

    for challenge_id, value in points.items():
        if not isinstance(value, int):
            return jsonify({'error': f'Point value for {challenge_id} must be an integer'}), 400
        challenges_by_id[challenge_id].value = value
    db.session.commit()

    return json.dumps(serialize_boss(boss), cls=ModelEncoder), 200


# ---------------------------------------------------------------------------
# Leaderboard
# ---------------------------------------------------------------------------

@app.route('/v2/events/<event_id>/botw/leaderboard', methods=['GET'])
def get_botw_leaderboard(event_id):
    event, err = _require_botw_event(event_id)
    if err:
        return err

    standings = leaderboard(event.id)
    return jsonify({'data': standings, 'total': len(standings)}), 200
