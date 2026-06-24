Server-side (SSR, on page load via getConquest.ts)

Section Endpoint
Territories (initial data) API_URL/v2/events/{id}/territories
Regions (initial data) API_URL/v2/events/{id}/regions
Activity log (initial data) API_URL/v2/events/{id}/event-logs?page=1&per_page=50
Client-side (polled every 10s via React Query)

Section Endpoint
Territories (live refresh) /api/conquest/{id}/territories
Regions (live refresh) /api/conquest/{id}/regions
Teams (live refresh) /api/conquest/{id}/teams
Activity log (live refresh) /api/conquest/{id}/logs?per_page=20
Activity log (load more) /api/conquest/{id}/logs?per_page=20&page={n}
Real-time (SSE)

Section Endpoint
Live updates /api/conquest/{id}/stream
Per-territory (fetched per row/card, cached forever)

Section Endpoint
Challenge details /api/conquest/challenges/{challengeId}
Trigger details (fallback if not embedded) /api/conquest/triggers/{triggerId}
Territory progress /api/conquest/territories/{territoryId}/progress (stale 15s)
Territory proofs (on dialog open) /api/conquest/territories/{territoryId}/proofs?team_id={teamId}
Scoreboard / Player Breakdown tabs

Section Endpoint
Full event log (scoreboard) /api/conquest/{id}/logs?per_page=1000 (polled 10s)
Player actions /api/conquest/{id}/player-actions (polled 10s)
