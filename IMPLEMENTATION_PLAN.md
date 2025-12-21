# Action Processing Implementation Plan

## Confirmed Decisions

1. ✅ Add `thread_id` to Event model
2. ✅ Add `image_url` to Team model
3. ✅ Use hierarchical challenges (Option B) - one trigger per challenge, use parent_challenge_id for OR/AND logic
4. ✅ Keep writing to Firestore (TODO: revisit later)
5. ✅ Fix bingo detection bug
6. ✅ Implement nested challenge evaluation (require_all logic)

---

## Implementation Components

### 1. **Action Processor Service** (`services/action_processor.py`)
Main entry point for processing actions.

**Responsibilities:**
- Receive action (player_id, name, source, quantity)
- Find all active events
- For each event, find player's team
- Match action to event triggers
- Update statuses (challenge → task → tile)
- Award points
- Create audit trail (ChallengeProof)
- Return notifications

---

### 2. **Challenge Evaluator** (`services/challenge_evaluator.py`)
Handles hierarchical challenge logic.

**Responsibilities:**
- Evaluate if challenge is completed
- Support OR logic (require_all=False): Any child completes = parent completes
- Support AND logic (require_all=True): All children complete = parent completes
- Recursive evaluation for nested parents
- Handle leaf challenges (direct trigger match)

---

### 3. **Bingo Service** (`services/bingo_service.py`)
Bingo-specific logic.

**Responsibilities:**
- Detect bingo completions (rows/columns at same medal level)
- Award bonus points (15 per bingo)
- Generate bingo notifications
- **Fixed bug**: Check ALL tiles have same level, not just minimum

---

### 4. **Notification Builder** (`services/notification_builder.py`)
Generate Discord notifications.

**Responsibilities:**
- Task completion notifications
- Bingo notifications (single, double, anomaly)
- Format with team info, points, tile names
- Use event.thread_id for routing

---

## Processing Flow

```
POST /api/v2/actions
  └─> ActionProcessor.process()
       │
       ├─> 1. Create Action record
       │
       ├─> 2. Find active events (start_date <= now <= end_date)
       │
       ├─> 3. For each active event:
       │    │
       │    ├─> 3.1. Find player's team
       │    │    - Lookup user by discord_id (from player_id)
       │    │    - Find TeamMember by user_id + event
       │    │
       │    ├─> 3.2. Match action to triggers
       │    │    - Case-insensitive trigger name matching
       │    │    - Wildcard source matching (empty = any)
       │    │    - Get all challenges with matching trigger
       │    │
       │    ├─> 3.3. For each matched challenge:
       │    │    │
       │    │    ├─> Update ChallengeStatus
       │    │    │    - Upsert (team_id, challenge_id)
       │    │    │    - Increment quantity
       │    │    │    - Mark completed if quantity >= challenge.quantity
       │    │    │    - Create ChallengeProof(challenge_status_id, action_id)
       │    │    │
       │    │    ├─> Evaluate parent challenges (if any)
       │    │    │    - ChallengeEvaluator.evaluate_challenge()
       │    │    │    - Recursive check up the tree
       │    │    │    - Update parent ChallengeStatus
       │    │    │
       │    │    ├─> Check if task completed
       │    │    │    - If challenge.task_id not null:
       │    │    │      - ChallengeEvaluator.is_task_complete(task_id, team_id)
       │    │    │      - Check task.require_all:
       │    │    │        - False (OR): ANY challenge complete = task complete
       │    │    │        - True (AND): ALL challenges complete = task complete
       │    │    │    - Update TaskStatus if newly completed
       │    │    │    - Return task_id if newly completed
       │    │    │
       │    │    └─> If task completed:
       │    │         │
       │    │         ├─> Update TileStatus
       │    │         │    - Upsert (team_id, tile_id)
       │    │         │    - Increment tasks_completed (0→1→2→3)
       │    │         │    - Award 3 points to team
       │    │         │
       │    │         └─> Track completed tile for bingo check
       │    │
       │    └─> 3.4. Check for bingos
       │         - BingoService.check_bingos(event_id, team_id, completed_tiles)
       │         - For each newly completed medal level:
       │           - Check all rows for full completion at that level
       │           - Check all columns for full completion at that level
       │         - Award 15 points per bingo
       │         - Track bingo count
       │
       └─> 4. Generate notifications
            - If bingo_count > 0: Bingo notification
            - Else if task completed: Task notification
            - Else: Silent (no notification)
```

---

## Data Structures

### ChallengeStatus
```python
{
    "team_id": UUID,
    "challenge_id": UUID,
    "quantity": int,           # Total accumulated
    "completed": bool,         # quantity >= challenge.quantity
    "created_at": datetime,
    "updated_at": datetime
}
```

### TaskStatus
```python
{
    "team_id": UUID,
    "task_id": UUID,
    "completed": bool,         # Based on task.require_all logic
    "created_at": datetime,
    "updated_at": datetime
}
```

### TileStatus
```python
{
    "team_id": UUID,
    "tile_id": UUID,
    "tasks_completed": int,    # 0=none, 1=bronze, 2=silver, 3=gold
    "created_at": datetime,
    "updated_at": datetime
}
```

### ChallengeProof
```python
{
    "challenge_status_id": UUID,
    "action_id": UUID,
    "created_at": datetime
}
```

---

## Challenge Hierarchy Examples

### Example 1: Simple OR (Get any ToA purple)
```
Task: "Get 3 ToA purples"
  └─ Parent Challenge (require_all=False, trigger_id=null, quantity=3)
      ├─ Child: Shadow (trigger_id=shadow_uuid, quantity=3)
      ├─ Child: Lightbearer (trigger_id=light_uuid, quantity=3)
      ├─ Child: Masori (trigger_id=masori_uuid, quantity=3)
      └─ Child: Ward (trigger_id=ward_uuid, quantity=3)

Logic: Parent completes when ANY child reaches quantity 3
```

### Example 2: AND Logic (Get specific items)
```
Task: "Get 2 shadows AND 1 lightbearer"
  └─ Parent Challenge (require_all=True, trigger_id=null, quantity=1)
      ├─ Child: Shadow (trigger_id=shadow_uuid, quantity=2)
      └─ Child: Lightbearer (trigger_id=light_uuid, quantity=1)

Logic: Parent completes when ALL children complete
```

### Example 3: Complex Nested ((A AND B) OR C)
```
Task: "Hard ToA challenge"
  └─ OR Parent (require_all=False)
      ├─ AND Parent (require_all=True)
      │   ├─ Shadow x2
      │   └─ Lightbearer x1
      └─ Single Child: Any purple x5

Logic: Complete if (Shadow x2 AND Light x1) OR (Any purple x5)
```

---

## Key Algorithms

### Algorithm 1: Evaluate Challenge Completion
```python
def evaluate_challenge(challenge_id, team_id):
    """Recursively evaluate if challenge is complete"""
    challenge = Challenge.query.get(challenge_id)
    status = ChallengeStatus.query.filter_by(
        challenge_id=challenge_id,
        team_id=team_id
    ).first()

    # Leaf challenge (has trigger)
    if challenge.trigger_id:
        if not status:
            return False
        return status.quantity >= challenge.quantity

    # Parent challenge (no trigger, has children)
    children = Challenge.query.filter_by(parent_challenge_id=challenge_id).all()

    if challenge.require_all:  # AND logic
        return all(evaluate_challenge(child.id, team_id) for child in children)
    else:  # OR logic
        return any(evaluate_challenge(child.id, team_id) for child in children)
```

### Algorithm 2: Check Task Completion
```python
def is_task_complete(task_id, team_id):
    """Check if task is complete based on its challenges"""
    task = Task.query.get(task_id)

    # Get all ROOT challenges for this task (parent_challenge_id is null)
    root_challenges = Challenge.query.filter_by(
        task_id=task_id,
        parent_challenge_id=None
    ).all()

    # Evaluate each root challenge
    results = [evaluate_challenge(c.id, team_id) for c in root_challenges]

    if task.require_all:  # AND logic
        return all(results)
    else:  # OR logic
        return any(results)
```

### Algorithm 3: Fixed Bingo Detection
```python
def check_bingos(event_id, team_id, new_medal_level):
    """Check for newly completed bingos at the specified medal level"""
    # Get all tile statuses for this team
    statuses = TileStatus.query.join(Tile).filter(
        Tile.event_id == event_id,
        TileStatus.team_id == team_id
    ).all()

    # Build 5x5 grid
    grid = [[0]*5 for _ in range(5)]
    for ts in statuses:
        tile = Tile.query.get(ts.tile_id)
        row, col = tile.index // 5, tile.index % 5
        grid[row][col] = ts.tasks_completed

    bingo_count = 0

    # Check rows: ALL tiles in row must have >= new_medal_level
    for row in grid:
        if all(level >= new_medal_level for level in row):
            bingo_count += 1

    # Check columns: ALL tiles in column must have >= new_medal_level
    for col in range(5):
        if all(grid[row][col] >= new_medal_level for row in range(5)):
            bingo_count += 1

    return bingo_count
```

---

## Reminder: Firestore
TODO: Come back to evaluate if we still need Firestore writes

---

## Next Steps
1. Implement ActionProcessor service
2. Implement ChallengeEvaluator service
3. Implement BingoService
4. Implement NotificationBuilder
5. Wire up to /api/v2/actions endpoint
6. Test with sample data
