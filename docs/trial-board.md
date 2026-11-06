# Backend-owned trial board

Paired change: `Fuzznip/stabilibot` PR #29. The backend owns all trial state and
coordination in PostgreSQL; the bot only supplies Discord UI, verifies actual
Discord permissions, renders/delivers messages and reports receipts.

## Database and activation

Apply migration `022_add_trial_board` (revision `d9e0f1a2b3c4`) after the existing
`c8d9e0f1a2b3` migration. It creates seven `new_stability.trial_board_*` tables for
state/worker lease, volunteers, trials, feedback, outbox, audit and request IDs.
Existing clan/application tables are unchanged. The state row starts paused.
Downgrade removes only the new tables and their trial records, so back up before
using downgrade after any real trial activity.

Configure `.example.env`'s new trial settings privately. Leave
`TRIAL_BOARD_ENABLED=false` until a concrete private test is approved. The backend
owns guild/channel/role IDs, shared routing, offer count and planning days. The bot
must have matching ID configuration and is independently disabled by default.
Use separate private queue and staff feedback channels; never expose staff feedback
to the volunteer role. A person can hold both staff and volunteer roles, but the
configured role ID lists themselves must be disjoint.

The existing `API_KEYS` middleware still applies. In addition, trial endpoints
require a nonempty separate `TRIAL_BOARD_API_KEY` through `X-Trial-Board-Key`, even
when the existing middleware is disabled in local development. Stabilibot sends
its existing `BACKEND_API_KEY` as `X-API-Key` and the shared trial key in the second
header. Keep both credentials in server secret environments; never in browser JS.
The trial key trusts its caller to assert real Discord identities and current
roles. Do not share this key with general website/browser clients.

## Transport contract

`POST /trial-board/actions`, JSON:

```json
{
  "guild_id": 123456789012345678,
  "action": "health",
  "actor": {"id": 234567890123456789, "role_ids": [345678901234567890]},
  "data": {}
}
```

Response: `{"result": ...}`; 401 invalid dedicated credential, 403 wrong guild,
409 authorization/workflow/validation conflict, 503 disabled/unavailable. Responses
and logs do not include SQL failures, credentials or feedback payloads. Mutations
are not blindly retried after network errors.

Staff actions: `approve` (`user`, `board`, `capacity`), `disable` (`user`), `create`
(`applicant`, `channel`, `board`, `minutes`, stable `request_id`), `close` (`number`,
`outcome`), `pause`, `resume`, `health`, `job` (`delivery`) and `recover` (`delivery`,
`status`, verified `message`/`channel` for `sent`, or explicit `pending` retry).

Participant actions: `get` (`number`); `list` (staff/approved volunteers);
`volunteer` (self status); `availability` (volunteer raw `windows` and `zone`);
`away`; `applicant_availability` (`number`, raw `windows`, `zone`, card `revision`);
`slots` (`number`); `propose` (`number`, `start`, `revision`); `confirm` (`number`,
`revision`); `feedback` (`number`, `recommendation`, `notes`); `reopen` (`number`,
`revision`, staff may omit revision). The backend independently checks roles,
volunteer approval, participants, stale revisions, time, capacity and overlaps.

Transport-only actions use `actor: null`: `bootstrap` returns matching configuration
and durable view registrations; `dispatch` (`worker`) acquires/renews the lease,
advances scheduling and claims one job, returning its trial plus private feedback
only for a feedback delivery; `ack` (`worker`, `delivery`, `claim_token`, `status`,
`message`, `channel`) records its receipt; `suspend` pauses after Discord permission
validation fails. Other clients must not call these operations.

## Transaction and failure behavior

All state changes lock the singleton state row with `SELECT FOR UPDATE`. This
serializes the capacity, overlap, duplicate applicant and idempotency checks across
backend workers. A unique active-applicant index and durable request IDs reinforce
those rules. A replayed request returns the same trial even after it closes or the
workflow pauses. Approval never implicitly opts a volunteer in.

The outbox stores data and receipts, not rendered Discord messages. Lease takeover
or an expired send claim marks delivery `uncertain`; no automatic resend occurs.
Later jobs for that trial remain held until staff inspect Discord and reconcile.
Claim tokens reject stale acknowledgements; identical receipt retries are safe.
Backend processing does not change clan membership/rank roles or admission policy.

The existing application accept endpoint remains unchanged. A manually started
trial works end to end through Discord. For a future website acceptance hook, call
`services.trial_board.TrialBoard.create` only after staff acceptance and an explicit
private Discord application-channel association, using a stable application request
ID. Do not infer channel IDs or turn an admission/rank API call into a trial silently.

## Tests

Use an isolated PostgreSQL database whose name ends in `_test`. Existing conftest
and calendar tests deliberately drop test schemas. Never point these at production.
Set `DATABASE_USERNAME`, `DATABASE_PASSWORD`, `DATABASE_URL` as for existing tests;
`DATABASE_URL` includes host, port and the `*_test` database. Optionally set
`TRIAL_BOARD_TEST_DATABASE_URL` to a full SQLAlchemy URL for the new workflow tests.

```sh
python -m pip install -r requirements.txt
python -m pytest
```

The new tests cover the full HTTP trial flow, keys/role/participant isolation,
PostgreSQL booking and start races, capacity/overlap, DST, backend restarts, reminder
deduplication, worker takeover, lost claim/receipt responses, private feedback,
manual reconciliation and migration upgrade/downgrade. No Discord messages are
sent. Complete the paired bot's private Discord acceptance checklist before rollout.
