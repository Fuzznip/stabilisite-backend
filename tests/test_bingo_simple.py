#!/usr/bin/env python3
"""
Simplified Bingo Test - Tests key features in one context
"""

import datetime
from datetime import timezone, timedelta
from app import app, db
from models.new_events import *
from models.models import Users
from services.action_processor import ActionProcessor

def main():
    print("\n" + "="*70)
    print("🧪 SIMPLIFIED BINGO TEST - Testing Key Features")
    print("="*70 + "\n")

    with app.app_context():
        # 1. Get users
        print("👥 Getting test users...")
        users = Users.query.limit(4).all()
        print(f"✅ Found {len(users)} users\n")

        # 2. Create event
        print("📅 Creating test event...")
        now = datetime.datetime.now(timezone.utc)
        event = Event(
            name=f"Test Event {now.strftime('%H:%M:%S')}",
            start_date=now - timedelta(days=1),
            end_date=now + timedelta(days=30)
        )
        db.session.add(event)
        db.session.flush()
        print(f"✅ Event created: {event.name}\n")

        # 3. Create team
        print("🎯 Creating test team...")
        team = Team(event_id=event.id, name="Test Squad")
        db.session.add(team)
        db.session.flush()

        for user in users:
            member = TeamMember(team_id=team.id, user_id=user.id)
            db.session.add(member)
        db.session.flush()
        print(f"✅ Team created with {len(users)} members\n")

        # 4. Create triggers
        print("🎯 Creating triggers...")
        vorkath_trigger = Trigger(name="Vorkath", type="KC")
        dharok_trigger = Trigger(name="Dharok's greataxe", type="DROP")
        tanzanite_trigger = Trigger(name="Tanzanite fang", type="DROP")
        magic_trigger = Trigger(name="Magic fang", type="DROP")
        serpentine_trigger = Trigger(name="Serpentine visage", type="DROP")
        quest_trigger = Trigger(name="Dragon Slayer II", type="QUEST")
        db.session.add_all([vorkath_trigger, dharok_trigger, tanzanite_trigger, magic_trigger, serpentine_trigger, quest_trigger])
        db.session.flush()
        print("✅ Created 6 triggers\n")

        # 5. Create tiles
        print("📋 Creating test tiles...\n")

        # TILE 0: Simple KC tile
        print("  Tile 0: Simple KC (Vorkath 5/10/25)")
        tile0 = Tile(event_id=event.id, index=0, name="Vorkath Kills")
        db.session.add(tile0)
        db.session.flush()

        for diff, qty in [("Bronze", 5), ("Silver", 10), ("Gold", 25)]:
            task = Task(tile_id=tile0.id, name=f"{diff}: Vorkath", require_all=False)
            db.session.add(task)
            db.session.flush()

            challenge = Challenge(task_id=task.id, trigger_id=vorkath_trigger.id, quantity=qty)
            db.session.add(challenge)

        # TILE 1: OR logic (any Barrows piece)
        print("  Tile 1: OR logic (Any of 4 Barrows items)")
        tile1 = Tile(event_id=event.id, index=1, name="Barrows Piece (Any)")
        db.session.add(tile1)
        db.session.flush()

        task1 = Task(tile_id=tile1.id, name="Get any Barrows piece", require_all=False)  # OR
        db.session.add(task1)
        db.session.flush()

        # Create Barrows triggers
        barrows_items = ["Torag's platebody", "Ahrim's robetop", "Karil's crossbow"]
        for item in barrows_items:
            trigger = Trigger(name=item, type="DROP")
            db.session.add(trigger)
            db.session.flush()

            challenge = Challenge(task_id=task1.id, trigger_id=trigger.id, quantity=1)
            db.session.add(challenge)

        # Also add Dharok (already created)
        challenge = Challenge(task_id=task1.id, trigger_id=dharok_trigger.id, quantity=1)
        db.session.add(challenge)

        # TILE 2: AND logic (all 3 Zulrah uniques)
        print("  Tile 2: AND logic (All 3 Zulrah uniques)")
        tile2 = Tile(event_id=event.id, index=2, name="Full Zulrah Collection")
        db.session.add(tile2)
        db.session.flush()

        task2 = Task(tile_id=tile2.id, name="Get all Zulrah uniques", require_all=True)  # AND
        db.session.add(task2)
        db.session.flush()

        for trigger in [tanzanite_trigger, magic_trigger, serpentine_trigger]:
            challenge = Challenge(task_id=task2.id, trigger_id=trigger.id, quantity=1)
            db.session.add(challenge)

        # TILE 3: Multi-task tile (Bronze/Silver/Gold boss kills)
        print("  Tile 3: Multi-task (Vorkath 3/5/10)")
        tile3 = Tile(event_id=event.id, index=3, name="Vorkath Grind")
        db.session.add(tile3)
        db.session.flush()

        for diff, qty in [("Bronze", 3), ("Silver", 5), ("Gold", 10)]:
            task = Task(tile_id=tile3.id, name=f"{diff}: Vorkath Grind")
            db.session.add(task)
            db.session.flush()

            challenge = Challenge(task_id=task.id, trigger_id=vorkath_trigger.id, quantity=qty)
            db.session.add(challenge)

        # TILE 4: Simple quest tile
        print("  Tile 4: Simple quest tile")
        tile4 = Tile(event_id=event.id, index=4, name="Dragon Slayer II")
        db.session.add(tile4)
        db.session.flush()

        task4 = Task(tile_id=tile4.id, name="Complete DS2")
        db.session.add(task4)
        db.session.flush()

        challenge4 = Challenge(task_id=task4.id, trigger_id=quest_trigger.id, quantity=1)
        db.session.add(challenge4)

        db.session.commit()
        print("\n✅ Created 5 tiles with different challenge types\n")

        # TEST 1: OR Logic
        print("="*70)
        print("TEST 1: OR Logic - Any Barrows Piece")
        print("="*70)
        print(f"Submitting Dharok's greataxe...")

        result = ActionProcessor.process_action(
            player_id=str(users[0].id),
            action_name="Dharok's greataxe",
            action_type="DROP",
            source="Barrows",
            quantity=1
        )

        proofs = ChallengeProof.query.join(
            ChallengeStatus, ChallengeProof.challenge_status_id == ChallengeStatus.id
        ).join(
            Challenge, ChallengeStatus.challenge_id == Challenge.id
        ).filter(
            Challenge.task_id == task1.id,
            ChallengeStatus.team_id == team.id
        ).count()

        task1_status = TaskStatus.query.filter_by(team_id=team.id, task_id=task1.id).first()

        print(f"✅ Action processed")
        print(f"   Proofs created: {proofs} (expected: 1)")
        print(f"   Task completed: {task1_status.completed if task1_status else False}")
        print(f"   Result: {'✅ PASS' if task1_status and task1_status.completed else '❌ FAIL'}\n")

        # TEST 2: AND Logic
        print("="*70)
        print("TEST 2: AND Logic - All Zulrah Uniques")
        print("="*70)

        for i, item in enumerate(["Tanzanite fang", "Magic fang", "Serpentine visage"], 1):
            print(f"Submitting {i}/3: {item}")
            ActionProcessor.process_action(
                player_id=str(users[1].id),
                action_name=item,
                action_type="DROP",
                source="Zulrah",
                quantity=1
            )

        task2_status = TaskStatus.query.filter_by(team_id=team.id, task_id=task2.id).first()
        proofs2 = ChallengeProof.query.join(
            ChallengeStatus, ChallengeProof.challenge_status_id == ChallengeStatus.id
        ).join(
            Challenge, ChallengeStatus.challenge_id == Challenge.id
        ).filter(
            Challenge.task_id == task2.id,
            ChallengeStatus.team_id == team.id
        ).count()

        print(f"✅ All items submitted")
        print(f"   Proofs created: {proofs2} (expected: 3)")
        print(f"   Task completed: {task2_status.completed if task2_status else False}")
        print(f"   Result: {'✅ PASS' if task2_status and task2_status.completed else '❌ FAIL'}\n")

        # TEST 3: Multi-Task Progression
        print("="*70)
        print("TEST 3: Multi-Task Progression (Bronze→Silver→Gold)")
        print("="*70)

        print("Tile 3 has 3 tasks: Bronze (3 kills), Silver (5 kills), Gold (10 kills)")
        print("Submitting 10 Vorkath kills to test task progression...")

        # Get all tasks for tile 3
        tile3_tasks = Task.query.filter_by(tile_id=tile3.id).order_by(Task.id).all()
        bronze_task, silver_task, gold_task = tile3_tasks

        for i in range(1, 11):
            ActionProcessor.process_action(
                player_id=str(users[2].id),
                action_name="Vorkath",
                action_type="KC",
                quantity=1
            )
            print(f"   Kill {i}/10")

        # Check all task statuses
        bronze_status = TaskStatus.query.filter_by(team_id=team.id, task_id=bronze_task.id).first()
        silver_status = TaskStatus.query.filter_by(team_id=team.id, task_id=silver_task.id).first()
        gold_status = TaskStatus.query.filter_by(team_id=team.id, task_id=gold_task.id).first()

        print(f"\n✅ All kills submitted")
        print(f"   Bronze (3 kills): {bronze_status.completed if bronze_status else False}")
        print(f"   Silver (5 kills): {silver_status.completed if silver_status else False}")
        print(f"   Gold (10 kills): {gold_status.completed if gold_status else False}")

        all_complete = (
            bronze_status and bronze_status.completed and
            silver_status and silver_status.completed and
            gold_status and gold_status.completed
        )
        print(f"   Result: {'✅ PASS' if all_complete else '❌ FAIL'}\n")

        # TEST 4: Proof Optimization
        print("="*70)
        print("TEST 4: Proof Optimization on Simple Tile")
        print("="*70)

        print("Submitting 4 Vorkath kills (bronze=5, silver=10, gold=25)...")
        for i in range(1, 5):
            ActionProcessor.process_action(
                player_id=str(users[3].id),
                action_name="Vorkath",
                action_type="KC",
                quantity=1
            )
            print(f"   Kill {i}/4")

        # Count proofs for tile 0
        proofs0 = ChallengeProof.query.join(
            ChallengeStatus, ChallengeProof.challenge_status_id == ChallengeStatus.id
        ).join(
            Challenge, ChallengeStatus.challenge_id == Challenge.id
        ).join(
            Task, Challenge.task_id == Task.id
        ).filter(
            Task.tile_id == tile0.id,
            ChallengeStatus.team_id == team.id
        ).count()

        print(f"\n✅ Vorkath kills submitted")
        print(f"   Proofs created: {proofs0}")
        print(f"   Expected: 4 (one per action, all for bronze task)")
        print(f"   Without optimization would be: 12 (4 kills × 3 tasks)")
        print(f"   Result: {'✅ PASS' if proofs0 == 4 else '❌ FAIL'}\n")

        # FINAL STATS
        print("="*70)
        print("🎉 FINAL STATS")
        print("="*70)

        total_actions = Action.query.count()
        total_proofs = ChallengeProof.query.count()
        ratio = total_proofs / max(total_actions, 1)

        print(f"Total actions: {total_actions}")
        print(f"Total proofs: {total_proofs}")
        print(f"Ratio: {ratio:.2f} proofs per action")
        print(f"Expected: ~1.5-2.0 (with optimization)")
        print(f"Without optimization: 3.0+")

        # Count completed tiles (tasks_completed == 3 means all bronze/silver/gold done OR single task done)
        all_tile_statuses = TileStatus.query.filter_by(team_id=team.id).all()
        completed_tiles = sum(1 for ts in all_tile_statuses if ts.tasks_completed > 0)

        print(f"\nTiles with progress: {completed_tiles}")
        print(f"Team points: {team.points}")

        print("\n" + "="*70)
        print("✅ ALL TESTS COMPLETE!")
        print("="*70 + "\n")

if __name__ == "__main__":
    main()
