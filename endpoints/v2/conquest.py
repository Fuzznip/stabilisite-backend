import json
import logging
import queue

from app import app, db
from flask import Response, jsonify, request, stream_with_context
from sqlalchemy import text
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

    root_id = str(territory.challenge_id)
    root_challenge = Challenge.query.get(territory.challenge_id)
    teams = Team.query.filter_by(event_id=region.event_id).all()

    rows = db.session.execute(text("""
        SELECT
            t.id AS team_id,
            COALESCE(SUM(COALESCE(cs.quantity, 0)), 0) AS total_quantity,
            COALESCE(SUM(FLOOR(COALESCE(cs.quantity, 0)::numeric / leaf.quantity)), 0) AS completions
        FROM new_stability.teams t
        JOIN new_stability.challenges leaf
            ON leaf.trigger_id IS NOT NULL AND (
                leaf.id = :root_id
                OR leaf.parent_challenge_id = :root_id
                OR leaf.parent_challenge_id IN (
                    SELECT id FROM new_stability.challenges
                    WHERE parent_challenge_id = :root_id
                )
            )
        LEFT JOIN new_stability.challenge_statuses cs
            ON cs.challenge_id = leaf.id AND cs.team_id = t.id
        WHERE t.event_id = :event_id
        GROUP BY t.id
    """), {"root_id": root_id, "event_id": str(region.event_id)}).fetchall()

    by_team = {str(r.team_id): r for r in rows}

    data = []
    for team in teams:
        r = by_team.get(str(team.id))
        data.append({
            'team_id': str(team.id),
            'team_name': team.name,
            'quantity': int(r.total_quantity) if r else 0,
            'required': root_challenge.quantity,
            'completions': int(r.completions) if r else 0,
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

    root_id = str(territory.challenge_id)
    leaf_ids = [
        r.id for r in db.session.execute(text("""
            SELECT id FROM new_stability.challenges
            WHERE trigger_id IS NOT NULL AND (
                id = :root_id
                OR parent_challenge_id = :root_id
                OR parent_challenge_id IN (
                    SELECT id FROM new_stability.challenges
                    WHERE parent_challenge_id = :root_id
                )
            )
        """), {"root_id": root_id}).fetchall()
    ]

    query = ChallengeStatus.query.filter(ChallengeStatus.challenge_id.in_(leaf_ids))
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
# Player Actions
# ---------------------------------------------------------------------------

@app.route('/v2/events/<event_id>/player-actions', methods=['GET'])
def get_event_player_actions(event_id):
    event, err = _require_conquest_event(event_id)
    if err:
        return err

    # Start from team_members so players with no drops still appear.
    # LEFT JOIN to action aggregates so they show up with an empty actions list.
    rows = db.session.execute(text("""
        WITH action_agg AS (
            SELECT
                t.id              AS team_id,
                u.runescape_name  AS player_name,
                a.name            AS action_name,
                a.source          AS action_source,
                MAX(tr.img_path)  AS trigger_img,
                SUM(a.quantity)   AS total_quantity
            FROM new_stability.teams t
            JOIN new_stability.challenge_statuses cs  ON cs.team_id = t.id
            JOIN new_stability.challenge_proofs   cp  ON cp.challenge_status_id = cs.id
            JOIN new_stability.actions             a  ON a.id = cp.action_id
            JOIN users                             u  ON u.id = a.player_id
            JOIN new_stability.challenges          ch ON ch.id = cs.challenge_id
            LEFT JOIN new_stability.triggers       tr ON tr.id = ch.trigger_id
            JOIN new_stability.territories        ter ON ter.challenge_id = ch.id
                OR ter.challenge_id IN (
                    SELECT parent_challenge_id FROM new_stability.challenges
                    WHERE id = ch.id AND parent_challenge_id IS NOT NULL
                )
                OR ter.challenge_id IN (
                    SELECT p.parent_challenge_id
                    FROM new_stability.challenges c2
                    JOIN new_stability.challenges p ON p.id = c2.parent_challenge_id
                    WHERE c2.id = ch.id AND p.parent_challenge_id IS NOT NULL
                )
            JOIN new_stability.regions              r ON r.id = ter.region_id
            WHERE t.event_id = :event_id
              AND r.event_id = :event_id
            GROUP BY t.id, u.runescape_name, a.name, a.source
        )
        SELECT
            tm.team_id,
            u.runescape_name  AS player_name,
            aa.action_name,
            aa.action_source,
            aa.trigger_img,
            aa.total_quantity
        FROM new_stability.team_members tm
        JOIN new_stability.teams t ON t.id = tm.team_id
        JOIN users u ON u.id = tm.user_id
        LEFT JOIN action_agg aa
               ON aa.team_id = tm.team_id
              AND aa.player_name = u.runescape_name
        WHERE t.event_id = :event_id
        ORDER BY u.runescape_name, aa.total_quantity DESC NULLS LAST
    """), {'event_id': event_id}).fetchall()

    teams = Team.query.filter_by(event_id=event_id).all()

    team_player_actions: dict = {}
    for row in rows:
        tid = str(row.team_id)
        team_player_actions.setdefault(tid, {})
        # Ensure the player key exists even if they have no actions
        if row.player_name not in team_player_actions[tid]:
            team_player_actions[tid][row.player_name] = []
        if row.action_name is not None:
            team_player_actions[tid][row.player_name].append({
                'name': row.action_name,
                'source': row.action_source,
                'img_path': row.trigger_img,
                'quantity': int(row.total_quantity),
            })

    data = []
    for team in teams:
        tid = str(team.id)
        players_raw = team_player_actions.get(tid, {})
        players_list = sorted([
            {'player_name': pname, 'actions': actions}
            for pname, actions in players_raw.items()
        ], key=lambda p: p['player_name'])
        data.append({
            'team_id': tid,
            'team_name': team.name,
            'team_color': team.color,
            'team_image_url': team.image_url,
            'players': players_list,
        })

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
