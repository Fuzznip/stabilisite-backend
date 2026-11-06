"""Trial workflow, HTTP authorization and PostgreSQL concurrency regression tests."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import threading
import unittest
from unittest.mock import patch
import uuid
from flask import Flask
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from models.trial_board import metadata, state, jobs as J, trials as T
from services.trial_board import TrialBoard
from services.trial_board_api import Settings, make_blueprint
from services.trial_board_windows import RuleError, parse_windows


def database_url():
    direct = os.getenv('TRIAL_BOARD_TEST_DATABASE_URL')
    url = sa.make_url(direct) if direct else sa.URL.create('postgresql+psycopg2', username=os.getenv('DATABASE_USERNAME', 'stability'),
        password=os.getenv('DATABASE_PASSWORD', 'stabilisite'), host='127.0.0.1', port=5432,
        database='stability_test')
    if not (url.database or '').endswith('_test'):
        raise RuntimeError('Trial-board tests require a database ending in _test')
    return url


class TrialBoardTests(unittest.TestCase):
    def setUp(self):
        self.schema = 'trial_test_' + uuid.uuid4().hex
        self.base = sa.create_engine(database_url())
        with self.base.begin() as c:
            c.execute(sa.schema.CreateSchema(self.schema))
        self.engine = self.base.execution_options(schema_translate_map={'new_stability': self.schema})
        metadata.create_all(self.engine)
        with self.engine.begin() as c:
            c.execute(state.insert().values(id=1, paused=True))
        self.now = int(datetime(2026, 11, 6, 12, tzinfo=timezone.utc).timestamp())
        self.s = TrialBoard(self.engine, clock=lambda: self.now)
        self.cfg = Settings(1, 100, 200, [300], [400])
        self.flask = Flask(__name__)
        self.flask.register_blueprint(make_blueprint(lambda cfg: self.s, lambda: self.cfg))
        self.client = self.flask.test_client()
        self.env = patch.dict(os.environ, {'TRIAL_BOARD_ENABLED': 'true', 'TRIAL_BOARD_API_KEY': 'test-only-key'})
        self.env.start()
        self.staff = {'id': 99, 'role_ids': [300]}
        self.user = {'id': 1, 'role_ids': []}
        self.voucher = {'id': 10, 'role_ids': [400]}
        self.start = ((self.now + 2 * 86400 + 899) // 900) * 900
        self.windows = [[self.start, self.start + 4 * 3600]]
        self.raw = '\n'.join(datetime.fromtimestamp(s, timezone.utc).strftime('%Y-%m-%d %H:%M') + ' / ' +
                            datetime.fromtimestamp(e, timezone.utc).strftime('%Y-%m-%d %H:%M') for s, e in self.windows)

    def tearDown(self):
        self.env.stop()
        with self.base.begin() as c:
            c.execute(sa.schema.DropSchema(self.schema, cascade=True))
        self.base.dispose()

    def call(self, action, actor=None, **data):
        return self.client.post('/trial-board/actions', headers={'X-Trial-Board-Key': 'test-only-key'},
            json={'guild_id': 1, 'action': action, 'data': data, 'actor': actor})

    def result(self, action, actor=None, **data):
        response = self.call(action, actor, **data)
        self.assertEqual(response.status_code, 200, response.json)
        return response.json['result']

    def ready(self):
        self.s.pause(False, 99)
        for user in (10, 11):
            self.s.approve(user, 'normal', 2, 99)
            self.s.availability(user, self.windows, 'UTC', True)

    def trial(self, user=1):
        t = self.s.create(user, 150 + user, 'normal', 60, 14, 99)
        self.s.applicant_availability(t['id'], user, self.windows, 'UTC')
        return self.s.get(t['id'])

    def booked(self):
        t = self.trial()
        t = self.s.propose(t['id'], 10, self.start, t['revision'])
        return self.s.confirm(t['id'], 1, t['revision'])

    def test_end_to_end_via_http_no_automatic_membership_changes(self):
        self.result('resume', self.staff)
        self.result('approve', self.staff, user=10)
        self.result('availability', self.voucher, windows=self.raw, zone='UTC')
        t = self.result('create', self.staff, applicant=1, channel=151, request_id='app:123')
        self.result('applicant_availability', self.user, number=t['id'], windows=self.raw, zone='UTC', revision=t['revision'])
        t = self.result('get', self.user, number=t['id'])
        slots = self.result('slots', self.voucher, number=t['id'])
        t = self.result('propose', self.voucher, number=t['id'], start=slots[0][0], revision=t['revision'])
        self.result('confirm', self.user, number=t['id'], revision=t['revision'])
        self.now = slots[0][1]
        self.result('feedback', self.voucher, number=t['id'], recommendation='recommend', notes='Listened and participated well.')
        self.result('close', self.staff, number=t['id'], outcome='accepted')
        self.assertEqual(self.s.get(t['id'])['outcome'], 'accepted')
        self.assertFalse(any('users' in name and 'trial_board' not in name for name in metadata.tables))

    def test_disabled_or_missing_dedicated_key_fails_closed(self):
        os.environ.pop('TRIAL_BOARD_API_KEY')
        self.assertEqual(self.call('bootstrap').status_code, 401)
        os.environ['TRIAL_BOARD_API_KEY'] = 'test-only-key'
        os.environ['TRIAL_BOARD_ENABLED'] = 'false'
        self.assertEqual(self.call('bootstrap').status_code, 503)

    def test_wrong_guild_bad_actor_and_bool_ids_rejected(self):
        payload = dict(guild_id=2, action='bootstrap', data={}, actor=None)
        self.assertEqual(self.client.post('/trial-board/actions', json=payload, headers={'X-Trial-Board-Key': 'test-only-key'}).status_code, 403)
        self.assertEqual(self.call('health', {'id': True, 'role_ids': [300]}).status_code, 409)
        self.assertEqual(self.call('health', self.user).status_code, 409)
        self.assertEqual(self.call('dispatch', self.user, worker='test').status_code, 409)

    def test_pause_default_and_readonly_status(self):
        self.assertTrue(self.result('health', self.staff)['paused'])
        self.assertEqual(self.call('create', self.staff, applicant=1, channel=151, request_id='a').status_code, 409)
        self.assertIsNone(self.result('dispatch', worker='test'))

    def test_approval_and_role_do_not_implicitly_opt_in(self):
        self.s.approve(10, 'normal', 2, 99)
        self.assertFalse(self.s.volunteer(10)['active'])
        self.assertEqual(self.call('availability', {'id': 10, 'role_ids': []}, windows=self.raw, zone='UTC').status_code, 409)
        self.assertEqual(self.call('availability', {'id': 11, 'role_ids': [400]}, windows=self.raw, zone='UTC').status_code, 409)

    def test_nonparticipants_cannot_confirm_reschedule_or_read_trials(self):
        self.ready()
        t = self.trial()
        stranger = {'id': 123, 'role_ids': []}
        for action in ('get', 'confirm', 'reopen'):
            self.assertEqual(self.call(action, stranger, number=t['id'], revision=t['revision']).status_code, 409)

    def test_stale_card_cannot_replace_applicant_availability(self):
        self.ready()
        t = self.trial()
        self.assertEqual(self.call('applicant_availability', self.user, number=t['id'], revision=1, windows=self.raw, zone='UTC').status_code, 409)

    def test_request_id_replays_even_after_close_or_pause(self):
        self.ready()
        t = self.s.create(1, 151, 'normal', 60, 14, 99, 'app:123')
        self.s.close(t['id'], 99, 'withdrawn')
        self.s.pause(True, 99)
        replay = self.s.create(1, 151, 'normal', 60, 14, 99, 'app:123')
        self.assertEqual(replay['id'], t['id'])
        self.assertTrue(replay['replayed'])
        with self.assertRaises(RuleError):
            self.s.create(2, 151, 'normal', 60, 14, 99, 'app:123')

    def test_concurrent_start_requests_create_one_trial(self):
        self.ready()
        barrier = threading.Barrier(2)
        def start(_):
            barrier.wait()
            return self.s.create(1, 151, 'normal', 60, 14, 99, 'app:123')
        with ThreadPoolExecutor(2) as pool:
            rows = list(pool.map(start, range(2)))
        self.assertEqual(len({t['id'] for t in rows}), 1)
        self.assertEqual(sorted(t['replayed'] for t in rows), [False, True])

    def test_concurrent_vouchers_can_only_claim_once(self):
        self.ready()
        t = self.trial()
        barrier = threading.Barrier(2)
        def propose(user):
            barrier.wait()
            try:
                self.s.propose(t['id'], user, self.start, t['revision'])
                return 'claimed'
            except RuleError:
                return 'changed'
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(propose, [10, 11]))
        self.assertEqual(sorted(results), ['changed', 'claimed'])

    def test_capacity_and_cross_trial_overlap_are_serialized(self):
        self.ready()
        self.s.approve(10, 'normal', 1, 99)
        a, b = self.trial(1), self.trial(2)
        self.s.propose(a['id'], 10, self.start, a['revision'])
        self.assertEqual(self.s.available_slots(b['id'], 10), [])
        self.s.approve(10, 'normal', 2, 99)
        self.assertTrue(all(s >= self.start + 3600 for s, e in self.s.available_slots(b['id'], 10)))

    def test_shared_pool_then_future_split(self):
        self.ready()
        t = self.s.create(1, 151, 'efficient', 60, 14, 99)
        self.s.applicant_availability(t['id'], 1, self.windows, 'UTC')
        self.assertTrue(self.s.available_slots(t['id'], 10))
        split = TrialBoard(self.engine, clock=lambda: self.now, shared_pool=False)
        self.assertEqual(split.available_slots(t['id'], 10), [])

    def test_proposal_expires_and_reminders_are_deduplicated(self):
        self.ready()
        t = self.trial()
        t = self.s.propose(t['id'], 10, self.start, t['revision'])
        self.now = t['proposal_expires'] + 1
        self.s.tick()
        self.assertEqual(self.s.get(t['id'])['status'], 'open')
        self.now = int(datetime(2026, 11, 6, 12, tzinfo=timezone.utc).timestamp())
        self.s.close(t['id'], 99, 'withdrawn')
        t = self.booked()
        self.now = t['start'] - 100
        self.s.tick()
        self.s.tick()
        with self.engine.connect() as c:
            rows = list(c.execute(sa.select(J).where(J.c.trial == t['id'], J.c.kind == 'reminder')).mappings())
        self.assertEqual(len(rows), 1)

    def test_feedback_owner_and_start_time_checked_on_backend(self):
        self.ready()
        t = self.booked()
        with self.assertRaises(RuleError):
            self.s.feedback(t['id'], 10, 'recommend', 'Too early.')
        self.now = self.start + 1
        with self.assertRaises(RuleError):
            self.s.feedback(t['id'], 11, 'recommend', 'Not the owner.')
        self.s.feedback(t['id'], 10, 'concern', 'A private staff-only note.')
        with self.assertRaises(RuleError):
            self.s.feedback(t['id'], 10, 'concern', 'A duplicate note.')
        self.assertNotIn('notes', json.dumps(self.result('get', self.user, number=t['id'])))

    def test_durable_button_rehydration_after_backend_restart(self):
        self.ready()
        t = self.trial()
        self.s.acquire_worker('one')
        while job := self.s.next_job('one'):
            self.s.finish_job(job, 'sent', job['id'] + 1000, 100 if job['kind'] == 'card' else 151)
        restarted = TrialBoard(self.engine)
        self.assertTrue(any(v['trial'] == t['id'] and v['kind'] == 'card' for v in restarted.views()))

    def test_worker_takeover_does_not_resend_ambiguous_message(self):
        self.ready()
        self.trial()
        self.assertTrue(self.s.acquire_worker('one'))
        job = self.s.next_job('one')
        self.assertFalse(self.s.acquire_worker('two'))
        self.now += 301
        self.assertTrue(self.s.acquire_worker('two'))
        self.assertEqual(self.s.job(job['id'])['status'], 'uncertain')
        self.assertIsNone(self.s.next_job('two'))
        with self.assertRaises(RuleError):
            self.s.finish_job(job, 'sent', 999, 100)

    def test_lost_claim_response_expires_even_if_same_worker_stays_alive(self):
        self.ready()
        self.trial()
        self.s.acquire_worker('one')
        job = self.s.next_job('one')
        self.now += 241
        self.s.acquire_worker('one')
        self.s.tick()
        self.assertEqual(self.s.job(job['id'])['status'], 'uncertain')
        self.assertIsNone(self.s.next_job('one'))

    def test_receipt_retry_is_idempotent_and_wrong_destination_rejected(self):
        self.ready()
        self.trial()
        context = self.result('dispatch', worker='one')
        job = context['job']
        self.assertEqual(self.call('ack', worker='one', delivery=job['id'], claim_token=job['claim_token'], status='sent', message=999, channel=200).status_code, 409)
        for _ in range(2):
            self.result('ack', worker='one', delivery=job['id'], claim_token=job['claim_token'], status='sent', message=999, channel=100)
        self.assertEqual(self.s.get(job['trial'])['card'], 999)

    def test_reconciliation_requires_staff_and_matching_destination(self):
        self.ready()
        self.trial()
        context = self.result('dispatch', worker='one')
        job = context['job']
        self.result('ack', worker='one', delivery=job['id'], claim_token=job['claim_token'], status='uncertain')
        self.assertEqual(self.call('recover', self.user, delivery=job['id'], status='pending').status_code, 409)
        self.assertEqual(self.call('recover', self.staff, delivery=job['id'], status='sent', message=999, channel=200).status_code, 409)
        self.result('recover', self.staff, delivery=job['id'], status='sent', message=999, channel=100)
        self.assertEqual(self.s.issues(), [])

    def test_migration_upgrade_downgrade_round_trip(self):
        metadata.drop_all(self.engine)
        path = Path(__file__).resolve().parents[1] / 'migrations/versions/022_add_trial_board.py'
        spec = importlib.util.spec_from_file_location('trial_migration', path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        with self.engine.begin() as c:
            with Operations.context(MigrationContext.configure(c)):
                migration.upgrade()
            self.assertTrue(c.execute(sa.select(state.c.paused)).scalar_one())
            with Operations.context(MigrationContext.configure(c)):
                migration.downgrade()
        self.assertNotIn('trial_board_state', sa.inspect(self.base).get_table_names(schema=self.schema))

    def test_dst_gaps_and_ambiguous_times_rejected(self):
        before = int(datetime(2026, 10, 25, tzinfo=timezone.utc).timestamp())
        with self.assertRaises(RuleError):
            parse_windows('2026-11-01 01:10 / 2026-11-01 02:10', 'America/New_York', before)
        with self.assertRaises(RuleError):
            parse_windows(self.raw, 'Not/AZone', self.now)


if __name__ == '__main__':
    unittest.main()
