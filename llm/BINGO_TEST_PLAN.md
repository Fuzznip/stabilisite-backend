# Bingo Event System - Comprehensive Test Plan

## Overview
This test plan validates the complete bingo event system from API submission through to database model updates. Each test should be executed manually via the `/events/submit` API endpoint with appropriate payloads.

## Prerequisites
- Database snapshot/dump created for rollback
- Active bingo event configured in database
- Test teams and users set up with team memberships
- API server running and accessible

## API Endpoint
**POST** `/events/submit`

**Payload Structure:**
```json
{
  "rsn": "string",           // RuneScape name of player
  "id": "string",            // Discord ID (optional)
  "trigger": "string",       // Name of item/boss/achievement
  "source": "string",        // Source of trigger (boss name, etc.)
  "quantity": number,        // Quantity (kills, items, etc.)
  "totalValue": number,      // Value (optional)
  "type": "string"           // Type: DROP, KC, SKILL, QUEST, etc.
}
```

---

## Test Categories

### 1. USER IDENTIFICATION & VALIDATION

#### Test 1.1: Valid User by RSN
**Objective:** Verify submission works with valid RSN (case-insensitive)
```json
{
  "rsn": "TestPlayer1",
  "trigger": "Vorkath",
  "type": "KC",
  "quantity": 1
}
```
**Expected:** Action created, progress updated for player's team

#### Test 1.2: Valid User by RSN (Different Case)
```json
{
  "rsn": "testplayer1",
  "trigger": "Vorkath",
  "type": "KC",
  "quantity": 1
}
```
**Expected:** Same user identified (case-insensitive match)

#### Test 1.3: Valid User by Discord ID
```json
{
  "rsn": null,
  "id": "123456789",
  "trigger": "Vorkath",
  "type": "KC",
  "quantity": 1
}
```
**Expected:** User found by Discord ID, action processed

#### Test 1.4: Invalid User - Not Found
```json
{
  "rsn": "NonExistentPlayer",
  "trigger": "Vorkath",
  "type": "KC",
  "quantity": 1
}
```
**Expected:** Action NOT created, warning logged, empty response

#### Test 1.5: User Not in Event
**Setup:** User exists but not in any team
```json
{
  "rsn": "PlayerNotInEvent",
  "trigger": "Vorkath",
  "type": "KC",
  "quantity": 1
}
```
**Expected:** Action created but no team progress, info logged

---

### 2. ACTION CREATION & LOGGING

#### Test 2.1: Action with All Fields
```json
{
  "rsn": "TestPlayer1",
  "id": "123456789",
  "trigger": "Tanzanite Fang",
  "source": "Zulrah",
  "quantity": 1,
  "totalValue": 3500000,
  "type": "DROP"
}
```
**Verify:**
- Action record created in `new_stability.actions`
- All fields populated correctly
- Firestore write attempted

#### Test 2.2: Action with Minimal Fields
```json
{
  "rsn": "TestPlayer1",
  "trigger": "Vorkath",
  "type": "KC",
  "quantity": 1
}
```
**Verify:**
- Action created with null/default values for missing fields
- Source is null

#### Test 2.3: Multiple Actions from Same User
Submit 5 identical actions
**Verify:**
- 5 separate Action records created
- Each links to same user via player_id
- Timestamps differ

---

### 3. TRIGGER MATCHING LOGIC

#### Test 3.1: Exact Trigger Name Match (Case-Insensitive)
**Setup:** Challenge has trigger "Vorkath"
```json
{
  "rsn": "TestPlayer1",
  "trigger": "vorkath",
  "type": "KC",
  "quantity": 1
}
```
**Expected:** Trigger matches (case-insensitive)

#### Test 3.2: Trigger Name Mismatch
```json
{
  "rsn": "TestPlayer1",
  "trigger": "Zulrah",
  "type": "KC",
  "quantity": 1
}
```
**Expected:** Does not match Vorkath challenge

#### Test 3.3: Source Matching - Wildcard (Empty Source)
**Setup:** Trigger has empty/null source (matches anything)
```json
{
  "rsn": "TestPlayer1",
  "trigger": "Magic Fang",
  "source": "Zulrah",
  "type": "DROP",
  "quantity": 1
}
```
**Expected:** Matches trigger with null source

#### Test 3.4: Source Matching - Specific Source Required
**Setup:** Trigger has source="Zulrah"
```json
{
  "rsn": "TestPlayer1",
  "trigger": "Magic Fang",
  "source": "Zulrah",
  "type": "DROP",
  "quantity": 1
}
```
**Expected:** Matches

#### Test 3.5: Source Mismatch
**Setup:** Trigger source="Zulrah"
```json
{
  "rsn": "TestPlayer1",
  "trigger": "Magic Fang",
  "source": "Chambers of Xeric",
  "type": "DROP",
  "quantity": 1
}
```
**Expected:** Does NOT match

#### Test 3.6: Source Case Sensitivity
**Setup:** Trigger source="Zulrah"
```json
{
  "rsn": "TestPlayer1",
  "trigger": "Magic Fang",
  "source": "zulrah",
  "type": "DROP",
  "quantity": 1
}
```
**Expected:** Matches (case-insensitive)

---

### 4. CHALLENGE COMPLETION LOGIC

#### Test 4.1: Simple Challenge - Single Requirement
**Setup:** Challenge requires 1 kill
```json
{
  "rsn": "TestPlayer1",
  "trigger": "Vorkath",
  "type": "KC",
  "quantity": 1
}
```
**Verify:**
- ChallengeStatus created/updated
- quantity = 1
- completed = true
- ChallengeProof created linking to Action

#### Test 4.2: Cumulative Challenge - Partial Progress
**Setup:** Challenge requires 25 kills
```json
{
  "rsn": "TestPlayer1",
  "trigger": "Vorkath",
  "type": "KC",
  "quantity": 10
}
```
**Verify:**
- ChallengeStatus.quantity = 10
- completed = false
- ChallengeProof created

#### Test 4.3: Cumulative Challenge - Completion
**Setup:** Existing quantity=20, requires 25
```json
{
  "rsn": "TestPlayer1",
  "trigger": "Vorkath",
  "type": "KC",
  "quantity": 5
}
```
**Verify:**
- ChallengeStatus.quantity = 25
- completed = true
- ChallengeProof created for this action

#### Test 4.4: Challenge Already Completed
**Setup:** Challenge already completed (quantity=25, completed=true)
```json
{
  "rsn": "TestPlayer1",
  "trigger": "Vorkath",
  "type": "KC",
  "quantity": 10
}
```
**Verify:**
- ChallengeStatus.quantity = 35 (continues incrementing)
- completed remains true
- New ChallengeProof created

#### Test 4.5: Multiple Proofs for Same Challenge
Submit 3 separate actions for same challenge
**Verify:**
- 3 separate ChallengeProof records
- Each links to different Action
- All link to same ChallengeStatus

---

### 5. PARENT-CHILD CHALLENGE LOGIC

#### Test 5.1: Child Challenge Completion (No Parent Complete Yet)
**Setup:** Parent requires 3 of 4 children
```json
{
  "rsn": "TestPlayer1",
  "trigger": "General Graardor",
  "type": "KC",
  "quantity": 10
}
```
**Verify:**
- Child ChallengeStatus completed=true
- Parent ChallengeStatus created
- Parent quantity = 1
- Parent completed = false

#### Test 5.2: Parent Completion via Children
**Setup:** Parent needs 3 of 4, currently 2 completed
```json
{
  "rsn": "TestPlayer1",
  "trigger": "Kree'arra",
  "type": "KC",
  "quantity": 10
}
```
**Verify:**
- Child ChallengeStatus completed=true
- Parent quantity = 3
- Parent completed = true

#### Test 5.3: Extra Children Beyond Parent Requirement
**Setup:** Parent needs 3 of 4, already has 3
```json
{
  "rsn": "TestPlayer1",
  "trigger": "Commander Zilyana",
  "type": "KC",
  "quantity": 10
}
```
**Verify:**
- 4th child completed
- Parent quantity = 4
- Parent remains completed=true

#### Test 5.4: Child Without Trigger (Parent Challenge)
**Setup:** Parent challenge has no trigger_id
**Expected:** Skipped during processing (line 57-58 in bingo.py)

---

### 6. TASK COMPLETION LOGIC - OR

#### Test 6.1: Task with Single Challenge (OR - Trivial)
**Setup:** Task with require_all=False, 1 challenge
```json
{
  "rsn": "TestPlayer1",
  "trigger": "Tanzanite Fang",
  "source": "Zulrah",
  "type": "DROP",
  "quantity": 1
}
```
**Verify:**
- Challenge completed
- TaskStatus created, completed=true
- TileStatus updated

#### Test 6.2: Task with Multiple Challenges - First Completes
**Setup:** Task (require_all=False) with 3 challenges, none completed
```json
{
  "rsn": "TestPlayer1",
  "trigger": "Magic Fang",
  "source": "Zulrah",
  "type": "DROP",
  "quantity": 1
}
```
**Verify:**
- Challenge 1 completed
- Task completed (OR logic)
- Other challenges not required

#### Test 6.3: Task Already Completed (OR)
**Setup:** Task already completed via different challenge
```json
{
  "rsn": "TestPlayer1",
  "trigger": "Serpentine Visage",
  "source": "Zulrah",
  "type": "DROP",
  "quantity": 1
}
```
**Verify:**
- New challenge completed
- Task remains completed (idempotent)
- No duplicate task completion

---

### 7. TASK COMPLETION LOGIC - AND

#### Test 7.1: AND Task - Partial Progress
**Setup:** Task requires ALL 3 challenges, 0 completed
```json
{
  "rsn": "TestPlayer1",
  "trigger": "Dagannoth Rex",
  "type": "KC",
  "quantity": 1
}
```
**Verify:**
- Challenge 1 completed
- TaskStatus created, completed=false
- TileStatus NOT updated

#### Test 7.2: AND Task - Second Challenge
**Setup:** 1 of 3 challenges completed
```json
{
  "rsn": "TestPlayer1",
  "trigger": "Dagannoth Prime",
  "type": "KC",
  "quantity": 1
}
```
**Verify:**
- Challenge 2 completed
- TaskStatus remains completed=false
- TileStatus NOT updated

#### Test 7.3: AND Task - Completion
**Setup:** 2 of 3 challenges completed
```json
{
  "rsn": "TestPlayer1",
  "trigger": "Dagannoth Supreme",
  "type": "KC",
  "quantity": 1
}
```
**Verify:**
- Challenge 3 completed
- TaskStatus.completed=true
- TileStatus updated

#### Test 7.4: AND Task - Out of Order Completion
Submit challenges in random order: 3rd, 1st, 2nd
**Verify:**
- All 3 challenges completed
- Task completed after final challenge
- Order doesn't matter

---

### 8. TILE STATUS UPDATES

#### Test 8.1: First Task on Tile
**Setup:** Tile has 0 tasks completed
```json
{
  "rsn": "TestPlayer1",
  "trigger": "Vorkath",
  "type": "KC",
  "quantity": 25
}
```
**Verify:**
- TileStatus created if not exists
- tasks_completed = 1
- Team points += 3

#### Test 8.2: Second Task on Tile
**Setup:** Tile has 1 task completed
```json
{
  "rsn": "TestPlayer1",
  "trigger": "Vorkath",
  "type": "KC",
  "quantity": 50
}
```
**Verify:**
- TileStatus.tasks_completed = 2
- Team points += 3 (total +6)

#### Test 8.3: Third Task on Tile (Cap)
**Setup:** Tile has 2 tasks completed
```json
{
  "rsn": "TestPlayer1",
  "trigger": "Vorkath",
  "type": "KC",
  "quantity": 100
}
```
**Verify:**
- TileStatus.tasks_completed = 3 (capped)
- Team points += 3 (total +9)

#### Test 8.4: Fourth Task on Tile (Beyond Cap)
**Setup:** Tile already has 3 tasks completed
**Note:** Unlikely in real scenario but test the cap
**Verify:**
- TileStatus.tasks_completed remains 3
- Team points += 3 (still awarded)

#### Test 8.5: Multiple Teams - Separate Status
**Setup:** Submit for different team
```json
{
  "rsn": "Team2Player",
  "trigger": "Vorkath",
  "type": "KC",
  "quantity": 25
}
```
**Verify:**
- Separate TileStatus for Team 2
- Team 1 status unchanged

---

### 9. TEAM POINTS CALCULATION

#### Test 9.1: Points from Task Completion
Complete a task
**Verify:**
- Team.points += 3

#### Test 9.2: Points from Multiple Tasks
Complete 3 tasks on different tiles
**Verify:**
- Team.points += 9 (3 per task)

#### Test 9.3: Points from Bingo (Row)
**Setup:** Complete 5th tile in a row (all at same medal level)
**Verify:**
- Team.points += 15 (bingo bonus)
- Plus 3 from task completion

#### Test 9.4: Points from Bingo (Column)
**Setup:** Complete 5th tile in a column
**Verify:**
- Team.points += 15 (bingo bonus)

#### Test 9.5: Double Bingo (Row + Column Intersection)
**Setup:** Complete tile that creates both row and column bingo
**Verify:**
- Team.points += 30 (15 per bingo)
- Plus 3 from task completion
- Total +33

---

### 10. BINGO DETECTION - ROWS

#### Test 10.1: Row Incomplete (Different Medal Levels)
**Setup:** Row with tiles at [1,1,0,1,1] tasks completed
**Expected:** No bingo (min=0)

#### Test 10.2: Row Bronze Bingo
**Setup:** Row with all tiles at 1+ tasks completed, min=1
**Verify:**
- check_row_for_bingo returns true
- Notification: "Bingo!"
- +15 points

#### Test 10.3: Row Silver Bingo
**Setup:** Row with all tiles at 2+ tasks completed, min=2
**Verify:**
- Bingo detected
- +15 points

#### Test 10.4: Row Gold Bingo
**Setup:** Row with all tiles at 3 tasks completed
**Verify:**
- Bingo detected
- +15 points

#### Test 10.5: Multiple Rows
**Setup:** Complete task that creates bingo in already-bingoed row
**Expected:** Bingo not counted again (same row, same level)

---

### 11. BINGO DETECTION - COLUMNS

#### Test 11.1: Column Incomplete
**Setup:** Column with tiles at [1,2,0,1,1] tasks
**Expected:** No bingo (min=0)

#### Test 11.2: Column Bronze Bingo
**Setup:** All 5 tiles in column at 1+ tasks
**Verify:**
- check_column_for_bingo returns true
- +15 points

#### Test 11.3: Column Silver Bingo
**Setup:** All 5 tiles in column at 2+ tasks
**Verify:**
- Bingo detected
- +15 points

#### Test 11.4: Column Gold Bingo
**Setup:** All 5 tiles in column at 3 tasks
**Verify:**
- Bingo detected
- +15 points

---

### 12. BINGO DETECTION - EDGE CASES

#### Test 12.1: Center Tile (Tile 12) - Two Bingos
**Setup:** Complete task on tile 12 that creates both row 2 and column 2 bingo
**Verify:**
- bingo_count = 2
- Notification: "Multiple Bingos!"
- +30 points (15 * 2)

#### Test 12.2: Corner Tile - Single Bingo
**Setup:** Complete tile 0 (top-left) creating row 0 bingo
**Verify:**
- bingo_count = 1
- +15 points

#### Test 12.3: No Completed Tasks in Tile
**Setup:** Tile has tasks_completed=0
**Expected:** check_row/column returns false

#### Test 12.4: Bingo Anomaly (Should Never Happen)
**Manual Override:** Force bingo_count > 2
**Expected:**
- Notification: "Bingo Anomaly Detected!"
- Red color notification

---

### 13. NOTIFICATION RESPONSES

#### Test 13.1: No Task Completed
Submit action that doesn't complete any task
**Verify:**
- Empty list returned
- No notification

#### Test 13.2: Task Completed (No Bingo)
Complete a task
**Verify:**
- Notification title: "{Tile Name} Task Completed!"
- Color: 0xFFD700 (gold)
- Description: "The **{team name}** have completed a task!"
- Fields: Total Points

#### Test 13.3: Single Bingo
Complete row or column
**Verify:**
- Title: "Bingo!"
- Color: 0x00FF00 (green)
- Description: "...completed a row or column and scored a Bingo!"

#### Test 13.4: Double Bingo
Complete row AND column simultaneously
**Verify:**
- Title: "Multiple Bingos!"
- Color: 0xFF4500 (orange-red)
- Description: "...completed a double bingo!"

#### Test 13.5: Multiple Tasks in One Submission
**Setup:** Action completes multiple tasks on different tiles
**Verify:**
- Notification based on first completed tile
- All tiles updated correctly

---

### 14. QUANTITY HANDLING

#### Test 14.1: Quantity = 1
```json
{
  "rsn": "TestPlayer1",
  "trigger": "Vorkath",
  "type": "KC",
  "quantity": 1
}
```
**Verify:** Challenge quantity increases by 1

#### Test 14.2: Quantity > 1
```json
{
  "rsn": "TestPlayer1",
  "trigger": "Vorkath",
  "type": "KC",
  "quantity": 10
}
```
**Verify:** Challenge quantity increases by 10

#### Test 14.3: Quantity Null/Missing
```json
{
  "rsn": "TestPlayer1",
  "trigger": "Vorkath",
  "type": "KC"
}
```
**Expected:** May fail or default to 0/1 (check code)

#### Test 14.4: Quantity = 0
```json
{
  "rsn": "TestPlayer1",
  "trigger": "Vorkath",
  "type": "KC",
  "quantity": 0
}
```
**Verify:** Challenge quantity doesn't increase

#### Test 14.5: Negative Quantity
```json
{
  "rsn": "TestPlayer1",
  "trigger": "Vorkath",
  "type": "KC",
  "quantity": -5
}
```
**Verify:** Behavior (should reject or handle gracefully)

#### Test 14.6: Large Quantity
```json
{
  "rsn": "TestPlayer1",
  "trigger": "Vorkath",
  "type": "KC",
  "quantity": 1000
}
```
**Verify:** Processes correctly, completes challenge immediately

---

### 15. TYPE FIELD VARIATIONS

#### Test 15.1: Type = "DROP"
```json
{
  "trigger": "Twisted Bow",
  "type": "DROP",
  "source": "Chambers of Xeric"
}
```

#### Test 15.2: Type = "KC"
```json
{
  "trigger": "Vorkath",
  "type": "KC"
}
```

#### Test 15.3: Type = "SKILL"
```json
{
  "trigger": "99 Attack",
  "type": "SKILL"
}
```

#### Test 15.4: Type = "QUEST"
```json
{
  "trigger": "Dragon Slayer II",
  "type": "QUEST"
}
```

#### Test 15.5: Type = "ACHIEVEMENT"
```json
{
  "trigger": "Combat Achievements - Elite",
  "type": "ACHIEVEMENT"
}
```

#### Test 15.6: Type = "DIARY"
```json
{
  "trigger": "Western Provinces Hard",
  "type": "DIARY"
}
```

**Verify for all:** Action.type stored correctly

---

### 16. CONCURRENT SUBMISSIONS

#### Test 16.1: Same User, Same Challenge, Rapid Fire
Submit 10 requests quickly for same challenge
**Verify:**
- 10 Actions created
- ChallengeStatus quantity correct
- No race conditions

#### Test 16.2: Different Users, Same Team, Same Tile
2 users submit simultaneously for different tasks on same tile
**Verify:**
- Both tasks completed
- TileStatus updated correctly
- Points awarded correctly

#### Test 16.3: Different Teams, Same Challenge
Users from different teams submit for same challenge
**Verify:**
- Separate ChallengeStatus per team
- Independent progress tracking

---

### 17. EDGE CASE SCENARIOS

#### Test 17.1: Empty Event (No Tiles)
**Setup:** Event with no tiles configured
**Expected:** Empty list returned, error logged

#### Test 17.2: Tile with No Tasks
**Setup:** Tile exists but has no tasks
**Expected:** Skipped gracefully

#### Test 17.3: Task with No Challenges
**Setup:** Task exists but has no challenges
**Expected:** Skipped gracefully

#### Test 17.4: Challenge with No Trigger
**Setup:** Challenge has trigger_id = null (parent challenge)
**Expected:** Skipped (line 57-58)

#### Test 17.5: Orphaned Trigger
**Setup:** Challenge.trigger_id points to non-existent trigger
**Expected:** Skipped, warning logged

#### Test 17.6: Multiple Tasks Complete Simultaneously
**Setup:** Single action matches multiple challenges on different tiles
**Verify:**
- All matching challenges updated
- All tiles updated
- Correct bingo detection

---

### 18. DATABASE INTEGRITY

#### Test 18.1: Foreign Key Constraints
Verify all relationships maintained:
- Action → Users (player_id)
- TeamMember → Team → Event
- Challenge → Trigger
- ChallengeStatus → Team + Challenge
- ChallengeProof → ChallengeStatus + Action

#### Test 18.2: Unique Constraints
- TileStatus: unique (team_id, tile_id)
- TaskStatus: unique (team_id, task_id)
- ChallengeStatus: unique (team_id, challenge_id)
- ChallengeProof: unique (challenge_status_id, action_id)

#### Test 18.3: Cascade Deletes
Delete a team, verify:
- TileStatus deleted
- TaskStatus deleted
- ChallengeStatus deleted

#### Test 18.4: Transaction Rollback
Force an error mid-process
**Expected:** Changes rolled back

---

### 19. EVENT TIMING

#### Test 19.1: Active Event
**Setup:** Current time within event start_date and end_date
**Verify:** Event found, submissions processed

#### Test 19.2: Event Not Started
**Setup:** Current time before start_date
**Verify:** No event found, empty response

#### Test 19.3: Event Ended
**Setup:** Current time after end_date
**Verify:** No event found, empty response

#### Test 19.4: Multiple Events
**Setup:** Multiple events, only one active
**Verify:** Correct event selected

---

### 20. FIRESTORE INTEGRATION

#### Test 20.1: Firestore Write Success
Submit with valid data
**Verify:**
- Action logged to PostgreSQL
- Drop written to Firestore collection "drops"

#### Test 20.2: Firestore Write Failure
**Setup:** Firestore unavailable
**Verify:**
- PostgreSQL action still created
- Error logged but doesn't fail request

#### Test 20.3: Firestore Data Format
**Verify:** EventLog.to_dict() format correct

---

## Test Execution Checklist

For each test:
- [ ] Prepare test data (users, teams, tiles, tasks, challenges)
- [ ] Record initial state (points, statuses)
- [ ] Submit API request with exact payload
- [ ] Verify database changes:
  - [ ] Actions table
  - [ ] ChallengeStatus table
  - [ ] TaskStatus table
  - [ ] TileStatus table
  - [ ] Team points
  - [ ] ChallengeProof table
- [ ] Verify API response (notifications)
- [ ] Check logs for expected messages
- [ ] Restore from snapshot if needed

---

## Test Tools

### cURL Example
```bash
curl -X POST http://localhost:5000/events/submit \
  -H "Content-Type: application/json" \
  -d '{
    "rsn": "TestPlayer1",
    "id": "123456789",
    "trigger": "Vorkath",
    "type": "KC",
    "quantity": 1
  }'
```

### Database Query Helpers
```sql
-- Check challenge status
SELECT * FROM new_stability.challenge_statuses WHERE team_id = '...';

-- Check task status
SELECT * FROM new_stability.task_statuses WHERE team_id = '...';

-- Check tile status
SELECT * FROM new_stability.tile_statuses WHERE team_id = '...';

-- Check team points
SELECT name, points FROM new_stability.teams WHERE id = '...';

-- Check actions
SELECT * FROM new_stability.actions ORDER BY created_at DESC LIMIT 10;

-- Check proofs
SELECT * FROM new_stability.challenge_proofs WHERE challenge_status_id = '...';
```

---

## Success Criteria

- [ ] All 100+ tests pass
- [ ] No data corruption
- [ ] Points calculated correctly in all scenarios
- [ ] Bingo detection accurate
- [ ] Notifications sent appropriately
- [ ] No unexpected errors in logs
- [ ] Database constraints respected
- [ ] Concurrent submissions handled correctly

---

## Rollback Procedure

After testing:
1. Stop API server
2. Restore database from snapshot/dump
3. Restart API server
4. Verify clean state
