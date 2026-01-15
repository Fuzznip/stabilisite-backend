#!/usr/bin/env python3
"""
Manual testing script for Bingo event handler
Tests various scenarios including OR/AND logic and parent challenges
"""

import datetime
from datetime import timezone
from app import app, db
from models.new_events import Event, Team, TeamMember, Action, TileStatus, TaskStatus, ChallengeStatus
from models.models import Users
from event_handlers.bingo.bingo import bingo_handler
from event_handlers.event_handler import EventSubmission

def print_section(title):
    print("\n" + "="*70)
    print(f"  {title}")
    print("="*70)

def print_team_status(team):
    """Print current team status"""
    tile_statuses = TileStatus.query.filter_by(team_id=team.id).all()
    completed_count = sum(1 for ts in tile_statuses if ts.tasks_completed > 0)

    print(f"\n📊 {team.name} Status:")
    print(f"   Points: {team.points}")
    print(f"   Tiles with progress: {completed_count}/25")

    if tile_statuses:
        print(f"   Tile progress breakdown:")
        for ts in tile_statuses[:5]:  # Show first 5
            from models.new_events import Tile
            tile = Tile.query.get(ts.tile_id)
            print(f"     - Tile {tile.index} ({tile.name}): {ts.tasks_completed}/3 tasks")

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

    print(f"\n📤 Submitting: {action_type} - {action_name} x{quantity}" +
          (f" from {source}" if source else ""))

    result = bingo_handler(submission)

    if result:
        print(f"✅ Notification sent: {result[0].title}")
        return True
    else:
        print(f"   (No notification - progress updated)")
        return False

def main():
    print("\n" + "="*70)
    print("🧪 BINGO EVENT HANDLER MANUAL TEST SUITE")
    print("="*70)

    with app.app_context():
        # Get event and teams
        event = Event.query.filter_by(name="Winter Bingo 2026").first()
        if not event:
            print("❌ No bingo event found! Run setup_bingo_test_data.py first.")
            return

        teams = Team.query.filter_by(event_id=event.id).all()
        if not teams:
            print("❌ No teams found!")
            return

        print(f"\n✅ Found event: {event.name}")
        print(f"✅ Found {len(teams)} teams")

        # Get users from first team
        team1 = teams[0]
        members = TeamMember.query.filter_by(team_id=team1.id).all()
        users = [Users.query.get(m.user_id) for m in members]

        if len(users) < 3:
            print("❌ Need at least 3 users on team!")
            return

        user1, user2, user3 = users[0], users[1], users[2]
        print(f"\n👥 Test users from {team1.name}:")
        print(f"   User 1: {user1.runescape_name}")
        print(f"   User 2: {user2.runescape_name}")
        print(f"   User 3: {user3.runescape_name}")

        # TEST 1: Simple progression (Bronze -> Silver -> Gold)
        print_section("TEST 1: Simple KC Progression (Vorkath)")
        print("Testing Tile 1: Vorkath Grind (Bronze: 25, Silver: 50, Gold: 100)")

        print("\n🎯 Submitting 25 Vorkath kills (should complete Bronze)...")
        for i in range(25):
            submit_action(user1, "Vorkath", "KC", quantity=1)
            if i % 10 == 9:
                print(f"   Progress: {i+1}/25 kills")

        print("\n🎯 Submitting 25 more Vorkath kills (should complete Silver at 50 total)...")
        for i in range(25):
            submit_action(user1, "Vorkath", "KC", quantity=1)
            if i % 10 == 9:
                print(f"   Progress: {25+i+1}/50 kills")

        print("\n🎯 Submitting 50 more Vorkath kills (should complete Gold at 100 total)...")
        for i in range(50):
            submit_action(user1, "Vorkath", "KC", quantity=1)
            if i % 20 == 19:
                print(f"   Progress: {50+i+1}/100 kills")

        print_team_status(team1)

        # TEST 2: OR Logic (any one of multiple options)
        print_section("TEST 2: OR Logic - GWD Bosses")
        print("Testing Tile 0: GWD Starter")
        print("Bronze task requires 10 total KC across 4 GWD bosses (OR logic)")

        print("\n🎯 Submitting mixed GWD kills...")
        submit_action(user2, "General Graardor", "KC", quantity=3)
        submit_action(user2, "Kree'arra", "KC", quantity=3)
        submit_action(user2, "Commander Zilyana", "KC", quantity=2)
        submit_action(user2, "K'ril Tsutsaroth", "KC", quantity=2)
        print("   Total: 10 GWD KC (should complete Bronze)")

        print_team_status(team1)

        # TEST 3: AND Logic (need all requirements)
        print_section("TEST 3: AND Logic - DKs Tribrid")
        print("Testing Tile 4: DKs Tribrid")
        print("Bronze task requires 1 kill of EACH DK (AND logic)")

        print("\n🎯 Submitting only 2 DKs (should NOT complete)...")
        submit_action(user3, "Dagannoth Rex", "KC", quantity=1)
        submit_action(user3, "Dagannoth Prime", "KC", quantity=1)

        task_status = db.session.query(TaskStatus).join(
            Team
        ).filter(Team.id == team1.id).first()
        print(f"   Task completed: {task_status.completed if task_status else 'N/A'}")

        print("\n🎯 Submitting the 3rd DK (should complete Bronze)...")
        submit_action(user3, "Dagannoth Supreme", "KC", quantity=1)

        print_team_status(team1)

        # TEST 4: Multiple tasks on same tile
        print_section("TEST 4: Multi-Task Tile - Zulrah Uniques")
        print("Testing Tile 11: Each unique is a separate task (OR within tile)")

        print("\n🎯 Getting Tanzanite Fang...")
        submit_action(user1, "Tanzanite Fang", "DROP", source="Zulrah", quantity=1)

        print("\n🎯 Getting Magic Fang...")
        submit_action(user2, "Magic Fang", "DROP", source="Zulrah", quantity=1)

        print("\n🎯 Getting Serpentine Visage...")
        submit_action(user3, "Serpentine Visage", "DROP", source="Zulrah", quantity=1)

        print("   All 3 tasks should be completed (3/3 on this tile)")

        print_team_status(team1)

        # TEST 5: Wilderness bosses (OR logic with multiple bosses)
        print_section("TEST 5: Wilderness Bosses - OR Logic")
        print("Testing Tile 3: Wilderness Boss (Bronze needs 10 KC across 3 bosses)")

        print("\n🎯 Distributing kills across wildy bosses...")
        submit_action(user1, "Venenatis", "KC", quantity=4)
        submit_action(user2, "Callisto", "KC", quantity=3)
        submit_action(user3, "Vet'ion", "KC", quantity=3)
        print("   Total: 10 Wildy KC (should complete Bronze)")

        print_team_status(team1)

        # TEST 6: Slayer bosses progression
        print_section("TEST 6: Slayer Bosses - Mixed Kills")
        print("Testing Tile 7: Slayer Bosses (Bronze: 25 KC across 3 bosses)")

        print("\n🎯 Submitting Kraken kills...")
        submit_action(user1, "Kraken", "KC", quantity=10)

        print("\n🎯 Submitting Thermy kills...")
        submit_action(user2, "Thermonuclear Smoke Devil", "KC", quantity=8)

        print("\n🎯 Submitting Cerberus kills...")
        submit_action(user3, "Cerberus", "KC", quantity=7)
        print("   Total: 25 Slayer Boss KC (should complete Bronze)")

        print_team_status(team1)

        # TEST 7: Raids (any raid counts)
        print_section("TEST 7: Raids - OR Logic Between Raid Types")
        print("Testing Tile 5: Raids Beginner (Bronze: 1 raid of either type)")

        print("\n🎯 Completing 1 CoX...")
        submit_action(user1, "Chambers of Xeric", "KC", quantity=1)
        print("   Should complete Bronze (either raid counts)")

        print_team_status(team1)

        # TEST 8: Rare drops
        print_section("TEST 8: Mega Rares - Individual Tasks")
        print("Testing Tile 10: Mega Rares (3 separate mega rare tasks)")

        print("\n🎯 Getting Twisted Bow...")
        submit_action(user1, "Twisted Bow", "DROP", source="Chambers of Xeric", quantity=1)
        print("   Should complete task 1/3")

        print("\n🎯 Getting Elysian Spirit Shield...")
        submit_action(user2, "Elysian Spirit Shield", "DROP", source="Corporeal Beast", quantity=1)
        print("   Should complete task 2/3")

        print_team_status(team1)

        # TEST 9: Combat 99s (OR with multiple options)
        print_section("TEST 9: Combat 99s - OR Logic")
        print("Testing Tile 14: Combat 99s (Bronze: Any combat 99)")

        print("\n🎯 Getting 99 Attack...")
        submit_action(user1, "99 Attack", "SKILL", quantity=1)
        print("   Should complete Bronze (any combat 99 counts)")

        print_team_status(team1)

        # TEST 10: Barrows
        print_section("TEST 10: Barrows Chests - Simple Grind")
        print("Testing Tile 9: Barrows (Bronze: 50, Silver: 100, Gold: 200)")

        print("\n🎯 Submitting 50 Barrows chests...")
        submit_action(user1, "Barrows", "KC", quantity=50)
        print("   Should complete Bronze")

        print("\n🎯 Submitting 50 more chests (100 total)...")
        submit_action(user2, "Barrows", "KC", quantity=50)
        print("   Should complete Silver")

        print_team_status(team1)

        # FINAL STATS
        print_section("FINAL TEST RESULTS")

        db.session.refresh(team1)

        total_actions = Action.query.count()
        total_tile_statuses = TileStatus.query.filter_by(team_id=team1.id).count()
        total_task_statuses = TaskStatus.query.filter_by(team_id=team1.id).count()
        completed_tasks = TaskStatus.query.filter_by(team_id=team1.id, completed=True).count()

        print(f"\n📊 Database Stats:")
        print(f"   Total actions submitted: {total_actions}")
        print(f"   Tiles with progress: {total_tile_statuses}")
        print(f"   Task statuses created: {total_task_statuses}")
        print(f"   Tasks completed: {completed_tasks}")
        print(f"   Team points: {team1.points}")

        # Show tile breakdown
        print(f"\n📋 Tile Completion Breakdown:")
        tile_statuses = TileStatus.query.filter_by(team_id=team1.id).all()
        from models.new_events import Tile
        for ts in sorted(tile_statuses, key=lambda x: x.tasks_completed, reverse=True)[:10]:
            tile = Tile.query.get(ts.tile_id)
            medal = ["❌", "🥉", "🥈", "🥇"][ts.tasks_completed]
            print(f"   {medal} Tile {tile.index}: {tile.name} - {ts.tasks_completed}/3 tasks")

        print("\n" + "="*70)
        print("✅ ALL MANUAL TESTS COMPLETE!")
        print("="*70 + "\n")

if __name__ == "__main__":
    main()
