"""Authenticated bot-to-backend interface. Never expose the bot key in a browser.

Discord identity/roles are asserted by the trusted bot, not by website clients.
The backend repeats staff/participant/approval checks on every operation.
"""
from dataclasses import dataclass, asdict
import hmac
import os
import re
from flask import Blueprint, jsonify, request
from services.trial_board_windows import RuleError, parse_windows


def ident(value, label='ID'):
    if type(value) is not int or not 0 < value < 2**63:
        raise RuleError(f'{label} must be a positive integer Discord/database ID.')
    return value


@dataclass(frozen=True)
class Settings:
    guild_id: int
    queue_channel_id: int
    staff_channel_id: int
    staff_role_ids: list[int]
    volunteer_role_ids: list[int]
    shared_pool: bool = True
    offer_limit: int = 3
    trial_days: int = 14

    @classmethod
    def from_env(cls):
        def roles(name):
            return [int(x.strip()) for x in os.environ.get(name, '').split(',') if x.strip()]
        try:
            result = cls(int(os.getenv('TRIAL_BOARD_GUILD_ID', '0')),
                int(os.getenv('TRIAL_BOARD_QUEUE_CHANNEL_ID', '0')),
                int(os.getenv('TRIAL_BOARD_STAFF_CHANNEL_ID', '0')),
                roles('TRIAL_BOARD_STAFF_ROLE_IDS'), roles('TRIAL_BOARD_VOLUNTEER_ROLE_IDS'),
                os.getenv('TRIAL_BOARD_SHARED_POOL', 'true').lower() == 'true',
                int(os.getenv('TRIAL_BOARD_OFFER_LIMIT', '3')), int(os.getenv('TRIAL_BOARD_TRIAL_DAYS', '14')))
            for value in [result.guild_id, result.queue_channel_id, result.staff_channel_id, *result.staff_role_ids, *result.volunteer_role_ids]:
                ident(value)
            if (not result.staff_role_ids or not result.volunteer_role_ids or
                set(result.staff_role_ids) & set(result.volunteer_role_ids) or
                result.queue_channel_id == result.staff_channel_id or
                not 1 <= result.offer_limit <= 5 or not 1 <= result.trial_days <= 30):
                raise ValueError()
            return result
        except (ValueError, RuleError):
            raise RuleError('Set valid backend trial channel, role and scheduling configuration.')


class Controller:
    def __init__(self, service, settings):
        self.s, self.cfg = service, settings

    def run(self, action, data, actor):
        if not isinstance(data, dict):
            raise RuleError('data must be an object.')
        staff = False
        user = None
        if actor is not None:
            if not isinstance(actor, dict) or set(actor) != {'id', 'role_ids'}:
                raise RuleError('Supply the Discord actor and current roles.')
            user = ident(actor['id'])
            roles = actor['role_ids']
            if not isinstance(roles, list) or len(roles) > 250:
                raise RuleError('Invalid actor roles.')
            for role in roles:
                ident(role, 'Role ID')
            staff = bool(set(roles) & set(self.cfg.staff_role_ids))

        def require_staff():
            if not staff:
                raise RuleError('This action is for configured staff roles only.')

        def volunteer():
            v = self.s.volunteer(user)
            if not v or not v['approved'] or not set(actor['role_ids']) & set(self.cfg.volunteer_role_ids):
                raise RuleError('You need staff approval and the volunteer Discord role first.')
            return v

        def number():
            return ident(data.get('number'), 'Trial ID')

        internal = {'bootstrap', 'dispatch', 'ack', 'suspend'}
        if action in internal:
            if actor is not None:
                raise RuleError('This operation is for the Discord transport only.')
            if action == 'bootstrap':
                return {'config': asdict(self.cfg), 'views': self.s.views(), 'paused': self.s.paused()}
            if action == 'suspend':
                self.s.pause(True, 0)
                return None
            worker = data.get('worker', '')
            if not isinstance(worker, str) or not re.fullmatch(r'[A-Za-z0-9-]{1,64}', worker):
                raise RuleError('Invalid worker identity.')
            if action == 'dispatch':
                if not self.s.acquire_worker(worker):
                    return None
                self.s.tick(self.cfg.offer_limit)
                job = self.s.next_job(worker)
                if job is None:
                    return None
                t = self.s.get(job['trial'])
                context = {'job': job, 'trial': t}
                if job['kind'] == 'feedback':
                    import json
                    context['feedback'] = self.s.feedback_record(json.loads(job['data'])['feedback'])
                return context
            job = self.s.job(ident(data.get('delivery'), 'Delivery ID'))
            job['claim_token'] = data.get('claim_token')
            status = data.get('status')
            if status not in ('sent', 'failed', 'uncertain'):
                raise RuleError('Invalid delivery result.')
            message, channel = data.get('message'), data.get('channel')
            if message is not None:
                ident(message, 'Message ID')
            if status == 'sent':
                self.check_destination(job, channel)
                if message is None and job['kind'] != 'offer':
                    raise RuleError('A sent delivery needs its Discord message ID.')
            self.s.finish_job(job, status, message, channel, None if status == 'sent' else 'Discord transport failure')
            return None

        if user is None:
            raise RuleError('A Discord actor is required.')
        if action == 'volunteer':
            return self.s.volunteer(user)
        if action in {'pause', 'resume', 'health', 'approve', 'disable', 'create', 'close', 'job', 'recover'}:
            require_staff()
            if action in ('pause', 'resume'):
                self.s.pause(action == 'pause', user)
            elif action == 'health':
                return {'paused': self.s.paused(), 'issues': self.s.issues()}
            elif action == 'approve':
                self.s.approve(ident(data.get('user')), data.get('board', 'normal'), data.get('capacity', 2), user)
            elif action == 'disable':
                self.s.disable(ident(data.get('user')), user)
            elif action == 'create':
                channel, applicant = ident(data.get('channel')), ident(data.get('applicant'))
                if channel in (self.cfg.queue_channel_id, self.cfg.staff_channel_id):
                    raise RuleError('Choose a separate private application channel.')
                key = data.get('request_id')
                if not isinstance(key, str):
                    raise RuleError('A stable request ID is required.')
                return self.s.create(applicant, channel, data.get('board', 'normal'), data.get('minutes', 60), self.cfg.trial_days, user, external_key=key)
            elif action == 'close':
                self.s.close(number(), user, data.get('outcome'))
            elif action == 'job':
                return self.s.job(ident(data.get('delivery')))
            elif action == 'recover':
                job = self.s.job(ident(data.get('delivery')))
                status = data.get('status')
                if status not in ('pending', 'sent'):
                    raise RuleError('Choose a verified receipt or an explicit retry.')
                if status == 'sent':
                    ident(data.get('message'), 'Message ID')
                    self.check_destination(job, data.get('channel'))
                self.s.finish_job(job, status, data.get('message'), data.get('channel'), reconciliation=True)
            return None
        if action == 'list':
            if not staff:
                volunteer()
            return self.s.list()[:100]
        if action in ('availability', 'away'):
            v = volunteer()
            if action == 'away':
                import json
                self.s.availability(user, json.loads(v['windows']), v['zone'], False)
            else:
                raw, zone = data.get('windows'), data.get('zone')
                if not isinstance(raw, str) or len(raw) > 1000 or not isinstance(zone, str) or len(zone) > 80:
                    raise RuleError('Supply dated availability and an IANA timezone.')
                self.s.availability(user, parse_windows(raw, zone, self.s.now()), zone.strip(), True)
            return None
        t = self.s.get(number())
        if action == 'get':
            if not staff and user not in (t['applicant'], t['owner']):
                volunteer()
            return t
        if action in ('slots', 'propose', 'feedback'):
            volunteer()
            if action == 'slots':
                return self.s.available_slots(t['id'], user)
            if action == 'propose':
                return self.s.propose(t['id'], user, ident(data.get('start')), ident(data.get('revision')))
            self.s.feedback(t['id'], user, data.get('recommendation'), data.get('notes'))
        elif action == 'applicant_availability':
            if data.get('revision') is not None and data['revision'] != t['revision']:
                raise RuleError('This card is old. Open the current trial controls.')
            raw, zone = data.get('windows'), data.get('zone')
            if not isinstance(raw, str) or len(raw) > 1000 or not isinstance(zone, str) or len(zone) > 80:
                raise RuleError('Supply dated availability and an IANA timezone.')
            self.s.applicant_availability(t['id'], user, parse_windows(raw, zone, self.s.now()), zone.strip())
        elif action == 'confirm':
            return self.s.confirm(t['id'], user, ident(data.get('revision')))
        elif action == 'reopen':
            rev = data.get('revision')
            if rev is not None:
                ident(rev)
            self.s.reopen(t['id'], user, staff=staff, revision=rev)
        else:
            raise RuleError('Unknown trial action.')
        return None

    def check_destination(self, job, channel):
        t = self.s.get(job['trial'])
        expected = self.cfg.queue_channel_id if job['kind'] in ('card', 'offer', 'owner') else self.cfg.staff_channel_id if job['kind'] in ('staff', 'feedback') else t['channel']
        if channel != expected:
            raise RuleError('Delivery receipt does not match its configured destination.')


def make_blueprint(service_factory, settings_factory=Settings.from_env):
    bp = Blueprint('trial_board', __name__)

    @bp.post('/trial-board/actions')
    def actions():
        expected = os.environ.get('TRIAL_BOARD_API_KEY', '')
        provided = request.headers.get('X-Trial-Board-Key', '')
        if not expected or not hmac.compare_digest(expected.encode(), provided.encode()):
            return jsonify(error='Invalid trial-board API key'), 401
        if os.getenv('TRIAL_BOARD_ENABLED', 'false').lower() != 'true':
            return jsonify(error='Backend trial coordination is disabled'), 503
        if request.content_length is not None and request.content_length > 32768:
            return jsonify(error='Request too large'), 413
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or set(payload) != {'guild_id', 'action', 'data', 'actor'}:
            return jsonify(error='Supply guild_id, action, data and actor'), 400
        try:
            settings = settings_factory()
            if type(payload['guild_id']) is not int or payload['guild_id'] != settings.guild_id:
                return jsonify(error='Wrong trial server'), 403
            if not isinstance(payload['action'], str):
                raise RuleError('Invalid action.')
            service = service_factory(settings)
            return jsonify(result=Controller(service, settings).run(payload['action'], payload['data'], payload['actor']))
        except RuleError as error:
            return jsonify(error=str(error)), 409
        except Exception:
            # Never expose SQL, notes, actor payloads or keys in logs/errors.
            return jsonify(error='Trial backend unavailable. Check status before retrying.'), 503
    return bp
