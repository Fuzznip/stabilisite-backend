# Current Event Processing Logic Analysis

## Overview
This document analyzes the existing bingo event processing logic to ensure we capture all features and identify what needs to change for the new schema.

---

## Current Processing Flow (bingo_handler)

### 1. **Event Submission Entry Point**
- Location: [endpoints/events/submit.py](endpoints/events/submit.py:29-49)
- Receives action data from external system (DINK plugin)
- Input format:
```python
{
    "rsn": str,          # Player RuneScape name
    "id": str,           # Discord ID
    "trigger": str,      # Item/boss name
    "source": str,       # Where it came from
    "quantity": int,     # How many
    "totalValue": int,   # GP value
    "type": str          # "DROP" or "KC"
}
```

### 2. **Handler Registration System**
- Location: [event_handlers/event_handler_init.py](event_handlers/event_handler_init.py:1-14)
- Multiple event handlers registered:
  - `gnome_child_bone_handler` (DINK_TEST)
  - `stability_party_handler` (STABILITY_PARTY)
  - `botw_handler` (BOTW)
  - `bingo_handler` (BINGO)
  - `raid_weekend_event_handler` (RAID_WEEKEND)
- **ALL handlers are called for EVERY submission**
- Each handler checks if there's an active event of its type

### 3. **Bingo Handler Processing Steps**

#### Step 3.1: Find Active Event
```python
# Lines 141-149 in bingo.py
event: Events = Events.query.filter(
    Events.start_time <= now,
    Events.end_time >= now,
    Events.type == "BINGO"
).first()
```
- Checks for active BINGO event
- Returns early if none found

#### Step 3.2: Log Action to Database
```python
# Lines 152-163
event_log_entry: EventLog = EventLog(
    event_id=event.id,
    rsn=submission.rsn,
    discord_id=submission.id,
    trigger=submission.trigger,
    source=submission.source,
    quantity=submission.quantity,
    type=submission.type,
    value=submission.totalValue
)
db.session.add(event_log_entry)
db.session.commit()
```
- **IMPORTANT**: Logs EVERY action for the event, even if player not participating
- Also writes to Firestore (line 165)

#### Step 3.3: Find Player's Team
```python
# Lines 168-177
player = EventTeamMemberMappings.query.join(EventTeams).filter(
    EventTeams.event_id == event.id,
    (
        func.lower(EventTeamMemberMappings.username) == username.lower()
    ) | (
        func.lower(EventTeamMemberMappings.discord_id) == str(discord_id).lower()
    )
).first()
```
- **Case-insensitive matching** on both username AND discord_id
- Returns early if player not in event

#### Step 3.4: Load Team Data from JSONB
```python
# Line 188
team_data: BingoTeam = BingoTeam.from_dict(team.data)
```
- **Current schema**: All progress stored in `EventTeams.data` JSONB field
- Deserializes complex nested structure

#### Step 3.5: Process Submission Against All Tiles
```python
# progress_team function, lines 74-106
for tile in tiles:
    tile_progress = team_data.get_tile_progress(tile_index)
    if tile_progress is None:
        # Initialize new tile progress
        tile_progress = BingoTileProgress()
        tile_progress.tile_id = tile_index
        tile_progress.name = tile.name
        tile_progress.progress = []
        team_data.board_progress.append(tile_progress)

    bingo_progress = progress_tile(submission, tile_progress, tile, team_data)
```
- **Checks ALL tiles for EVERY action** (could match multiple tiles)
- Initializes progress on-the-fly if not exists

#### Step 3.6: Match Trigger to Challenges
```python
# progress_tile function, lines 28-69
for task in tasks:  # BingoChallenges (3 per tile: bronze, silver, gold)
    for challenge_id in task.challenges:
        event_challenge = EventChallenges.query.filter_by(id=challenge_id).first()

        for task_id in event_challenge.tasks:  # EventTasks
            event_task = EventTasks.query.filter_by(id=task_id).first()

            for task_trigger_id in event_task.triggers:  # EventTriggers
                event_trigger = EventTriggers.query.filter_by(id=task_trigger_id).first()

                # Normalize and match
                trigger_source_norm = event_trigger.source.lower() if event_trigger.source else ""
                submission_source_norm = submission.source.lower() if submission.source else ""

                # Wildcard source matching
                source_matches = (not trigger_source_norm) or (trigger_source_norm == submission_source_norm)

                if event_trigger.trigger.lower() == submission.trigger.lower() and source_matches:
                    # MATCH FOUND - Progress the task
                    task_completed = tile_progress.add_task_progress(...)
```

**KEY FEATURES**:
- **Case-insensitive trigger matching**
- **Wildcard source matching**: Empty source in trigger matches ANY source
- **Nested loop structure**: BingoChallenges → EventChallenges → EventTasks → EventTriggers
- **Multiple matches possible**: Same action can progress multiple tiles/tasks

#### Step 3.7: Update Progress (OR logic)
```python
# add_task_progress_or function, lines 120-165 in models/bingo.py
if task_progress is None:
    # Create new task progress
    task_progress = BingoTaskProgress()
    task_progress.log = []

challenge_progress = next((c for c in task_progress.log if c.challenge_id == event_challenge.id), None)
if challenge_progress is None:
    # First time seeing this challenge
    challenge_progress = BingoChallengeProgress()
    challenge_progress.challenge_id = event_challenge.id
    challenge_progress.value = quantity
    challenge_progress.required = event_task.quantity
    challenge_progress.completed = challenge_progress.value >= challenge_progress.required
    challenge_progress.triggers = [BingoTriggerProgress(name=trigger, value=quantity)]
    task_progress.log.append(challenge_progress)
else:
    # Update existing challenge
    challenge_progress.value += quantity
    challenge_progress.completed = challenge_progress.value >= challenge_progress.required

    # Track which specific trigger contributed
    for log_entry in challenge_progress.triggers:
        if log_entry.name == trigger:
            log_entry.value += quantity
            break
    else:
        # New trigger for this challenge
        challenge_progress.triggers.append(BingoTriggerProgress(name=trigger, value=quantity))

# Mark task as completed if ANY challenge is completed (OR logic)
if not task_progress.completed:
    task_progress.completed = challenge_progress.completed
```

**KEY FEATURES**:
- **Cumulative quantity tracking**: Adds quantities together
- **OR logic**: Task completes when ANY challenge completes
- **Per-trigger tracking**: Remembers which specific triggers contributed and how much
- **Returns boolean**: True if task was JUST completed (not already completed)

#### Step 3.8: Award Points for Task Completion
```python
# Line 65 in bingo.py
if task_completed:
    team_data.points += 3
    team_data.board_state[tile.index] += 1
```
- **3 points per task**
- `board_state` array tracks medal level (0=none, 1=bronze, 2=silver, 3=gold)

#### Step 3.9: Check for Bingo Completions
```python
# Lines 200-209
bingo_count = 0
for index in completed_task_tile_indices:
    if check_row_for_bingo(index, team_data):
        bingo_count += 1
    if check_column_for_bingo(index, team_data):
        bingo_count += 1

team_data.points += bingo_count * 15
```

**Bingo Detection Logic** (lines 115-137):
```python
def check_row_for_bingo(tile_index: int, team_data: BingoTeam) -> bool:
    completed_tasks = tile_progress.get_completed_task_count()  # How many tasks THIS tile has
    row = tile_index // 5
    min_completed = 3  # Start with max

    # Find minimum tasks completed across row
    for i in range(5):
        tile_progress = team_data.get_tile_progress(str(row * 5 + i))
        min_completed = min(min_completed, tile_progress.get_completed_task_count())

    # Bingo if THIS tile's count equals the row's minimum
    return min_completed == completed_tasks
```

**BINGO DETECTION BUG IDENTIFIED**:
This logic is **WRONG**! It awards a bingo if the NEWLY completed tile has the same medal level as the minimum in that row/column, rather than checking if ALL tiles in the row/column have the SAME medal level.

**Example of bug**:
- Row has tiles with medal levels: [1, 1, 1, 1, 0]
- Player completes bronze (level 1) on the 5th tile
- `min_completed = 1` (correct)
- `completed_tasks = 1` (the newly completed tile)
- Returns TRUE, awards bingo - **INCORRECT!** Should require ALL tiles at level 1.

**Correct logic should be**:
```python
# Check if ALL tiles in row have at least 'medal_level' completed tasks
def check_row_for_bingo(tile_index: int, team_data: BingoTeam, medal_level: int) -> bool:
    row = tile_index // 5
    for i in range(5):
        tile_progress = team_data.get_tile_progress(str(row * 5 + i))
        if not tile_progress or tile_progress.get_completed_task_count() < medal_level:
            return False
    return True
```

#### Step 3.10: Save Progress Back to JSONB
```python
# Lines 196-197, 212-213
team.data = team_data.to_dict()
db.session.commit()
```
- Serializes entire progress structure back to JSONB
- **No separate status tables** - all in one field

#### Step 3.11: Generate Notifications
```python
# Lines 216-306
if bingo_count < 1:
    # Task completion notification
    return [NotificationResponse(
        threadId=event.thread_id,
        title=f"{tile.name} Task Completed!",
        ...
    )]
elif bingo_count == 1:
    # Single bingo
    return [NotificationResponse(title="Bingo!", ...)]
elif bingo_count == 2:
    # Double bingo
    return [NotificationResponse(title="Multiple Bingos!", ...)]
```
- Uses `event.thread_id` to route notifications
- Includes team name, points, tile info

---

## Current Data Structures

### Old Schema Tables Used:
1. **Events** - Event metadata (`type`, `thread_id`, `start_time`, `end_time`)
2. **EventTeams** - Team info (`name`, `image`, `data` JSONB)
3. **EventTeamMemberMappings** - User to team mapping (`username`, `discord_id`)
4. **BingoTiles** - Tile definitions (`event_id`, `index`, `name`, `data` JSONB)
5. **BingoChallenges** - Task definitions (`tile_id`, `task_index`, `challenges` UUID array, `name`)
6. **EventChallenges** - Challenge definitions (`tasks` UUID array, `type` "OR"/"AND")
7. **EventTasks** - Task requirements (`triggers` UUID array, `quantity`, `value`)
8. **EventTriggers** - Trigger definitions (`trigger`, `source`, `type`)
9. **EventLog** - Action log (`event_id`, `rsn`, `discord_id`, `trigger`, `source`, `quantity`, `type`, `value`)

### JSONB Storage in EventTeams.data:
```python
{
    "team_id": str,
    "name": str,
    "members": list[str],
    "image_url": str,
    "points": int,
    "board_state": [0,0,1,2,3,0,...],  # 25 integers, 0-3 for medal level
    "board_progress": [
        {
            "tile_id": str,
            "name": str,
            "progress": [
                {
                    "task_id": str,
                    "task_index": str,
                    "completed": bool,
                    "proof": str,
                    "log": [
                        {
                            "challenge_id": str,
                            "value": int,
                            "required": int,
                            "completed": bool,
                            "triggers": [
                                {"name": str, "value": int}
                            ],
                            "type": "OR"
                        }
                    ]
                }
            ]
        }
    ]
}
```

---

## New Schema Differences & Required Changes

### 1. **Team Member Lookup**
**OLD**:
```python
EventTeamMemberMappings.query.join(EventTeams).filter(
    EventTeams.event_id == event.id,
    (func.lower(EventTeamMemberMappings.username) == username.lower()) |
    (func.lower(EventTeamMemberMappings.discord_id) == str(discord_id).lower())
).first()
```

**NEW**:
```python
# TeamMember has user_id (UUID), not username/discord_id
# Need to:
# 1. Look up user by discord_id first
# 2. Then find team membership by user_id

user = Users.query.filter(func.lower(Users.discord_id) == str(discord_id).lower()).first()
if not user:
    return []

team_member = TeamMember.query.join(Team).filter(
    Team.event_id == event.id,
    TeamMember.user_id == user.id
).first()
```

**CHANGES NEEDED**:
- ✅ Use proper FK to Users table
- ✅ Two-step lookup (user, then team)
- ✅ Keep case-insensitive matching

---

### 2. **Progress Storage**
**OLD**: All progress in `EventTeams.data` JSONB
**NEW**: Separate status tables (`TileStatus`, `TaskStatus`, `ChallengeStatus`)

**CHANGES NEEDED**:
- ❌ No more JSONB serialization/deserialization
- ✅ Query/update status tables directly
- ✅ Create status records on-the-fly if not exists
- ✅ Use `upsert` pattern for updates

---

### 3. **Challenge Structure**
**OLD**:
```
BingoChallenges (tile-level)
  └─ challenges: array[UUID]
      └─ EventChallenges
          └─ tasks: array[UUID]
              └─ EventTasks
                  └─ triggers: array[UUID]
                      └─ EventTriggers
```

**NEW**:
```
Tile
  └─ Task (direct FK)
      └─ Challenge (direct FK)
          └─ Trigger (direct FK)
```

**CHANGES NEEDED**:
- ✅ Simpler FK relationships
- ✅ No array UUID lookups
- ❌ No separate BingoChallenges table
- ✅ Task-level challenges instead of tile-level

---

### 4. **Challenge Hierarchy (NEW FEATURE)**
**OLD**: Flat challenge structure with OR/AND type
**NEW**: Recursive `parent_challenge_id` for nesting

**CHANGES NEEDED**:
- ⚠️ Need to implement AND logic (currently returns False!)
- ✅ Support nested challenges via parent_challenge_id
- ⚠️ New complexity: How to evaluate nested require_all logic?

---

### 5. **Points Storage**
**OLD**: `team_data.points` in JSONB
**NEW**: `teams.points` as INTEGER column

**CHANGES NEEDED**:
- ✅ Direct column update
- ✅ No JSONB serialization needed

---

### 6. **Board State Tracking**
**OLD**: `board_state` array [0,0,1,2,3,...]
**NEW**: `TileStatus.tasks_completed` (0-3)

**CHANGES NEEDED**:
- ✅ Query TileStatus instead of array lookup
- ✅ medal_level helper method exists

---

### 7. **Action Logging**
**OLD**: `EventLog` table (separate from new schema)
**NEW**: `Action` table in new_stability schema

**CHANGES NEEDED**:
- ✅ Different table, same concept
- ⚠️ **QUESTION**: Keep EventLog for backward compatibility? Or migrate to Action table?
- ⚠️ **QUESTION**: Still write to Firestore?

---

### 8. **Trigger Matching**
**OLD**:
```python
# Wildcard source: empty source matches ANY
source_matches = (not trigger_source_norm) or (trigger_source_norm == submission_source_norm)
```

**NEW**: Same logic needed

**CHANGES NEEDED**:
- ✅ Keep wildcard source matching
- ✅ Keep case-insensitive trigger name matching

---

### 9. **Per-Trigger Progress Tracking**
**OLD**: `BingoTriggerProgress` tracks which triggers contributed
```python
challenge_progress.triggers = [
    {"name": "Twisted bow", "value": 2},
    {"name": "Elder maul", "value": 1}
]
```

**NEW**: No equivalent in schema!

**CHANGES NEEDED**:
- ⚠️ **LOST FEATURE**: Can't track which specific triggers contributed
- ⚠️ Only have total quantity in `ChallengeStatus.quantity`
- ✅ `ChallengeProof` links actions, but doesn't track per-trigger totals
- 💡 **DECISION NEEDED**: Keep per-trigger tracking or simplify?

---

### 10. **Bingo Detection**
**OLD**: `check_row_for_bingo()` and `check_column_for_bingo()`
**NEW**: Need equivalent logic using TileStatus table

**CHANGES NEEDED**:
- ✅ Query TileStatus for all tiles in row/column
- ✅ Check if all have same tasks_completed level
- ⚠️ **FIX THE BUG** identified above!

---

### 11. **Notification Generation**
**OLD**: `event.thread_id`, `team.name`, `team.image`
**NEW**: Thread ID not in new Event model!

**CHANGES NEEDED**:
- ⚠️ **MISSING FIELD**: Need to add `thread_id` to Event model
- ⚠️ **MISSING FIELD**: Need to add `image` to Team model (or use existing EventTeams.image)

---

### 12. **Challenge Proof Tracking**
**OLD**: No explicit proof tracking, just "proof" string field
**NEW**: `ChallengeProof` table links actions to challenge status

**CHANGES NEEDED**:
- ✅ Create ChallengeProof record when action progresses challenge
- ✅ Better audit trail
- ✅ Can reconstruct progress from proofs

---

## Missing Features to Add

### 1. **Event.thread_id**
Add to Event model for Discord notifications

### 2. **Team.image_url**
Add to Team model for visual display

### 3. **AND Challenge Logic**
Currently `add_task_progress_and()` returns False - need implementation

### 4. **Nested Challenge Evaluation**
Logic for evaluating `parent_challenge_id` hierarchies

### 5. **Migration Script**
Convert existing JSONB progress to new status tables

---

## Bugs to Fix

### 1. **Bingo Detection Logic** (CRITICAL)
Current logic incorrectly awards bingos. See Step 3.9 above.

**Fix**:
```python
def check_bingo(event_id, team_id, medal_level):
    """Check if team has completed all tiles in any row/column at medal_level"""
    tiles = TileStatus.query.join(Tile).filter(
        Tile.event_id == event_id,
        TileStatus.team_id == team_id
    ).all()

    # Build 5x5 grid of medal levels
    grid = [[0]*5 for _ in range(5)]
    for ts in tiles:
        tile = Tile.query.get(ts.tile_id)
        row, col = tile.index // 5, tile.index % 5
        grid[row][col] = ts.tasks_completed

    bingo_count = 0

    # Check rows
    for row in grid:
        if all(level >= medal_level for level in row):
            bingo_count += 1

    # Check columns
    for col in range(5):
        if all(grid[row][col] >= medal_level for row in range(5)):
            bingo_count += 1

    return bingo_count
```

---

## Implementation Strategy

### Phase 1: Core Action Processing
1. Create action from submission
2. Find player's team in active events
3. Match action to triggers
4. Update ChallengeStatus (quantity, completed)
5. Check if challenge completion triggers task completion
6. Update TaskStatus (completed)
7. Check if task completion triggers tile completion
8. Update TileStatus (tasks_completed++)
9. Award points (3 per task)
10. Create ChallengeProof records

### Phase 2: Bingo Detection
1. After tile status update, check for new bingos
2. Query all TileStatus for team
3. Build medal level grid
4. Detect newly completed rows/columns
5. Award bonus points (15 per bingo)
6. Return bingo count

### Phase 3: Notifications
1. Generate NotificationResponse based on:
   - Task completion (no bingo)
   - Single bingo
   - Multiple bingos
2. Include team info, points, tile name

### Phase 4: Audit Trail
1. Maintain ChallengeProof records
2. Enable progress reconstruction
3. Support debugging/admin review

---

## Questions for Confirmation

1. **Should we keep EventLog for backward compatibility**, or fully migrate to Action table?
2. **Should we write to Firestore still**, or remove that dependency?
3. **Do we need per-trigger progress tracking**, or is per-challenge quantity sufficient?
4. **Should we add thread_id and image_url to new models**, or handle separately?
5. **How should nested challenges (parent_challenge_id) be evaluated?**
6. **Should we migrate existing JSONB data**, or start fresh?
7. **Should actions check ALL event types**, or just BINGO for now?

---

## Summary of Changes

### What Stays the Same ✅
- Case-insensitive matching
- Wildcard source matching
- OR challenge logic (any trigger completes)
- Points: 3 per task, 15 per bingo
- Notification structure

### What Changes ⚠️
- No JSONB storage (use status tables)
- Proper FK to Users table
- Simpler challenge structure (no nested arrays)
- Fixed bingo detection logic
- ChallengeProof audit trail

### What's New ✅
- Recursive challenge hierarchy
- Separate status tables
- Better audit trail
- Proper database constraints

### What's Lost ❌
- Per-trigger quantity tracking
- AND challenge logic (needs implementation)

### What's Missing 🔴
- Event.thread_id
- Team.image_url
- Nested challenge evaluation
