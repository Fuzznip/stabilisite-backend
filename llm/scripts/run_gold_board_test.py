#!/usr/bin/env python3
"""
Gold Board Test - Complete all 75 tasks for Team Zamorak
Based on GOLD_BOARD_TEST_INSTRUCTIONS.md
"""

import requests
import time
from app import app, db
from models.new_events import (
    Event, Team, TeamMember, Tile, Task, Challenge, Trigger,
    TileStatus, TaskStatus, ChallengeStatus
)
from sqlalchemy import func

# Configuration
API_URL = "http://localhost:8000/events/submit"
TEAM_NAME = "Team Zamorak"
TEST_RSN = "joe crab"

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    PURPLE = '\033[95m'
    CYAN = '\033[96m'
    END = '\033[0m'

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

    try:
        response = requests.post(API_URL, json=payload, timeout=5)
        return response.status_code, response.json()
    except Exception as e:
        return None, {"error": str(e)}

def complete_challenge(rsn, challenge, trigger):
    qty = challenge.quantity or 1  # NULL quantity = single completion

    print(f"      Completing: {trigger.name} (qty: {qty})")

    if trigger.type == "KC":
        # KC: batch in groups of 10
        remaining = qty
        while remaining > 0:
            batch_size = min(10, remaining)
            status, _ = submit_event(
                rsn=rsn,
                trigger_name=trigger.name,
                event_type=trigger.type,
                source=trigger.source,
                quantity=batch_size
            )
            if status != 200:
                return False
            remaining -= batch_size
    elif trigger.type == "SKILL":
        # SKILL (XP): batch in groups of 100,000
        remaining = qty
        while remaining > 0:
            batch_size = min(100000, remaining)
            status, _ = submit_event(
                rsn=rsn,
                trigger_name=trigger.name,
                event_type=trigger.type,
                source=trigger.source,
                quantity=batch_size
            )
            if status != 200:
                return False
            remaining -= batch_size
    else:
        # For DROP/other types, submit multiple times if qty > 1
        for _ in range(qty):
            status, _ = submit_event(
                rsn=rsn,
                trigger_name=trigger.name,
                event_type=trigger.type or "DROP",
                source=trigger.source,
                quantity=1
            )
            if status != 200:
                return False

    return True

def complete_task_challenges(team, task, rsn):
    """Complete all challenges for a task"""
    challenges = Challenge.query.filter_by(task_id=task.id).all()

    # Top-level challenges are those without a parent
    top_level = [c for c in challenges if c.parent_challenge_id is None]

    # For each top-level challenge, we need to complete it
    # If it has a trigger_id, complete it directly
    # If it has NO trigger_id, it's a parent - complete ONE of its children
    challenges_to_complete = []

    for challenge in top_level:
        if challenge.trigger_id:
            # Direct challenge with trigger
            challenges_to_complete.append(challenge)
        else:
            # Parent challenge - need to complete enough children to satisfy parent.quantity
            children = Challenge.query.filter_by(parent_challenge_id=challenge.id).all()
            if children:
                target_value = challenge.quantity
                accumulated_value = 0

                # Check if children are repeatable (qty=NULL)
                children_with_triggers = [c for c in children if c.trigger_id]
                children_repeatable = all(child.quantity is None for child in children_with_triggers)

                if children_repeatable and children_with_triggers:
                    # Children are repeatable - cycle through them to reach target
                    child_index = 0
                    while accumulated_value < target_value:
                        child = children_with_triggers[child_index % len(children_with_triggers)]
                        challenges_to_complete.append(child)
                        accumulated_value += child.value or 1
                        child_index += 1
                else:
                    # Process each child - some may have triggers (leaf), some may be parents (intermediate)
                    for child in children:
                        if accumulated_value >= target_value:
                            break

                        if child.trigger_id:
                            # Leaf challenge with trigger - add directly
                            challenges_to_complete.append(child)
                            accumulated_value += child.value or 1
                        else:
                            # Intermediate parent - need to complete ONE of its grandchildren
                            grandchildren = Challenge.query.filter_by(parent_challenge_id=child.id).all()
                            if grandchildren:
                                # Just complete the first grandchild (or first N based on child.quantity)
                                num_grandchildren_needed = child.quantity or 1
                                for gc in grandchildren[:num_grandchildren_needed]:
                                    challenges_to_complete.append(gc)
                                accumulated_value += child.value or 1

                if accumulated_value < target_value:
                    print(
                        f"{Colors.YELLOW}WARNING: Parent {challenge.id} "
                        f"requires {target_value}, but children only provide {accumulated_value}{Colors.END}"
                    )
            else:
                print(f"      {Colors.YELLOW}WARNING: Parent challenge {challenge.id} has no children{Colors.END}")

    print(f"    Challenges to complete: {len(challenges_to_complete)}")

    for idx, challenge in enumerate(challenges_to_complete, 1):
        trigger = Trigger.query.get(challenge.trigger_id)
        if not trigger:
            print(f"      {Colors.RED}ERROR: No trigger found for challenge {challenge.id}{Colors.END}")
            continue

        print(f"      [{idx}/{len(challenges_to_complete)}]", end=" ")
        success = complete_challenge(rsn, challenge, trigger)

        if not success:
            return False

    # Refresh and verify task completion
    db.session.expire_all()
    task_status = TaskStatus.query.filter_by(
        team_id=team.id,
        task_id=task.id
    ).first()

    return task_status and task_status.completed

def check_for_bingos(team):
    """Check if team has completed any bingos (rows or columns)"""
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

    return {
        "total": total_bingos,
        "rows": completed_rows,
        "cols": completed_cols,
        "expected_points": expected_bingo_points
    }

def verify_tile_status(team, tile, task_num, expected_points):
    """Verify tile status after completing a task"""
    tile_status = TileStatus.query.filter_by(
        team_id=team.id,
        tile_id=tile.id
    ).first()

    db.session.refresh(team)

    # Determine medal level
    medal = ""
    if tile_status:
        if tile_status.tasks_completed == 1:
            medal = f"{Colors.YELLOW}Bronze ⭐{Colors.END}"
        elif tile_status.tasks_completed == 2:
            medal = f"{Colors.CYAN}Silver ⭐⭐{Colors.END}"
        elif tile_status.tasks_completed == 3:
            medal = f"{Colors.PURPLE}Gold ⭐⭐⭐{Colors.END}"

    tasks_completed = tile_status.tasks_completed if tile_status else 0

    print(f"    {Colors.GREEN}✓{Colors.END} Tile {tile.index}: {tasks_completed}/3 tasks | {medal} | Team points: {team.points}")

    # Check for bingos
    bingos = check_for_bingos(team)
    if bingos["total"] > 0:
        print(f"      {Colors.PURPLE}🎉 BINGO!{Colors.END} Total: {bingos['total']} (Rows: {bingos['rows']}, Cols: {bingos['cols']}) | Bonus: {bingos['expected_points']} pts")

    return tasks_completed == task_num

def main():
    print(f"\n{Colors.BLUE}{'='*80}{Colors.END}")
    print(f"{Colors.BLUE}🎯 GOLD BOARD TEST - TEAM ZAMORAK{Colors.END}")
    print(f"{Colors.BLUE}Goal: Complete all 75 tasks (25 tiles × 3 tasks) for a full gold board{Colors.END}")
    print(f"{Colors.BLUE}{'='*80}{Colors.END}\n")

    with app.app_context():
        # Get team
        team = Team.query.filter_by(name=TEAM_NAME).first()
        if not team:
            print(f"{Colors.RED}ERROR: Team '{TEAM_NAME}' not found!{Colors.END}")
            return

        print(f"{Colors.GREEN}✓{Colors.END} Team found: {team.name} (ID: {team.id})")
        print(f"  Event ID: {team.event_id}")
        print(f"  Starting points: {team.points}\n")

        # Get all tiles for this event
        tiles = Tile.query.filter_by(event_id=team.event_id).order_by(Tile.index).all()
        print(f"{Colors.GREEN}✓{Colors.END} Found {len(tiles)} tiles\n")

        if len(tiles) != 25:
            print(f"{Colors.YELLOW}WARNING: Expected 25 tiles, found {len(tiles)}{Colors.END}\n")

        # Track progress
        total_tasks_completed = 0
        expected_points = team.points
        tiles_completed = 0

        start_time = time.time()

        # Complete all tiles
        for tile_idx, tile in enumerate(tiles, 1):
            print(f"\n{Colors.CYAN}{'─'*80}{Colors.END}")
            print(f"{Colors.CYAN}TILE {tile.index}/{len(tiles)-1}: {tile.name}{Colors.END}")
            print(f"{Colors.CYAN}{'─'*80}{Colors.END}")

            tasks = Task.query.filter_by(tile_id=tile.id).all()
            print(f"  Tasks on this tile: {len(tasks)}")

            if len(tasks) != 3:
                print(f"  {Colors.YELLOW}WARNING: Expected 3 tasks, found {len(tasks)}{Colors.END}")

            # Complete each task on this tile
            for task_num, task in enumerate(tasks, 1):
                print(f"\n  {Colors.BLUE}Task {task_num}/3:{Colors.END} (ID: {task.id}, require_all={task.require_all})")

                # Complete the task
                success = complete_task_challenges(team, task, rsn=TEST_RSN)

                if success:
                    total_tasks_completed += 1
                    expected_points += 3

                    # Verify after each task
                    verified = verify_tile_status(team, tile, task_num, expected_points)

                    if not verified:
                        print(f"    {Colors.RED}✗ Verification failed!{Colors.END}")
                else:
                    print(f"    {Colors.RED}✗ Task {task_num} failed to complete!{Colors.END}")
                    print(f"    Stopping test at Tile {tile.index}, Task {task_num}")
                    return

            # After all 3 tasks on this tile
            tiles_completed += 1
            print(f"\n  {Colors.GREEN}✓ Tile {tile.index} COMPLETE: Gold medal ⭐⭐⭐{Colors.END}")

            # Progress update
            elapsed = time.time() - start_time
            avg_time_per_tile = elapsed / tiles_completed
            remaining_tiles = len(tiles) - tiles_completed
            estimated_remaining = avg_time_per_tile * remaining_tiles

            print(f"\n  Progress: {tiles_completed}/{len(tiles)} tiles | {total_tasks_completed}/75 tasks | {elapsed:.1f}s elapsed | ~{estimated_remaining:.1f}s remaining")

        # =====================================================================
        # FINAL VERIFICATION
        # =====================================================================

        total_time = time.time() - start_time

        print(f"\n\n{Colors.PURPLE}{'='*80}{Colors.END}")
        print(f"{Colors.PURPLE}🏆 FINAL RESULTS - TEAM ZAMORAK{Colors.END}")
        print(f"{Colors.PURPLE}{'='*80}{Colors.END}\n")

        # Refresh team data
        db.session.refresh(team)

        # Count tile statuses
        tile_statuses = TileStatus.query.filter_by(team_id=team.id).all()

        bronze_tiles = sum(1 for ts in tile_statuses if ts.tasks_completed == 1)
        silver_tiles = sum(1 for ts in tile_statuses if ts.tasks_completed == 2)
        gold_tiles = sum(1 for ts in tile_statuses if ts.tasks_completed == 3)

        print(f"{Colors.BLUE}Tile Status Breakdown:{Colors.END}")
        print(f"  {Colors.YELLOW}Bronze (1 task):{Colors.END}  {bronze_tiles}")
        print(f"  {Colors.CYAN}Silver (2 tasks):{Colors.END} {silver_tiles}")
        print(f"  {Colors.PURPLE}Gold (3 tasks):{Colors.END}   {gold_tiles}")
        print(f"  {Colors.GREEN}Total tiles:{Colors.END}      {len(tile_statuses)} (expected: 25)")

        # All gold?
        all_gold = (gold_tiles == 25)
        status = f"{Colors.GREEN}✓{Colors.END}" if all_gold else f"{Colors.RED}✗{Colors.END}"
        print(f"\n{status} All tiles gold: {all_gold}")

        # Check bingos
        print(f"\n{Colors.BLUE}Bingo Detection:{Colors.END}")
        bingos = check_for_bingos(team)
        print(f"  Completed rows: {bingos['rows']}")
        print(f"  Completed cols: {bingos['cols']}")
        print(f"  Total bingos: {bingos['total']} (expected: 10)")
        print(f"  Expected bonus: {bingos['expected_points']} points")

        # Points breakdown
        task_points = total_tasks_completed * 3
        expected_bingo_bonus = 10 * 15  # 150
        expected_total = task_points + expected_bingo_bonus  # 375

        print(f"\n{Colors.BLUE}Points Breakdown:{Colors.END}")
        print(f"  Task points:    {task_points} ({total_tasks_completed} tasks × 3 points)")
        print(f"  Bingo bonus:    {expected_bingo_bonus} (expected: 10 bingos × 15 points)")
        print(f"  Expected total: {expected_total}")
        print(f"  Actual total:   {team.points}")

        points_match = (team.points == expected_total)
        status = f"{Colors.GREEN}✓{Colors.END}" if points_match else f"{Colors.RED}✗{Colors.END}"
        print(f"\n{status} Points match expected: {points_match}")

        if not points_match:
            diff = team.points - expected_total
            print(f"  Difference: {diff:+d} points")

        # Time stats
        print(f"\n{Colors.BLUE}Performance:{Colors.END}")
        print(f"  Total time: {total_time:.1f}s ({total_time/60:.1f} minutes)")
        print(f"  Avg per task: {total_time/total_tasks_completed:.2f}s")
        print(f"  Avg per tile: {total_time/tiles_completed:.2f}s")

        # Final success check
        print(f"\n{Colors.PURPLE}{'='*80}{Colors.END}")
        if all_gold and bingos["total"] == 10 and points_match:
            print(f"{Colors.GREEN}✓✓✓ ALL TESTS PASSED! GOLD BOARD COMPLETE! ✓✓✓{Colors.END}")
        else:
            print(f"{Colors.YELLOW}⚠ Some checks failed - review results above{Colors.END}")
        print(f"{Colors.PURPLE}{'='*80}{Colors.END}\n")

if __name__ == "__main__":
    main()
