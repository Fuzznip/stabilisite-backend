# Team Zamorak Gold Board Test Instructions

## Objective
Complete all 75 tasks (3 tasks per tile × 25 tiles) for Team Zamorak to achieve a full gold board and verify:
- Points calculation (3 points per task = 225 points total)
- Tile status progression (Bronze → Silver → Gold)
- Bingo detection (5 rows + 5 columns = 10 bingos)
- Bingo bonus points (15 points per bingo = 150 points)
- **Expected final score: 375 points** (225 from tasks + 150 from bingos)

## Prerequisites
1. Database is in clean state (run `reset_test_data.py` if needed)
2. Flask API is running on port 8000
3. Team Zamorak exists with team members
4. Winter Bingo 2026 event is active with 25 tiles (indices 0-24)

## Test Strategy
For each tile (0-24):
1. Query the database to find all 3 tasks for that tile
2. For each task, find all required challenges
3. Submit actions to complete each challenge
4. After EACH task completion, verify:
   - Task marked as completed
   - Tile status updated (tasks_completed incremented)
   - Team points increased by 3
   - Tile reaches Bronze (1 task), Silver (2 tasks), or Gold (3 tasks)
5. After completing rows/columns, verify bingo detection and 15-point bonuses

## Step-by-Step Process

### Step 1: Get Tile and Task Information
```python
from app import app, db
from models.new_events import Tile, Task, Challenge, Trigger, Team

with app.app_context():
    team = Team.query.filter_by(name="Team Zamorak").first()
    event_id = team.event_id

    # Get all 25 tiles for this event, ordered by index
    tiles = Tile.query.filter_by(event_id=event_id).order_by(Tile.index).all()

    for tile in tiles:
        print(f"\nTile {tile.index}: {tile.name}")
        tasks = Task.query.filter_by(tile_id=tile.id).all()
        print(f"  Total tasks: {len(tasks)}")

        for i, task in enumerate(tasks, 1):
            print(f"  Task {i}: {task.id}")
            challenges = Challenge.query.filter_by(task_id=task.id).all()
            top_level = [c for c in challenges if c.parent_challenge_id is None]
            print(f"    Challenges: {len(top_level)}, require_all={task.require_all}")
```

### Step 2: Complete Each Task Systematically

For each tile (0-24), complete all 3 tasks:

```python
import requests

def submit_event(rsn, trigger_name, event_type, source=None, quantity=1):
    """Submit an event action via API"""
    payload = {
        "rsn": rsn,
        "trigger": trigger_name,
        "type": event_type,
        "quantity": quantity
    }
    if source:
        payload["source"] = source

    response = requests.post("http://localhost:8000/events/submit", json=payload)
    return response.status_code, response.json()

def complete_challenge(rsn, challenge, trigger):
    """Complete a single challenge by submitting required quantity"""
    for i in range(challenge.quantity):
        status, response = submit_event(
            rsn=rsn,
            trigger_name=trigger.name,
            event_type=trigger.type or "DROP",
            source=trigger.source,
            quantity=1
        )
    return status, response

def complete_task(team, task, rsn="joe crab"):
    """Complete a single task (all its challenges)"""
    challenges = Challenge.query.filter_by(task_id=task.id).all()
    top_level = [c for c in challenges if c.parent_challenge_id is None]

    for challenge in top_level:
        trigger = Trigger.query.get(challenge.trigger_id)
        if trigger:
            complete_challenge(rsn, challenge, trigger)

            # For parent-child structures, check if parent completed
            if challenge.parent_challenge_id:
                parent = Challenge.query.get(challenge.parent_challenge_id)
                # Parent updates automatically when child completes

    # Verify task completion
    from models.new_events import TaskStatus
    task_status = TaskStatus.query.filter_by(
        team_id=team.id,
        task_id=task.id
    ).first()

    return task_status and task_status.completed
```

### Step 3: Verification After Each Task

After completing each task, run these checks:

```python
def verify_task_completion(team, tile, expected_tasks_completed, expected_points):
    """Verify task completion and tile status after each task"""
    from models.new_events import TileStatus

    # 1. Check tile status
    tile_status = TileStatus.query.filter_by(
        team_id=team.id,
        tile_id=tile.id
    ).first()

    print(f"\n✓ Verification for Tile {tile.index}:")
    print(f"  Tasks completed: {tile_status.tasks_completed if tile_status else 0}/{expected_tasks_completed}")

    # 2. Check team points
    db.session.refresh(team)
    print(f"  Team points: {team.points} (expected: {expected_points})")

    # 3. Check medal level
    if tile_status:
        if tile_status.tasks_completed == 1:
            print(f"  Medal: Bronze ⭐")
        elif tile_status.tasks_completed == 2:
            print(f"  Medal: Silver ⭐⭐")
        elif tile_status.tasks_completed == 3:
            print(f"  Medal: Gold ⭐⭐⭐")

    # 4. Check for bingos (after each task)
    check_for_bingos(team)

    return True

def check_for_bingos(team):
    """Check if team has completed any bingos (rows or columns)"""
    from models.new_events import TileStatus, Tile

    tile_statuses = TileStatus.query.filter_by(team_id=team.id).all()

    # Build set of completed tile indices (at least bronze)
    completed_indices = set()
    for ts in tile_statuses:
        if ts.tasks_completed >= 1:
            tile = Tile.query.get(ts.tile_id)
            if tile:
                completed_indices.add(tile.index)

    # Check rows
    completed_rows = []
    for row in range(5):
        row_start = row * 5
        if all(row_start + col in completed_indices for col in range(5)):
            completed_rows.append(row)

    # Check columns
    completed_cols = []
    for col in range(5):
        if all(col + (row * 5) in completed_indices for row in range(5)):
            completed_cols.append(col)

    total_bingos = len(completed_rows) + len(completed_cols)
    expected_bingo_points = total_bingos * 15

    if total_bingos > 0:
        print(f"\n🎉 BINGO! Completed bingos: {total_bingos}")
        print(f"  Rows: {completed_rows}")
        print(f"  Columns: {completed_cols}")
        print(f"  Bingo bonus points: {expected_bingo_points}")
```

### Step 4: Full Test Execution

```python
with app.app_context():
    team = Team.query.filter_by(name="Team Zamorak").first()
    tiles = Tile.query.filter_by(event_id=team.event_id).order_by(Tile.index).all()

    total_tasks_completed = 0
    expected_points = 0

    # Complete all tiles
    for tile in tiles:
        print(f"\n{'='*70}")
        print(f"TILE {tile.index}: {tile.name}")
        print(f"{'='*70}")

        tasks = Task.query.filter_by(tile_id=tile.id).all()

        for task_num, task in enumerate(tasks, 1):
            print(f"\n  Task {task_num}/3 for Tile {tile.index}...")

            # Complete the task
            success = complete_task(team, task, rsn="joe crab")

            if success:
                total_tasks_completed += 1
                expected_points += 3

                print(f"  ✓ Task {task_num} completed!")

                # Verify after each task
                verify_task_completion(team, tile, task_num, expected_points)
            else:
                print(f"  ✗ Task {task_num} failed!")
                break

        # After all 3 tasks on this tile
        print(f"\n  Tile {tile.index} complete: Gold medal ⭐⭐⭐")
```

### Step 5: Final Verification

After completing all 75 tasks:

```python
with app.app_context():
    team = Team.query.filter_by(name="Team Zamorak").first()
    db.session.refresh(team)

    print(f"\n{'='*70}")
    print(f"FINAL RESULTS - TEAM ZAMORAK")
    print(f"{'='*70}")

    # 1. Count tile statuses
    from models.new_events import TileStatus
    tile_statuses = TileStatus.query.filter_by(team_id=team.id).all()

    bronze_tiles = sum(1 for ts in tile_statuses if ts.tasks_completed == 1)
    silver_tiles = sum(1 for ts in tile_statuses if ts.tasks_completed == 2)
    gold_tiles = sum(1 for ts in tile_statuses if ts.tasks_completed == 3)

    print(f"\nTile Status Breakdown:")
    print(f"  Bronze (1 task): {bronze_tiles}")
    print(f"  Silver (2 tasks): {silver_tiles}")
    print(f"  Gold (3 tasks): {gold_tiles}")
    print(f"  Total tiles: {len(tile_statuses)} (expected: 25)")

    # 2. Verify all gold
    all_gold = (gold_tiles == 25)
    print(f"\n✓ All tiles gold: {all_gold}")

    # 3. Check bingos
    check_for_bingos(team)

    # 4. Final points
    task_points = 75 * 3  # 225
    bingo_points = 10 * 15  # 150 (5 rows + 5 columns)
    expected_total = task_points + bingo_points  # 375

    print(f"\nPoints Breakdown:")
    print(f"  Task points: {team.points} (expected: {task_points} from 75 tasks)")
    print(f"  Bingo bonus: expected {bingo_points} (10 bingos × 15 points)")
    print(f"  Total expected: {expected_total}")
    print(f"  Actual total: {team.points}")
    print(f"\n{'✓' if team.points == expected_total else '✗'} Points match expected!")
```

## Expected Outcomes

### Progressive Milestones
- **After 1st task per tile (25 tasks)**: 25 bronze tiles, 75 points
- **After 2nd task per tile (50 tasks)**: 25 silver tiles, 150 points
- **After 1st row complete (5 tiles × 3 tasks = 15 tasks)**: 1st bingo, +15 points
- **After all rows/cols (75 tasks)**: 25 gold tiles, 10 bingos, 375 points

### Final Board State
```
Points: 375
  - Task points: 225 (75 tasks × 3 points)
  - Bingo bonus: 150 (10 bingos × 15 points)

Tiles: 25 gold medals ⭐⭐⭐

Bingos: 10
  - 5 rows (indices 0-4, 5-9, 10-14, 15-19, 20-24)
  - 5 columns (indices 0,5,10,15,20 | 1,6,11,16,21 | etc.)
```

## Troubleshooting

### If a task doesn't complete:
1. Check if it's an AND task (require_all=True) - all challenges must be completed
2. Verify trigger names and sources match exactly
3. Check parent-child relationships - parent updates when ALL children complete
4. Ensure user "joe crab" is a member of Team Zamorak

### If points don't increment:
1. Verify task actually completed (check TaskStatus.completed)
2. Check if tile status was created/updated
3. Ensure team.points is being refreshed from database

### If bingos aren't detected:
1. Verify tiles have tasks_completed >= 1 (bronze minimum)
2. Check tile.index values are 0-24
3. Ensure bingo detection logic is running after tile completions

## User Selection for Actions

Use Team Zamorak members for submissions:
- joe crab
- VintageSheep
- Anglicanism
- (Add more Team Zamorak members as needed)

Rotate between users to simulate real event activity.

## Time Estimate

- **Per task**: ~5-10 seconds (API calls + verification)
- **75 tasks total**: ~10-15 minutes
- **With verification pauses**: ~20-30 minutes

## Success Criteria

✅ All 25 tiles have 3 tasks completed (gold medals)
✅ Team Zamorak has 225 points from tasks
✅ 10 bingos detected (5 rows + 5 columns)
✅ 150 bonus points from bingos
✅ Final total: 375 points
✅ All tile statuses created correctly
✅ No cross-team contamination
✅ Database integrity maintained
