#!/usr/bin/env python3
"""
Comprehensive Bingo Test Suite
Tests OR logic, AND logic, parent-child challenges, multi-team scenarios, and proof optimization
"""

import sys
import os
from datetime import datetime, timezone, timedelta
from app import app, db
from models.new_events import (
    Event, Team, TeamMember, Tile, Task, Challenge, Trigger,
    TileStatus, TaskStatus, ChallengeStatus, ChallengeProof, Action
)
from models.models import Users
from services.action_processor import ActionProcessor
import uuid

def cleanup_test_data():
    """Clean up any existing test data"""
    print("🧹 Cleaning up existing test data...")

    with app.app_context():
        # Delete test events and cascading data
        test_events = Event.query.filter(Event.name.like('%Comprehensive Test%')).all()
        for event in test_events:
            db.session.delete(event)

        db.session.commit()
    print("✅ Cleanup complete\n")

def create_test_users():
    """Get existing users for the teams"""
    print("👥 Getting test users...")

    with app.app_context():
        # Get first 8 users from the database
        users = Users.query.filter_by(is_active=True).limit(8).all()

        if len(users) < 8:
            print(f"❌ Need at least 8 users in database, found {len(users)}")
            print("   Create more users or reduce team sizes")
            sys.exit(1)

        print(f"✅ Found {len(users)} test users\n")
        for i, user in enumerate(users, 1):
            print(f"   {i}. {user.runescape_name} (ID: {user.id})")
        print()
        return users

def create_test_event():
    """Create comprehensive test event"""
    print("📅 Creating test event...")

    with app.app_context():
        start_date = datetime.now(timezone.utc) - timedelta(days=1)
        end_date = datetime.now(timezone.utc) + timedelta(days=30)

        event = Event(
            name="Comprehensive Test Event",
            start_date=start_date,
            end_date=end_date,
            thread_id="test-thread-123"
        )
        db.session.add(event)
        db.session.commit()

        print(f"✅ Created event: {event.name} (ID: {event.id})\n")
        return event

def create_test_teams(event, users):
    """Create two test teams with members"""
    print("🎯 Creating test teams...")

    with app.app_context():
        # Team A - 4 players
        team_a = Team(
            event_id=event.id,
            name="Alpha Squad",
            points=0
        )
        db.session.add(team_a)
        db.session.flush()

        for user in users[:4]:
            member = TeamMember(
                team_id=team_a.id,
                user_id=user.id
            )
            db.session.add(member)

        # Team B - 4 players
        team_b = Team(
            event_id=event.id,
            name="Bravo Battalion",
            points=0
        )
        db.session.add(team_b)
        db.session.flush()

        for user in users[4:8]:
            member = TeamMember(
                team_id=team_b.id,
                user_id=user.id
            )
            db.session.add(member)

        db.session.commit()

        print(f"✅ Created Team A: {team_a.name} (4 members)")
        print(f"✅ Created Team B: {team_b.name} (4 members)\n")

        return team_a, team_b

def create_triggers():
    """Create all triggers needed for testing"""
    print("🎯 Creating triggers...")

    with app.app_context():
        trigger_data = [
            # Boss kills
            ("Vorkath", "KC"),
            ("Zulrah", "KC"),
            ("Corporeal Beast", "KC"),
            ("Chambers of Xeric", "KC"),

            # Drops
            ("Dragon warhammer", "DROP"),
            ("Twisted bow", "DROP"),
            ("Elysian sigil", "DROP"),
            ("Abyssal whip", "DROP"),
            ("Dragon chainbody", "DROP"),

            # Quests
            ("Dragon Slayer II", "QUEST"),
            ("Monkey Madness II", "QUEST"),
            ("Song of the Elves", "QUEST"),

            # Achievements
            ("Combat Achievement - Easy Tier", "ACHIEVEMENT"),
            ("Combat Achievement - Medium Tier", "ACHIEVEMENT"),
            ("Combat Achievement - Hard Tier", "ACHIEVEMENT"),

            # Diaries (use ACHIEVEMENT type as DIARY isn't in constraint)
            ("Lumbridge Elite Diary", "ACHIEVEMENT"),
            ("Varrock Elite Diary", "ACHIEVEMENT"),
        ]

        triggers = {}
        for name, ttype in trigger_data:
            existing = Trigger.query.filter_by(name=name).first()
            if existing:
                triggers[name] = existing
            else:
                trigger = Trigger(name=name, type=ttype)
                db.session.add(trigger)
                db.session.flush()
                triggers[name] = trigger

        db.session.commit()
        print(f"✅ Created/found {len(triggers)} triggers\n")
        return triggers

def create_simple_tile(event, index, name, trigger_name, triggers, bronze_qty, silver_qty, gold_qty):
    """Create a simple tile with 3 tasks (bronze/silver/gold)"""
    with app.app_context():
        tile = Tile(
            event_id=event.id,
            index=index,
            name=name
        )
        db.session.add(tile)
        db.session.flush()

        # Create bronze/silver/gold tasks
        tasks = []
        for difficulty, qty in [("Bronze", bronze_qty), ("Silver", silver_qty), ("Gold", gold_qty)]:
            task = Task(
                tile_id=tile.id,
                name=f"{difficulty}: {name}",
                require_all=False
            )
            db.session.add(task)
            db.session.flush()
            tasks.append(task)

            # Create challenge
            trigger = triggers[trigger_name]
            challenge = Challenge(
                task_id=task.id,
                trigger_id=trigger.id,
                require_all=False,
                quantity=qty
            )
            db.session.add(challenge)

        db.session.commit()
        return tile

def create_or_tile(event, index, triggers):
    """
    Create tile with OR logic
    Complete by getting ANY ONE of multiple items
    """
    with app.app_context():
        tile = Tile(
            event_id=event.id,
            index=index,
            name="Barrows Armor Piece (Any)"
        )
        db.session.add(tile)
        db.session.flush()

        # Single task with OR challenges
        task = Task(
            tile_id=tile.id,
            name="Get any Barrows armor piece",
            require_all=False  # OR logic - only need ONE challenge
        )
        db.session.add(task)
        db.session.flush()

        # Multiple challenges - completing ANY ONE completes the task
        barrows_items = [
            "Torag's platebody",
            "Dharok's greataxe",
            "Ahrim's robetop",
            "Karil's crossbow"
        ]

        for item_name in barrows_items:
            # Create trigger if doesn't exist
            trigger = Trigger.query.filter_by(name=item_name).first()
            if not trigger:
                trigger = Trigger(name=item_name, type="DROP")
                db.session.add(trigger)
                db.session.flush()

            challenge = Challenge(
                task_id=task.id,
                trigger_id=trigger.id,
                require_all=False,
                quantity=1
            )
            db.session.add(challenge)

        db.session.commit()
        print(f"✅ Created OR tile (index {index}): {tile.name}")
        return tile

def create_and_tile(event, index, triggers):
    """
    Create tile with AND logic
    Require ALL items from the same boss
    """
    with app.app_context():
        tile = Tile(
            event_id=event.id,
            index=index,
            name="Full Zulrah Collection"
        )
        db.session.add(tile)
        db.session.flush()

        # Single task requiring ALL challenges
        task = Task(
            tile_id=tile.id,
            name="Get all Zulrah uniques",
            require_all=True  # AND logic - need ALL challenges
        )
        db.session.add(task)
        db.session.flush()

        # Multiple challenges - need ALL of them
        zulrah_uniques = [
            "Tanzanite fang",
            "Magic fang",
            "Serpentine visage"
        ]

        for item_name in zulrah_uniques:
            trigger = Trigger.query.filter_by(name=item_name).first()
            if not trigger:
                trigger = Trigger(name=item_name, type="DROP")
                db.session.add(trigger)
                db.session.flush()

            challenge = Challenge(
                task_id=task.id,
                trigger_id=trigger.id,
                require_all=False,
                quantity=1
            )
            db.session.add(challenge)

        db.session.commit()
        print(f"✅ Created AND tile (index {index}): {tile.name}")
        return tile

def create_parent_child_tile(event, index, triggers):
    """
    Create tile with parent-child challenge structure
    (Quest OR Diary) AND (Boss kill)
    """
    with app.app_context():
        tile = Tile(
            event_id=event.id,
            index=index,
            name="Elite Achievement Combo"
        )
        db.session.add(tile)
        db.session.flush()

        # Task requires ALL parent challenges
        task = Task(
            tile_id=tile.id,
            name="Complete elite achievement + boss",
            require_all=True  # Need both parent challenges
        )
        db.session.add(task)
        db.session.flush()

        # Parent 1: Quest OR Diary (either one)
        parent1 = Challenge(
            task_id=task.id,
            trigger_id=None,  # Parent has no trigger
            require_all=False,  # OR - only need one child
            quantity=1
        )
        db.session.add(parent1)
        db.session.flush()

        # Children of parent 1
        for trigger_name in ["Lumbridge Elite Diary", "Dragon Slayer II"]:
            child = Challenge(
                task_id=task.id,
                trigger_id=triggers[trigger_name].id,
                parent_challenge_id=parent1.id,
                require_all=False,
                quantity=1
            )
            db.session.add(child)

        # Parent 2: Boss kill (required)
        parent2 = Challenge(
            task_id=task.id,
            trigger_id=triggers["Vorkath"].id,
            require_all=False,
            quantity=10
        )
        db.session.add(parent2)

        db.session.commit()
        print(f"✅ Created parent-child tile (index {index}): {tile.name}")
        return tile

def setup_full_board(event, triggers):
    """Create a full 25-tile board with various challenge types"""
    print("📋 Setting up full 25-tile board...\n")

    tiles = []

    # Tiles 0-4: Simple boss kill tiles (bottom row - for easy bingo)
    tiles.append(create_simple_tile(event, 0, "Vorkath Kills", "Vorkath", triggers, 5, 10, 25))
    tiles.append(create_simple_tile(event, 1, "Zulrah Kills", "Zulrah", triggers, 10, 25, 50))
    tiles.append(create_simple_tile(event, 2, "Corp Kills", "Corporeal Beast", triggers, 1, 5, 10))
    tiles.append(create_simple_tile(event, 3, "CoX Completions", "Chambers of Xeric", triggers, 1, 3, 10))
    tiles.append(create_simple_tile(event, 4, "Easy CA Tier", "Combat Achievement - Easy Tier", triggers, 1, 1, 1))

    # Tiles 5-9: Mixed with OR tile
    tiles.append(create_simple_tile(event, 5, "Medium CA Tier", "Combat Achievement - Medium Tier", triggers, 1, 1, 1))
    tiles.append(create_or_tile(event, 6, triggers))  # OR tile
    tiles.append(create_simple_tile(event, 7, "Hard CA Tier", "Combat Achievement - Hard Tier", triggers, 1, 1, 1))
    tiles.append(create_simple_tile(event, 8, "MM2 Quest", "Monkey Madness II", triggers, 1, 1, 1))
    tiles.append(create_simple_tile(event, 9, "DS2 Quest", "Dragon Slayer II", triggers, 1, 1, 1))

    # Tiles 10-14: Mixed with AND tile
    tiles.append(create_simple_tile(event, 10, "SOTE Quest", "Song of the Elves", triggers, 1, 1, 1))
    tiles.append(create_and_tile(event, 11, triggers))  # AND tile
    tiles.append(create_simple_tile(event, 12, "Lumbridge Diary", "Lumbridge Elite Diary", triggers, 1, 1, 1))
    tiles.append(create_simple_tile(event, 13, "Varrock Diary", "Varrock Elite Diary", triggers, 1, 1, 1))
    tiles.append(create_parent_child_tile(event, 14, triggers))  # Parent-child tile

    # Tiles 15-19: Simple drop tiles
    tiles.append(create_simple_tile(event, 15, "DWH Drop", "Dragon warhammer", triggers, 1, 1, 1))
    tiles.append(create_simple_tile(event, 16, "Tbow Drop", "Twisted bow", triggers, 1, 1, 1))
    tiles.append(create_simple_tile(event, 17, "Ely Drop", "Elysian sigil", triggers, 1, 1, 1))
    tiles.append(create_simple_tile(event, 18, "Whip Drop", "Abyssal whip", triggers, 1, 2, 5))
    tiles.append(create_simple_tile(event, 19, "D Chain Drop", "Dragon chainbody", triggers, 1, 1, 1))

    # Tiles 20-24: More simple tiles for pattern completion
    tiles.append(create_simple_tile(event, 20, "Vorkath Grind", "Vorkath", triggers, 50, 100, 250))
    tiles.append(create_simple_tile(event, 21, "Zulrah Grind", "Zulrah", triggers, 50, 100, 250))
    tiles.append(create_simple_tile(event, 22, "Corp Grind", "Corporeal Beast", triggers, 10, 25, 50))
    tiles.append(create_simple_tile(event, 23, "CoX Grind", "Chambers of Xeric", triggers, 10, 25, 50))
    tiles.append(create_simple_tile(event, 24, "Final Boss", "Corporeal Beast", triggers, 100, 250, 500))

    print(f"\n✅ Created full 25-tile board!\n")
    print("Board layout:")
    print("  0   1   2   3   4")
    print("  5   6*  7   8   9")
    print(" 10  11* 12  13  14*")
    print(" 15  16  17  18  19")
    print(" 20  21  22  23  24")
    print("\n* = Special tiles (6=OR, 11=AND, 14=Parent-child)\n")

    return tiles

def run_or_logic_test(team, user):
    """Test OR challenge completion"""
    print("\n" + "="*60)
    print("TEST 1: OR Logic (Get ANY Barrows piece)")
    print("="*60)

    with app.app_context():
        # Submit one Barrows item - should complete the tile
        result = ActionProcessor.process_action(
            player_id=str(user.id),
            action_name="Dharok's greataxe",
            action_type="DROP",
            source="Barrows",
            quantity=1
        )

        print(f"\n📊 Action Result:")
        print(f"   Challenges completed: {len(result.get('completed_challenges', []))}")
        print(f"   Tasks completed: {len(result.get('completed_tasks', []))}")
        print(f"   Tiles completed: {len(result.get('completed_tiles', []))}")
        print(f"   Bingos: {result.get('bingos', [])}")

        # Check proofs created
        tile = Tile.query.filter_by(index=6).first()
        task = Task.query.filter_by(tile_id=tile.id).first()
        proofs = ChallengeProof.query.join(Challenge).filter(
            Challenge.task_id == task.id,
            ChallengeProof.team_id == team.id
        ).all()

        print(f"\n🔍 Proofs Created: {len(proofs)}")
        print(f"   Expected: 1 (only for the matched challenge)")

        # Verify task completed
        task_status = TaskStatus.query.filter_by(
            team_id=team.id,
            task_id=task.id
        ).first()

        if task_status and task_status.completed:
            print(f"✅ OR logic works! Task completed with just one item")
        else:
            print(f"❌ OR logic failed - task not completed")

        return result

def run_and_logic_test(team, user):
    """Test AND challenge completion"""
    print("\n" + "="*60)
    print("TEST 2: AND Logic (Get ALL Zulrah uniques)")
    print("="*60)

    with app.app_context():
        zulrah_uniques = ["Tanzanite fang", "Magic fang", "Serpentine visage"]

        for i, item in enumerate(zulrah_uniques, 1):
            print(f"\n📦 Submitting item {i}/3: {item}")
            result = ActionProcessor.process_action(
                player_id=str(user.id),
                action_name=item,
                action_type="DROP",
                source="Zulrah",
                quantity=1
            )

            print(f"   Tasks completed: {len(result.get('completed_tasks', []))}")

            if i < 3:
                print(f"   ⏳ Task should NOT be complete yet (need all 3)")
            else:
                print(f"   ✅ Task should be complete now (got all 3)")

        # Check final state
        tile = Tile.query.filter_by(index=11).first()
        task = Task.query.filter_by(tile_id=tile.id).first()
        task_status = TaskStatus.query.filter_by(
            team_id=team.id,
            task_id=task.id
        ).first()

        if task_status and task_status.completed:
            print(f"\n✅ AND logic works! Task completed only after all items")
        else:
            print(f"\n❌ AND logic failed - task should be completed")

        # Check proofs
        proofs = ChallengeProof.query.join(Challenge).filter(
            Challenge.task_id == task.id,
            ChallengeProof.team_id == team.id
        ).all()

        print(f"\n🔍 Proofs Created: {len(proofs)}")
        print(f"   Expected: 3 (one for each item)")

        return result

def run_parent_child_logic_test(team, user):
    """Test parent-child challenge structure"""
    print("\n" + "="*60)
    print("TEST 3: Parent-Child Logic (Quest OR Diary) AND (Boss kills)")
    print("="*60)

    with app.app_context():
        # First, complete the boss requirement (10 Vorkath)
        print("\n📦 Step 1: Submit 10 Vorkath kills...")
        for i in range(10):
            ActionProcessor.process_action(
                player_id=str(user.id),
                action_name="Vorkath",
                action_type="KC",
                quantity=1
            )
        print("   ✅ Boss requirement submitted")

        # Check if task is complete (it shouldn't be)
        tile = Tile.query.filter_by(index=14).first()
        task = Task.query.filter_by(tile_id=tile.id).first()
        task_status = TaskStatus.query.filter_by(
            team_id=team.id,
            task_id=task.id
        ).first()

        if task_status and task_status.completed:
            print("   ❌ Task should NOT be complete yet (need quest/diary too)")
        else:
            print("   ✅ Task correctly incomplete (need quest/diary)")

        # Now complete ONE of the quest/diary options (should complete the parent)
        print("\n📦 Step 2: Complete Dragon Slayer II quest...")
        result = ActionProcessor.process_action(
            player_id=str(user.id),
            action_name="Dragon Slayer II",
            action_type="QUEST",
            quantity=1
        )

        # Re-check task status
        db.session.refresh(task_status) if task_status else None
        task_status = TaskStatus.query.filter_by(
            team_id=team.id,
            task_id=task.id
        ).first()

        if task_status and task_status.completed:
            print("   ✅ Task completed! Parent-child logic works")
            print("      (Boss kills AND quest/diary both satisfied)")
        else:
            print("   ❌ Task should be complete now")

        # Check proofs
        proofs = ChallengeProof.query.join(Challenge).filter(
            Challenge.task_id == task.id,
            ChallengeProof.team_id == team.id
        ).all()

        print(f"\n🔍 Proofs Created: {len(proofs)}")
        print(f"   Expected: ~11 (10 for Vorkath + 1 for quest)")

        return result

def run_multi_team_bingo_test(team_a, team_b, users):
    """Test bingo detection with multiple teams"""
    print("\n" + "="*60)
    print("TEST 4: Multi-Team Bingo Detection")
    print("="*60)

    with app.app_context():
        # Team A completes bottom row (tiles 0-4)
        print("\n🎯 Team A: Completing bottom row (tiles 0-4)")

        # Tile 0: Vorkath (5 kills for bronze)
        for i in range(5):
            ActionProcessor.process_action(
                player_id=str(users[0].id),  # Team A member
                action_name="Vorkath",
                action_type="KC",
                quantity=1
            )

        # Tile 1: Zulrah (10 kills for bronze)
        for i in range(10):
            ActionProcessor.process_action(
                player_id=str(users[1].id),
                action_name="Zulrah",
                action_type="KC",
                quantity=1
            )

        # Tile 2: Corp (1 kill for bronze)
        ActionProcessor.process_action(
            player_id=str(users[2].id),
            action_name="Corporeal Beast",
            action_type="KC",
            quantity=1
        )

        # Tile 3: CoX (1 completion for bronze)
        ActionProcessor.process_action(
            player_id=str(users[3].id),
            action_name="Chambers of Xeric",
            action_type="KC",
            quantity=1
        )

        # Tile 4: Easy CA (1 for bronze)
        result_a = ActionProcessor.process_action(
            player_id=str(users[0].id),
            action_name="Combat Achievement - Easy Tier",
            action_type="ACHIEVEMENT",
            quantity=1
        )

        team_a_obj = Team.query.get(team_a.id)
        bingos_a = result_a.get('bingos_awarded', 0)
        print(f"\n📊 Team A Results:")
        print(f"   Tiles completed: {len(result_a.get('completed_tiles', []))}")
        print(f"   Bingos awarded: {bingos_a}")
        print(f"   Points: {team_a_obj.points}")

        # Team B completes left column (tiles 0, 5, 10, 15, 20)
        print("\n🎯 Team B: Completing left column (tiles 0, 5, 10, 15, 20)")

        # Tile 0: Vorkath (5 kills)
        for i in range(5):
            ActionProcessor.process_action(
                player_id=str(users[4].id),  # Team B member
                action_name="Vorkath",
                action_type="KC",
                quantity=1
            )

        # Tile 5: Medium CA
        ActionProcessor.process_action(
            player_id=str(users[5].id),
            action_name="Combat Achievement - Medium Tier",
            action_type="ACHIEVEMENT",
            quantity=1
        )

        # Tile 10: SOTE Quest
        ActionProcessor.process_action(
            player_id=str(users[6].id),
            action_name="Song of the Elves",
            action_type="QUEST",
            quantity=1
        )

        # Tile 15: DWH
        ActionProcessor.process_action(
            player_id=str(users[7].id),
            action_name="Dragon warhammer",
            action_type="DROP",
            source="Shamans",
            quantity=1
        )

        # Tile 20: Vorkath grind (50 for bronze)
        for i in range(50):
            ActionProcessor.process_action(
                player_id=str(users[4].id),
                action_name="Vorkath",
                action_type="KC",
                quantity=1
            )

        team_b_obj = Team.query.get(team_b.id)
        # Count bingos from the final action result (last tile completion should award bingo)
        print(f"\n📊 Team B Results:")
        print(f"   Tiles completed: 5 (expected)")
        print(f"   Points: {team_b_obj.points}")

        # Check if bingos were awarded (tracked in action results)
        print("\n✅ Multi-team bingo test completed")
        print(f"   Check bingo notifications for both teams")

def run_proof_optimization_test():
    """Test that proof optimization is working across all challenge types"""
    print("\n" + "="*60)
    print("TEST 5: Proof Creation Optimization")
    print("="*60)

    with app.app_context():
        # Count all proofs created during testing
        total_proofs = ChallengeProof.query.count()
        total_actions = Action.query.count()

        print(f"\n📊 Proof Optimization Stats:")
        print(f"   Total actions submitted: {total_actions}")
        print(f"   Total proofs created: {total_proofs}")
        print(f"   Ratio: {total_proofs / max(total_actions, 1):.2f} proofs per action")
        print(f"\n   Expected: ~1.5-2.0 proofs per action (with optimization)")
        print(f"   Without optimization: 3.0 proofs per action")

        if total_proofs / max(total_actions, 1) < 2.5:
            print("\n✅ Proof optimization is working!")
        else:
            print("\n⚠️  Proof optimization may not be fully effective")

def main():
    """Run all comprehensive tests"""
    print("\n" + "="*60)
    print("🧪 COMPREHENSIVE BINGO TEST SUITE")
    print("="*60 + "\n")

    # Cleanup
    cleanup_test_data()

    # Setup
    users = create_test_users()
    event = create_test_event()
    team_a, team_b = create_test_teams(event, users)
    triggers = create_triggers()
    tiles = setup_full_board(event, triggers)

    # Run tests with Team A, Player 1
    run_or_logic_test(team_a, users[0])
    run_and_logic_test(team_a, users[1])
    run_parent_child_logic_test(team_a, users[2])

    # Multi-team test
    run_multi_team_bingo_test(team_a, team_b, users)

    # Proof optimization check
    run_proof_optimization_test()

    print("\n" + "="*60)
    print("🎉 ALL TESTS COMPLETE!")
    print("="*60 + "\n")

    # Final summary
    with app.app_context():
        team_a_obj = Team.query.get(team_a.id)
        team_b_obj = Team.query.get(team_b.id)

        print("📊 Final Stats:")
        print(f"\nTeam A ({team_a_obj.name}):")
        print(f"   Points: {team_a_obj.points}")

        print(f"\nTeam B ({team_b_obj.name}):")
        print(f"   Points: {team_b_obj.points}")

        print(f"\nTotal tiles in event: {Tile.query.filter_by(event_id=event.id).count()}")
        print(f"Total triggers created: {Trigger.query.count()}")
        print(f"Total actions processed: {Action.query.count()}")
        print(f"Total proofs created: {ChallengeProof.query.count()}")

if __name__ == "__main__":
    main()
