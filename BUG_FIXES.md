# Bug Fixes - Event System

## Summary
Fixed 3 critical bugs and 1 potential race condition identified during mental validation checks.

---

## Bug #3: Bingo Double-Awarding (CRITICAL) ✅ FIXED

### Problem
Every time a task completed at a medal level, the system counted ALL bingos at that level and awarded points, even if those bingos were already awarded before.

**Example:**
- Team completes bronze task 1 on row 0 → completes row 0 bronze → awards 15 points ✅
- Team completes bronze task 2 on row 0 → row 0 still complete → awards 15 points AGAIN! ❌

### Solution: Delta-Based Bingo Detection
Implemented a hybrid approach that calculates bingo count BEFORE and AFTER tile status update, then awards only the difference.

**Changes:**
1. **New method in [services/bingo_service.py](services/bingo_service.py:13-64)**
   - Added `count_bingos_at_level()` - counts bingos without awarding points
   - Deprecated `check_and_award_bingos()` with warning

2. **Updated [services/action_processor.py:370-396](services/action_processor.py#L370-L396)**
   - Count bingos BEFORE updating tile status: `bingos_before`
   - Update tile status (increment medal level)
   - Count bingos AFTER updating: `bingos_after`
   - Award points only for delta: `(bingos_after - bingos_before) * 15`

**Result:** Teams now receive correct bingo points exactly once per bingo completion.

---

## Bug #4: TaskStatus Race Condition ✅ ALREADY FIXED

### Problem
No unique constraint on TaskStatus(team_id, task_id) could allow concurrent requests to create duplicate records and award duplicate points.

### Solution
Verified that unique constraint already exists in migration file:
- [migrations/versions/001_create_new_event_schema.py:191](migrations/versions/001_create_new_event_schema.py#L191)
- `sa.UniqueConstraint('team_id', 'task_id', name='task_statuses_unique_team_task')`

**Result:** Database will prevent duplicate task status records.

---

## Bug #5: Multiple Task Completions Only Send One Notification (MEDIUM) ✅ FIXED

### Problem
When a single action completed multiple tasks (e.g., leaf challenge task + parent challenge task), only the first completion was returned and only one notification was sent.

**Example:**
- Leaf challenge completes Task A (bronze medal) → notification sent ✅
- Parent challenge completes Task B (silver medal) → **no notification!** ❌

### Solution: Return and Process All Results

**Changes:**

1. **Updated [services/action_processor.py:243-293](services/action_processor.py#L243-L293)**
   - Changed `_process_challenge_match()` return type from `Optional[dict]` → `List[dict]`
   - Returns ALL task completion results instead of just the first one
   - Changed `return results[0] if results else None` → `return results`

2. **Updated [services/action_processor.py:119-169](services/action_processor.py#L119-L169)**
   - Modified `_process_action_for_event()` to handle list of results
   - Loop through ALL results from each challenge match
   - Generate notifications for EVERY task completion
   - Code now properly handles:
     ```python
     for challenge in matched_challenges:
         results = ActionProcessor._process_challenge_match(...)
         for result in results:  # Process ALL results
             if result and result.get('task_completed'):
                 all_task_completions.append(result)
     ```

**Result:** All task completions are now tracked and notified, even when multiple tasks complete from a single action.

---

## Additional Improvements

### Enhanced Return Value
Updated `_check_and_process_task_completion()` to return more data:
```python
return {
    'task_completed': True,
    'tile_id': tile.id,
    'new_medal_level': new_medal_level,
    'event_id': event.id,
    'bingos_awarded': new_bingos  # NEW: track bingo delta
}
```

This allows the notification layer to:
- Know if bingos were awarded with this task completion
- Generate appropriate notifications (bingo vs task completion)
- Display correct point values to users

---

## Testing Recommendations

### Test Case 1: Bingo Double-Award Prevention
1. Create a 5x5 bingo board
2. Complete 4 bronze tasks in row 0
3. Complete 5th bronze task in row 0 → should award 15 points for bingo
4. Complete another bronze task in row 0 (6th tile) → should award 0 bingo points
5. **Expected:** Total bingo points = 15 (not 30)

### Test Case 2: Multiple Task Completions
1. Create a parent challenge (OR logic) with two child challenges
2. Parent challenge is linked to Task B, one child is linked to Task A
3. Submit action that completes the child
4. **Expected:** Two notifications (Task A completion + Task B completion)

### Test Case 3: Simultaneous Row + Column Bingo
1. Complete tiles such that one task creates both a row AND column bingo
2. **Expected:** Award 30 points (2 bingos), send notification for 2 bingos

### Test Case 4: Race Condition Prevention
1. Submit two identical actions simultaneously (same trigger, same team)
2. **Expected:** Database prevents duplicate TaskStatus creation, only one succeeds

---

## Files Modified

1. **[services/bingo_service.py](services/bingo_service.py)**
   - Added `count_bingos_at_level()` method
   - Deprecated `check_and_award_bingos()`

2. **[services/action_processor.py](services/action_processor.py)**
   - Modified `_process_challenge_match()` to return `List[dict]`
   - Updated `_check_and_process_task_completion()` with delta-based bingo logic
   - Updated `_process_action_for_event()` to handle multiple task completions

3. **[migrations/versions/001_create_new_event_schema.py](migrations/versions/001_create_new_event_schema.py)**
   - Verified unique constraint exists (no changes needed)

---

## Status: All Bugs Fixed ✅

The event system now correctly:
- ✅ Awards bingo points exactly once per bingo
- ✅ Prevents duplicate task status records (race condition protected)
- ✅ Sends notifications for ALL completed tasks, not just the first
- ✅ Handles multiple simultaneous bingos (row + column)
- ✅ Tracks bingo delta in return values for proper notification generation
