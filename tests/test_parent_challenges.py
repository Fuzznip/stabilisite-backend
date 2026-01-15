#!/usr/bin/env python3
"""
Test Parent Challenge Structures
Tests nested parent-child challenges like (Quest OR Diary) AND (Boss)
"""

import datetime
from datetime import timezone, timedelta
from app import app, db
from models.new_events import *
from models.models import Users
from services.action_processor import ActionProcessor

def main():
    print("\n" + "="*70)
    print("🧪 PARENT CHALLENGE TEST")
    print("="*70 + "\n")

    with app.app_context():
        # Setup
        print("👥 Getting test user...")
        user = Users.query.first()
        print(f"✅ Found user: {user.runescape_name}\n")

        print("📅 Creating test event...")
        now = datetime.datetime.now(timezone.utc)
        event = Event(
            name=f"Parent Test {now.strftime('%H:%M:%S')}",
            start_date=now - timedelta(days=1),
            end_date=now + timedelta(days=30)
        )
        db.session.add(event)
        db.session.flush()
        print(f"✅ Event created\n")

        print("🎯 Creating test team...")
        team = Team(event_id=event.id, name="Test Squad")
        db.session.add(team)
        db.session.flush()

        member = TeamMember(team_id=team.id, user_id=user.id)
        db.session.add(member)
        db.session.flush()
        print("✅ Team created\n")

        print("🎯 Creating triggers...")
        vorkath = Trigger(name="Vorkath", type="KC")
        quest = Trigger(name="Dragon Slayer II", type="QUEST")
        diary = Trigger(name="Lumbridge Elite", type="ACHIEVEMENT")
        db.session.add_all([vorkath, quest, diary])
        db.session.flush()
        print("✅ Created 3 triggers\n")

        print("📋 Creating parent-child tile...")
        print("   Structure: (Quest OR Diary) AND (Boss kills)")
        tile = Tile(event_id=event.id, index=0, name="Achievement Combo")
        db.session.add(tile)
        db.session.flush()

        task = Task(tile_id=tile.id, name="Complete achievement + boss", require_all=True)
        db.session.add(task)
        db.session.flush()

        # Parent 1: Quest OR Diary (either one)
        print("   Creating Parent 1: OR container (Quest OR Diary)")
        parent1 = Challenge(
            task_id=task.id,
            trigger_id=None,  # Parent has no trigger
            require_all=False,  # OR logic
            quantity=1
        )
        db.session.add(parent1)
        db.session.flush()
        print(f"   ✅ Parent 1 ID: {parent1.id}")

        # Children of parent 1
        print("   Creating children of Parent 1...")
        child1 = Challenge(
            task_id=task.id,
            trigger_id=quest.id,
            parent_challenge_id=parent1.id,
            quantity=1
        )
        db.session.add(child1)

        child2 = Challenge(
            task_id=task.id,
            trigger_id=diary.id,
            parent_challenge_id=parent1.id,
            quantity=1
        )
        db.session.add(child2)
        print("   ✅ Created 2 children (Quest, Diary)")

        # Parent 2: Boss kills (required)
        print("   Creating Parent 2: Boss requirement")
        parent2 = Challenge(
            task_id=task.id,
            trigger_id=vorkath.id,
            quantity=5
        )
        db.session.add(parent2)

        db.session.commit()
        print("\n✅ Parent-child structure created!\n")

        # TEST: Submit actions
        print("="*70)
        print("TEST: Parent-Child Challenge Completion")
        print("="*70)

        # First, submit boss kills
        print("\n📦 Step 1: Submit 5 Vorkath kills (parent 2)...")
        for i in range(1, 6):
            ActionProcessor.process_action(
                player_id=str(user.id),
                action_name="Vorkath",
                action_type="KC",
                quantity=1
            )
            print(f"   Kill {i}/5")

        task_status = TaskStatus.query.filter_by(team_id=team.id, task_id=task.id).first()
        print(f"\n✅ Boss kills done")
        print(f"   Task complete: {task_status.completed if task_status else False}")
        print(f"   Expected: False (still need Quest OR Diary)")

        if task_status and task_status.completed:
            print("   ❌ FAIL: Task should NOT be complete yet\n")
            return
        else:
            print("   ✅ PASS: Correctly incomplete\n")

        # Now submit quest (one of the OR options)
        print("📦 Step 2: Submit Dragon Slayer II quest (child of parent 1)...")
        result = ActionProcessor.process_action(
            player_id=str(user.id),
            action_name="Dragon Slayer II",
            action_type="QUEST",
            quantity=1
        )

        # Refresh task status
        task_status = TaskStatus.query.filter_by(team_id=team.id, task_id=task.id).first()

        print(f"\n✅ Quest submitted")
        print(f"   Task complete: {task_status.completed if task_status else False}")
        print(f"   Expected: True (Boss AND (Quest OR Diary) both satisfied)")

        # Check parent challenge statuses
        parent1_status = ChallengeStatus.query.filter_by(
            team_id=team.id,
            challenge_id=parent1.id
        ).first()

        parent2_status = ChallengeStatus.query.filter_by(
            team_id=team.id,
            challenge_id=parent2.id
        ).first()

        print(f"\n📊 Challenge Status:")
        print(f"   Parent 1 (Quest OR Diary): {parent1_status.completed if parent1_status else False}")
        print(f"   Parent 2 (Boss kills): {parent2_status.completed if parent2_status else False}")

        if task_status and task_status.completed:
            print(f"\n✅ ✅ ✅ PARENT CHALLENGE TEST PASSED! ✅ ✅ ✅")
            print(f"   Task completed correctly with nested parent-child structure")
        else:
            print(f"\n❌ FAIL: Task should be complete")

        print("\n" + "="*70)
        print("✅ TEST COMPLETE")
        print("="*70 + "\n")

if __name__ == "__main__":
    main()
