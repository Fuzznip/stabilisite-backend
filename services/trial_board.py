"""Trial rules and durable outbox, using the backend's PostgreSQL engine.

Every write locks one state row. This serializes claims/overlap/capacity checks
across backend processes, rather than relying on a bot's in-memory lock.
"""
from contextlib import contextmanager
import json
import re
import time
import uuid
import sqlalchemy as sa
from models.trial_board import state, volunteers as V, trials as T, feedback as F, jobs as J, audit as A, requests as R
from services.trial_board_windows import RuleError, parse_windows


class TrialBoard:
    def __init__(self, engine, clock=time.time, shared_pool=True):
        self.engine, self.clock, self.shared_pool = engine, clock, shared_pool

    def now(self):
        return int(self.clock())

    @contextmanager
    def tx(self):
        with self.engine.begin() as c:
            settings = c.execute(sa.select(state).where(state.c.id == 1).with_for_update()).mappings().first()
            if not settings:
                raise RuleError('Trial tables are not initialized. Apply the backend migration.')
            yield c

    @staticmethod
    def one(c, table, condition, required=True):
        row = c.execute(sa.select(table).where(condition)).mappings().first()
        if row is None and required:
            raise RuleError('Trial, volunteer or delivery not found.')
        return dict(row) if row else None

    def row(self, c, trial):
        return self.one(c, T, T.c.id == trial)

    def audit(self, c, actor, action, trial=None):
        c.execute(A.insert().values(actor=actor, action=action, trial=trial, created=self.now()))

    def require_running(self, c):
        if c.execute(sa.select(state.c.paused).where(state.c.id == 1)).scalar_one():
            raise RuleError('Trial workflow is paused. Ask staff to review /board status.')

    def paused(self):
        with self.engine.connect() as c:
            return c.execute(sa.select(state.c.paused).where(state.c.id == 1)).scalar_one()

    def pause(self, value, actor):
        with self.tx() as c:
            c.execute(state.update().where(state.c.id == 1).values(paused=value))
            self.audit(c, actor, 'pause' if value else 'resume')

    def volunteer(self, user):
        with self.engine.connect() as c:
            return self.one(c, V, V.c.user_id == user, False)

    def approve(self, user, board, capacity, actor):
        if board not in ('normal', 'efficient') or type(capacity) is not int or not 1 <= capacity <= 5:
            raise RuleError('Choose normal/efficient and a capacity of 1–5.')
        with self.tx() as c:
            values = dict(board=board, capacity=capacity, approved=True)
            if self.one(c, V, V.c.user_id == user, False):
                c.execute(V.update().where(V.c.user_id == user).values(**values))
            else:
                c.execute(V.insert().values(user_id=user, **values))
            self.audit(c, actor, 'approve_volunteer')

    def disable(self, user, actor):
        with self.tx() as c:
            c.execute(V.update().where(V.c.user_id == user).values(approved=False, active=False))
            self.audit(c, actor, 'disable_volunteer')

    def availability(self, user, windows, zone, active):
        with self.tx() as c:
            v = self.one(c, V, V.c.user_id == user)
            if not v['approved']:
                raise RuleError('Staff must approve you for the volunteer pool first.')
            c.execute(V.update().where(V.c.user_id == user).values(windows=json.dumps(windows), zone=zone, active=active))
            self.audit(c, user, 'volunteer_availability')

    def enqueue(self, c, t, kind, data=None, suffix=''):
        key = f"{t['id']}:{t['revision']}:{kind}:{suffix}"
        if c.execute(sa.select(J.c.id).where(J.c.dedupe == key)).first() is None:
            c.execute(J.insert().values(dedupe=key, trial=t['id'], revision=t['revision'],
                                      kind=kind, data=json.dumps(data or {}), created=self.now()))

    def get(self, trial):
        with self.engine.connect() as c:
            return self.row(c, trial)

    def list(self, active=True):
        with self.engine.connect() as c:
            query = sa.select(T).order_by(T.c.id.desc())
            if active:
                query = query.where(T.c.status.not_in(['closed', 'cancelled']))
            return [dict(r) for r in c.execute(query).mappings()]

    def changed(self, c, trial):
        c.execute(T.update().where(T.c.id == trial).values(revision=T.c.revision + 1))
        t = self.row(c, trial)
        self.enqueue(c, t, 'card')
        return t

    def create(self, applicant, channel, board, duration, days, actor, external_key=None):
        if board not in ('normal', 'efficient') or type(duration) is not int or not 30 <= duration <= 240 or not 1 <= days <= 30:
            raise RuleError('Use normal/efficient, 30–240 minutes, and a 1–30 day trial window.')
        with self.tx() as c:
            if external_key is not None:
                if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}', external_key):
                    raise RuleError('Use a stable request ID (1–100 simple characters).')
                previous = self.one(c, R, R.c.request_key == external_key, False)
                if previous:
                    if (previous['applicant'], previous['channel'], previous['board'], previous['duration']) != (applicant, channel, board, duration):
                        raise RuleError('This request ID was already used with different details.')
                    return dict(self.row(c, previous['trial']), replayed=True)
            self.require_running(c)
            existing = c.execute(sa.select(T.c.id).where(T.c.applicant == applicant, T.c.status.not_in(['closed', 'cancelled']))).first()
            if existing:
                raise RuleError('This applicant already has an open trial. Use /trial status.')
            ident = c.execute(T.insert().values(applicant=applicant, channel=channel, board=board,
                duration=duration * 60, created=self.now(), deadline=self.now() + days * 86400).returning(T.c.id)).scalar_one()
            t = self.row(c, ident)
            if external_key:
                c.execute(R.insert().values(request_key=external_key, applicant=applicant, channel=channel,
                                           board=board, duration=duration, trial=ident))
            self.enqueue(c, t, 'card')
            self.enqueue(c, t, 'application', {'event': 'availability'})
            self.audit(c, actor, 'start', ident)
            return dict(t, replayed=False)

    def applicant_availability(self, trial, user, windows, zone):
        with self.tx() as c:
            self.require_running(c)
            t = self.row(c, trial)
            if user != t['applicant'] or t['status'] not in ('availability', 'open'):
                raise RuleError('Only this applicant can edit availability on an unbooked trial.')
            if not windows or any(e - s < t['duration'] or e > t['deadline'] for s, e in windows):
                raise RuleError('Each window must fit the session and end before your trial deadline.')
            c.execute(T.update().where(T.c.id == trial).values(windows=json.dumps(windows), zone=zone, status='open'))
            self.changed(c, trial)
            self.audit(c, user, 'applicant_availability', trial)

    def load(self, c, user):
        return c.execute(sa.select(sa.func.count()).select_from(T).where(T.c.owner == user, T.c.status.in_(['proposed', 'booked', 'review']))).scalar_one()

    def slots(self, c, t, user):
        v = self.one(c, V, V.c.user_id == user, False)
        if not v or not v['approved'] or not v['active'] or user == t['applicant'] or self.load(c, user) >= v['capacity']:
            return []
        if not self.shared_pool and t['board'] == 'efficient' and v['board'] != 'efficient':
            return []
        conflicts = c.execute(sa.select(T.c.start, T.c.end).where(T.c.status.in_(['proposed', 'booked']),
            sa.or_(T.c.owner.in_([user, t['applicant']]), T.c.applicant.in_([user, t['applicant']])), T.c.id != t['id'])).all()
        result = set()
        for a, b in json.loads(t['windows']):
            for x, y in json.loads(v['windows']):
                start, end = max(a, x, self.now() + 300), min(b, y, t['deadline'])
                start = ((start + 899) // 900) * 900
                while start + t['duration'] <= end:
                    finish = start + t['duration']
                    if not any(start < r.end and finish > r.start for r in conflicts):
                        result.add((start, finish))
                    start += 1800
        return sorted(result)[:25]

    def available_slots(self, trial, user):
        with self.engine.connect() as c:
            t = self.row(c, trial)
            return self.slots(c, t, user) if t['status'] == 'open' else []

    def propose(self, trial, user, start, revision):
        with self.tx() as c:
            self.require_running(c)
            t = self.row(c, trial)
            if t['status'] != 'open' or t['revision'] != revision:
                raise RuleError('This trial changed. Open its latest card and choose again.')
            chosen = next((s for s in self.slots(c, t, user) if s[0] == start), None)
            if not chosen:
                raise RuleError('That slot is no longer available. Refresh the trial card.')
            c.execute(T.update().where(T.c.id == trial).values(owner=user, start=chosen[0], end=chosen[1],
                proposal_expires=min(self.now() + 86400, start - 300), status='proposed'))
            t = self.changed(c, trial)
            self.enqueue(c, t, 'application', {'event': 'confirm'})
            self.enqueue(c, t, 'owner', {'event': 'waiting'})
            self.audit(c, user, 'propose', trial)
            return t

    def confirm(self, trial, user, revision):
        with self.tx() as c:
            self.require_running(c)
            t = self.row(c, trial)
            if user != t['applicant'] or t['status'] != 'proposed' or revision != t['revision']:
                raise RuleError('Only the applicant can confirm the current proposal.')
            v = self.one(c, V, V.c.user_id == t['owner'], False)
            if not v or not v['approved'] or not v['active'] or t['proposal_expires'] <= self.now():
                raise RuleError('The proposal expired or the volunteer is unavailable. Ask staff to reopen it.')
            c.execute(T.update().where(T.c.id == trial).values(status='booked'))
            t = self.changed(c, trial)
            self.enqueue(c, t, 'application', {'event': 'booked'})
            self.enqueue(c, t, 'owner', {'event': 'booked'})
            self.audit(c, user, 'confirm', trial)
            return t

    def reopen(self, trial, user, staff=False, revision=None):
        with self.tx() as c:
            self.require_running(c)
            t = self.row(c, trial)
            if not staff and user not in (t['applicant'], t['owner']):
                raise RuleError('Only the applicant, assigned volunteer or staff can reschedule.')
            if t['status'] in ('closed', 'cancelled') or (revision is not None and revision != t['revision']):
                raise RuleError('This trial changed or is closed. Refresh its status.')
            previous = t['owner']
            c.execute(T.update().where(T.c.id == trial).values(owner=None, start=None, end=None,
                proposal_expires=None, status='availability', windows='[]'))
            t = self.changed(c, trial)
            self.enqueue(c, t, 'application', {'event': 'availability'})
            if previous:
                self.enqueue(c, t, 'owner', {'event': 'rescheduled', 'user': previous})
            self.audit(c, user, 'reopen', trial)

    def feedback(self, trial, user, recommendation, notes):
        if recommendation not in ('recommend', 'more_time', 'concern') or not isinstance(notes, str) or not 5 <= len(notes.strip()) <= 1800:
            raise RuleError('Choose recommend/more_time/concern and write 5–1800 characters.')
        with self.tx() as c:
            self.require_running(c)
            t = self.row(c, trial)
            v = self.one(c, V, V.c.user_id == user, False)
            if user != t['owner'] or not v or not v['approved'] or t['status'] not in ('booked', 'review') or self.now() < t['start']:
                raise RuleError('Only the approved assigned volunteer can submit feedback after the session starts.')
            if c.execute(sa.select(F.c.id).where(F.c.trial == trial, F.c.author == user)).first():
                raise RuleError('Feedback already submitted. Ask staff if a correction is needed.')
            ident = c.execute(F.insert().values(trial=trial, author=user, recommendation=recommendation,
                notes=notes.strip(), created=self.now()).returning(F.c.id)).scalar_one()
            c.execute(T.update().where(T.c.id == trial).values(status='review'))
            t = self.changed(c, trial)
            self.enqueue(c, t, 'feedback', {'feedback': ident})
            self.audit(c, user, 'feedback', trial)

    def close(self, trial, actor, outcome):
        if outcome not in ('accepted', 'declined', 'withdrawn'):
            raise RuleError('Choose accepted, declined or withdrawn.')
        with self.tx() as c:
            self.require_running(c)
            t = self.row(c, trial)
            if t['status'] in ('closed', 'cancelled'):
                raise RuleError('Trial is already closed.')
            c.execute(T.update().where(T.c.id == trial).values(status='closed', outcome=outcome))
            t = self.changed(c, trial)
            self.enqueue(c, t, 'staff', {'event': 'closed'})
            self.audit(c, actor, 'close:' + outcome, trial)

    def tick(self, offer_limit=3):
        with self.tx() as c:
            if c.execute(sa.select(state.c.paused).where(state.c.id == 1)).scalar_one():
                return
            now = self.now()
            c.execute(J.update().where(J.c.status == 'sending', J.c.claimed_at < now - 240).values(
                status='uncertain', error='Delivery lease expired; inspect Discord before retrying'))
            for row in c.execute(sa.select(T).where(T.c.status.not_in(['closed', 'cancelled']))).mappings().all():
                t = dict(row)
                if t['status'] == 'proposed' and t['proposal_expires'] <= now:
                    c.execute(T.update().where(T.c.id == t['id']).values(status='open', owner=None, start=None, end=None, proposal_expires=None))
                    t = self.changed(c, t['id'])
                    self.enqueue(c, t, 'application', {'event': 'expired'})
                if now >= t['deadline']:
                    self.enqueue(c, t, 'staff', {'event': 'deadline'})
                    continue
                if t['status'] == 'open':
                    eligible = [(self.load(c, v['user_id']), v['offered'], v['user_id'])
                        for v in c.execute(sa.select(V).where(V.c.approved, V.c.active)).mappings().all()
                        if self.slots(c, t, v['user_id'])]
                    users = [v[2] for v in sorted(eligible)[:offer_limit]]
                    if users:
                        self.enqueue(c, t, 'offer', {'users': users})
                    if now - t['created'] >= 86400:
                        self.enqueue(c, t, 'staff', {'event': 'unclaimed'})
                if t['status'] == 'availability' and now - t['created'] >= 86400:
                    self.enqueue(c, t, 'staff', {'event': 'availability_missing'})
                if t['status'] == 'booked':
                    for label, before in [('day', 86400), ('hour', 3600)]:
                        upper = t['start'] - 3600 if label == 'day' else t['start']
                        if t['start'] - before <= now < upper:
                            self.enqueue(c, t, 'reminder', {'event': label}, label)
                            self.enqueue(c, t, 'owner', {'event': 'reminder'}, label)
                    if now >= t['end'] + 3600:
                        self.enqueue(c, t, 'staff', {'event': 'feedback_due'})

    def acquire_worker(self, owner):
        with self.tx() as c:
            current = c.execute(sa.select(state).where(state.c.id == 1)).mappings().one()
            if current['worker'] != owner and (current['expires'] or 0) > self.now():
                return False
            if current['worker'] != owner:
                c.execute(J.update().where(J.c.status == 'sending').values(status='uncertain', error='Worker stopped during delivery'))
            c.execute(state.update().where(state.c.id == 1).values(worker=owner, expires=self.now() + 300))
            return True

    def next_job(self, worker):
        with self.tx() as c:
            current = c.execute(sa.select(state).where(state.c.id == 1)).mappings().one()
            if current['paused'] or current['worker'] != worker or (current['expires'] or 0) <= self.now():
                return None
            blocked = sa.select(J.c.trial).where(J.c.status.in_(['sending', 'uncertain', 'failed']))
            for row in c.execute(sa.select(J).where(J.c.status == 'pending', J.c.trial.not_in(blocked)).order_by(J.c.id)).mappings().all():
                job = dict(row)
                t, data = self.row(c, job['trial']), json.loads(job['data'])
                reminder = job['kind'] == 'reminder' or (job['kind'] == 'owner' and data.get('event') == 'reminder')
                if ((job['kind'] != 'feedback' and job['revision'] != t['revision']) or
                    (reminder and (not t['start'] or self.now() >= t['start'])) or
                    (job['kind'] in ('offer', 'application') and self.now() >= t['deadline'])):
                    c.execute(J.update().where(J.c.id == job['id']).values(status='cancelled'))
                    continue
                token = str(uuid.uuid4())
                c.execute(J.update().where(J.c.id == job['id']).values(status='sending', claim_token=token, claimed_at=self.now()))
                return dict(job, claim_token=token)
            return None

    def finish_job(self, job, status, message=None, channel=None, error=None, reconciliation=False):
        if status not in ('sent', 'failed', 'uncertain', 'pending'):
            raise RuleError('Invalid delivery result.')
        with self.tx() as c:
            current = self.one(c, J, J.c.id == job['id'])
            if reconciliation:
                if current['status'] not in ('failed', 'uncertain') or status not in ('pending', 'sent'):
                    raise RuleError('Only unresolved deliveries can be reconciled.')
            elif current['status'] != 'sending' or not job.get('claim_token') or job['claim_token'] != current['claim_token']:
                # Idempotent acknowledgement after a lost HTTP response.
                if current['status'] == status and current['message'] == message and current['channel'] == channel and job.get('claim_token') == current['claim_token']:
                    return
                raise RuleError('Delivery claim expired or changed. Inspect current status.')
            c.execute(J.update().where(J.c.id == job['id']).values(status=status, message=message, channel=channel, error=error))
            if status == 'sent' and current['kind'] == 'card':
                c.execute(T.update().where(T.c.id == current['trial']).values(card=message))
            if status == 'sent' and current['kind'] == 'offer':
                c.execute(V.update().where(V.c.user_id.in_(json.loads(current['data'])['users'])).values(offered=self.now()))

    def job(self, ident):
        with self.engine.connect() as c:
            return self.one(c, J, J.c.id == ident)

    def issues(self):
        with self.engine.connect() as c:
            return [dict(r) for r in c.execute(sa.select(J.c.id, J.c.trial, J.c.kind, J.c.status).where(J.c.status.in_(['uncertain', 'failed'])).order_by(J.c.id)).mappings()]

    def feedback_record(self, ident):
        with self.engine.connect() as c:
            return self.one(c, F, F.c.id == ident)

    def views(self):
        with self.engine.connect() as c:
            return [dict(r) for r in c.execute(sa.select(J.c.trial, J.c.revision, J.c.kind).distinct().where(J.c.status == 'sent', J.c.kind.in_(['card', 'application']))).mappings()]
