#!/usr/bin/env python3
"""
Test parent challenge patterns - nested requirements
Example: "Get 2 of the following items: (Twisted Bow, Dragon Hunter Lance, Dragon Crossbow)"
"""

import datetime
from datetime import timezone, timedelta
from app import app, db
from models.new_events import Event, Team, TeamMember, Trigger, Tile, Task, Challenge, TileStatus, TaskStatus, ChallengeStatus
from models.models import Users
from event_handlers.bingo.bingo import bingo_handler
from event_handlers.event_handler import EventSubmission

def submit_action(user, action_name, action_type, source=None, quantity=1):
    """Submit an action via the bingo handler"""
    submission = EventSubmission(
        rsn=user.runescape_name,
        id=user.discord_id,
        trigger=action_name,
        type=action_type,
        source=source,
        quantity=quantity,
        totalValue=0
    )

    print(f"📤 Submitting: {action_type} - {action_name} x{quantity}" +
          (f" from {source}" if source else ""))

    result = bingo_handler(submission)

    if result:
        print(f"✅ Notification: {result[0].title}")
        return True
    else:
        print(f"   (Progress updated)")
        return False

def main():
    print("\n" + "="*70)
    print("🧪 PARENT CHALLENGE PATTERN TESTS")
    print("="*70 + "\n")

    with app.app_context():
        # Get event and team
        event = Event.query.filter_by(name="Winter Bingo 2026").first()
        if not event:
            print("❌ No bingo event found!")
            return

        team = Team.query.filter_by(event_id=event.id).first()
        if not team:
            print("❌ No teams found!")
            return

        members = TeamMember.query.filter_by(team_id=team.id).all()
        users = [Users.query.get(m.user_id) for m in members[:3]]

        print(f"✅ Using event: {event.name}")
        print(f"✅ Using team: {team.name}")
        print(f"✅ Test users: {', '.join(u.runescape_name for u in users)}\n")

        # Use existing CoX Purples tile with parent challenge
        print("="*70)
        print("USING EXISTING TILE: CoX Purples")
        print("="*70)
        print("Pattern: 'Get 2 of 3 CoX Mega Rares (Tbow, DHCB, Lance)'\n")

        tile = Tile.query.filter_by(event_id=event.id, name="CoX Purples").first()
        if not tile:
            print("❌ CoX Purples tile not found!")
            return

        task = Task.query.filter_by(tile_id=tile.id).first()
        if not task:
            print("❌ Task not found!")
            return

        # Get parent and child challenges
        all_challenges = Challenge.query.filter_by(task_id=task.id).all()
        parent_challenge = next((c for c in all_challenges if c.parent_challenge_id is None), None)
        child_challenges = [c for c in all_challenges if c.parent_challenge_id is not None]

        if not parent_challenge or len(child_challenges) != 3:
            print(f"❌ Expected 1 parent and 3 children, got {1 if parent_challenge else 0} parent and {len(child_challenges)} children")
            return

        print(f"✅ Found tile: {tile.name}")
        print(f"✅ Parent challenge: Need {parent_challenge.quantity} of {len(child_challenges)} items")
        print(f"✅ Child challenges: Tbow, Lance, DHCB\n")

        print("="*70)
        print("TEST 1: Parent Challenge - Get 1 of 3 Items (Should NOT Complete)")
        print("="*70 + "\n")

        print("🎯 Getting Twisted Bow (1/3 items)...")
        submit_action(users[0], "Twisted Bow", "DROP", "Chambers of Xeric", 1)

        # Check task status
        task_status = TaskStatus.query.filter_by(team_id=team.id, task_id=task.id).first()
        print(f"\nTask completed: {task_status.completed if task_status else False}")
        print(f"Expected: False (need 2 items, only have 1)\n")

        print("="*70)
        print("TEST 2: Parent Challenge - Get 2 of 3 Items (Should Complete)")
        print("="*70 + "\n")

        print("🎯 Getting Dragon Hunter Lance (2/3 items)...")
        submit_action(users[1], "Dragon Hunter Lance", "DROP", "Chambers of Xeric", 1)

        # Check task status
        db.session.refresh(task_status) if task_status else None
        task_status = TaskStatus.query.filter_by(team_id=team.id, task_id=task.id).first()
        print(f"\nTask completed: {task_status.completed if task_status else False}")
        print(f"Expected: True (got 2/3 items required)\n")

        # Check tile status
        tile_status = TileStatus.query.filter_by(team_id=team.id, tile_id=tile.id).first()
        if tile_status:
            print(f"Tile tasks completed: {tile_status.tasks_completed}/1")
            print(f"Medal level: {tile_status.get_medal_level()}")

        print("\n" + "="*70)
        print("TEST 3: Parent Challenge - Get 3rd Item (Already Complete)")
        print("="*70 + "\n")

        print("🎯 Getting Dragon Crossbow (3/3 items)...")
        submit_action(users[2], "Dragon Crossbow", "DROP", "Chambers of Xeric", 1)

        print(f"\nTask should remain completed (no change)")

        # Check challenge statuses
        print("\n" + "="*70)
        print("VERIFICATION: Challenge Status Breakdown")
        print("="*70 + "\n")

        parent_status = ChallengeStatus.query.filter_by(
            team_id=team.id,
            challenge_id=parent_challenge.id
        ).first()

        child_statuses = ChallengeStatus.query.join(
            Challenge
        ).filter(
            ChallengeStatus.team_id == team.id,
            Challenge.parent_challenge_id == parent_challenge.id
        ).all()

        print(f"Parent Challenge Status:")
        if parent_status:
            print(f"  Quantity: {parent_status.quantity}/2")
            print(f"  Completed: {parent_status.completed}")
        else:
            print(f"  No status found (parent challenges track children)")

        print(f"\nChild Challenge Statuses:")
        for i, cs in enumerate(child_statuses, 1):
            c = Challenge.query.get(cs.challenge_id)
            t = Trigger.query.get(c.trigger_id)
            print(f"  Child {i} ({t.name}): {cs.quantity}/{c.quantity} - Completed: {cs.completed}")

        print("\n" + "="*70)
        print("✅ PARENT CHALLENGE TESTS COMPLETE!")
        print("="*70 + "\n")

if __name__ == "__main__":
    main()
