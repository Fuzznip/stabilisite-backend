import json
import logging
import queue

from app import app, db
from flask import Response, jsonify, request, stream_with_context
from helper.helpers import ModelEncoder
from models.models import Users
from models.new_events import Action, Challenge, ChallengeProof, ChallengeStatus, Event, EventLog, Region, Team, Territory
from services.conquest_service import sse_clients


def _require_conquest_event(event_id):
    """Return (event, None) or (None, error_response)."""
    event = Event.query.get(event_id)
    if not event:
        return None, (jsonify({'error': 'Event not found'}), 404)
    if event.type != 'conquest':
        return None, (jsonify({'error': 'Event is not a conquest event'}), 400)
    return event, None


# ---------------------------------------------------------------------------
# Regions
# ---------------------------------------------------------------------------

@app.route('/v2/events/<event_id>/regions', methods=['GET'])
def get_conquest_regions(event_id):
    event, err = _require_conquest_event(event_id)
    if err:
        return err

    regions = Region.query.filter_by(event_id=event_id).all()
    return jsonify({'data': [r.serialize() for r in regions]}), 200


@app.route('/v2/events/<event_id>/regions', methods=['POST'])
def create_conquest_region(event_id):
    event, err = _require_conquest_event(event_id)
    if err:
        return err

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON received'}), 400
    if 'name' not in data:
        return jsonify({'error': 'Missing required field: name'}), 400

    region = Region(
        event_id=event_id,
        name=data['name'],
        image_url=data.get('image_url'),
        offset_x=data.get('offset_x'),
        offset_y=data.get('offset_y'),
    )
    db.session.add(region)
    db.session.commit()
    return app.response_class(
        response=json.dumps(region.serialize(), cls=ModelEncoder),
        status=201,
        mimetype='application/json',
    )


# ---------------------------------------------------------------------------
# Territories
# ---------------------------------------------------------------------------

@app.route('/v2/events/<event_id>/territories', methods=['GET'])
def get_conquest_territories(event_id):
    event, err = _require_conquest_event(event_id)
    if err:
        return err

    regions = Region.query.filter_by(event_id=event_id).with_entities(Region.id).all()
    region_ids = [r.id for r in regions]

    territories = Territory.query.filter(
        Territory.region_id.in_(region_ids)
    ).order_by(Territory.display_order).all() if region_ids else []

    return jsonify({'data': [t.serialize() for t in territories]}), 200


@app.route('/v2/regions/<region_id>/territories', methods=['POST'])
def create_conquest_territory(region_id):
    region = Region.query.get(region_id)
    if not region:
        return jsonify({'error': 'Region not found'}), 404

    _, err = _require_conquest_event(str(region.event_id))
    if err:
        return err

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON received'}), 400
    if 'name' not in data:
        return jsonify({'error': 'Missing required field: name'}), 400

    territory = Territory(
        region_id=region_id,
        name=data['name'],
        tier=data.get('tier'),
        challenge_id=data.get('challenge_id'),
        display_order=data.get('display_order'),
        offset_x=data.get('offset_x'),
        offset_y=data.get('offset_y'),
        polygon_points=data.get('polygon_points'),
    )
    db.session.add(territory)
    db.session.commit()
    return app.response_class(
        response=json.dumps(territory.serialize(), cls=ModelEncoder),
        status=201,
        mimetype='application/json',
    )


@app.route('/v2/territories/<territory_id>', methods=['PUT'])
def update_conquest_territory(territory_id):
    territory = Territory.query.get(territory_id)
    if not territory:
        return jsonify({'error': 'Territory not found'}), 404

    region = Region.query.get(territory.region_id)
    _, err = _require_conquest_event(str(region.event_id))
    if err:
        return err

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON received'}), 400

    updatable = ('name', 'tier', 'challenge_id', 'display_order', 'offset_x', 'offset_y', 'polygon_points')
    for field in updatable:
        if field in data:
            setattr(territory, field, data[field])

    db.session.commit()
    return app.response_class(
        response=json.dumps(territory.serialize(), cls=ModelEncoder),
        status=200,
        mimetype='application/json',
    )


@app.route('/v2/territories/<territory_id>/progress', methods=['GET'])
def get_territory_progress(territory_id):
    territory = Territory.query.get(territory_id)
    if not territory:
        return jsonify({'error': 'Territory not found'}), 404

    region = Region.query.get(territory.region_id)
    _, err = _require_conquest_event(str(region.event_id))
    if err:
        return err

    if not territory.challenge_id:
        return jsonify({'data': []}), 200

    challenge = Challenge.query.get(territory.challenge_id)
    teams = Team.query.filter_by(event_id=region.event_id).all()

    statuses_by_team = {
        cs.team_id: cs
        for cs in ChallengeStatus.query.filter_by(challenge_id=territory.challenge_id).all()
    }

    data = []
    for team in teams:
        cs = statuses_by_team.get(team.id)
        quantity = cs.quantity if cs else 0
        data.append({
            'team_id': str(team.id),
            'team_name': team.name,
            'quantity': quantity,
            'required': challenge.quantity,
            'completions': quantity // challenge.quantity,
        })

    return jsonify({'data': data}), 200


@app.route('/v2/territories/<territory_id>/proofs', methods=['GET'])
def get_territory_proofs(territory_id):
    territory = Territory.query.get(territory_id)
    if not territory:
        return jsonify({'error': 'Territory not found'}), 404

    region = Region.query.get(territory.region_id)
    _, err = _require_conquest_event(str(region.event_id))
    if err:
        return err

    if not territory.challenge_id:
        return jsonify({'data': []}), 200

    team_id = request.args.get('team_id')

    query = ChallengeStatus.query.filter_by(challenge_id=territory.challenge_id)
    if team_id:
        query = query.filter_by(team_id=team_id)
    statuses = query.all()

    status_ids = [cs.id for cs in statuses]
    all_proofs = ChallengeProof.query.filter(
        ChallengeProof.challenge_status_id.in_(status_ids)
    ).all() if status_ids else []

    action_ids = [p.action_id for p in all_proofs if p.action_id]
    all_actions = Action.query.filter(Action.id.in_(action_ids)).all() if action_ids else []
    actions_by_id = {a.id: a for a in all_actions}

    player_ids = [a.player_id for a in all_actions if a.player_id]
    all_players = Users.query.filter(Users.id.in_(player_ids)).all() if player_ids else []
    players_by_id = {p.id: p for p in all_players}

    proofs_by_status = {}
    for proof in all_proofs:
        sid = proof.challenge_status_id
        if sid not in proofs_by_status:
            proofs_by_status[sid] = []
        proofs_by_status[sid].append(proof)

    data = []
    for cs in statuses:
        for proof in proofs_by_status.get(cs.id, []):
            proof_dict = {
                'id': str(proof.id),
                'img_path': proof.img_path,
                'created_at': proof.created_at.isoformat(),
                'team_id': str(cs.team_id),
            }
            action = actions_by_id.get(proof.action_id)
            if action:
                proof_dict['action'] = {
                    'id': str(action.id),
                    'name': action.name,
                    'source': action.source,
                    'type': action.type,
                    'quantity': action.quantity,
                    'value': action.value,
                    'date': action.date.isoformat() if action.date else None,
                }
                player = players_by_id.get(action.player_id)
                if player:
                    proof_dict['action']['player'] = {
                        'id': str(player.id),
                        'runescape_name': player.runescape_name,
                    }
            data.append(proof_dict)

    return jsonify({'data': data}), 200


# ---------------------------------------------------------------------------
# Event Logs
# ---------------------------------------------------------------------------

@app.route('/v2/events/<event_id>/event-logs', methods=['GET'])
def get_conquest_event_logs(event_id):
    event, err = _require_conquest_event(event_id)
    if err:
        return err

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)

    pagination = (
        EventLog.query
        .filter_by(event_id=event_id)
        .order_by(EventLog.created_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    return jsonify({
        'data': [log.serialize() for log in pagination.items],
        'total': pagination.total,
        'page': page,
        'per_page': per_page,
    }), 200


# ---------------------------------------------------------------------------
# SSE Scoreboard Stream
# ---------------------------------------------------------------------------

@app.route('/v2/events/<event_id>/scoreboard/stream', methods=['GET'])
def conquest_scoreboard_stream(event_id):
    event, err = _require_conquest_event(event_id)
    if err:
        return err

    def generate():
        q = queue.SimpleQueue()
        event_clients = sse_clients.setdefault(str(event_id), set())
        event_clients.add(q)
        try:
            # Initial snapshot: last 10 log entries, oldest first
            logs = (
                EventLog.query
                .filter_by(event_id=event_id)
                .order_by(EventLog.created_at.desc())
                .limit(10)
                .all()
            )
            logs.reverse()
            if logs:
                payload = json.dumps([log.serialize() for log in logs])
                yield f"data: {payload}\n\n"

            while True:
                try:
                    data = q.get(timeout=30)
                    yield f"data: {data}\n\n"
                except queue.Empty:
                    yield ": ping\n\n"
        except GeneratorExit:
            pass
        finally:
            event_clients.discard(q)

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        },
    )
