#!/usr/bin/env python3
"""
Setup comprehensive Bingo test data for manual testing
Creates a full bingo event with 25 tiles, 4 teams, and OSRS-themed challenges
"""

import datetime
from datetime import timezone, timedelta
from app import app, db
from models.new_events import Event, Team, TeamMember, Trigger, Tile, Task, Challenge
from models.models import Users
from sqlalchemy import func

def main():
    print("\n" + "="*70)
    print("🎮 BINGO EVENT TEST DATA GENERATOR")
    print("="*70 + "\n")

    with app.app_context():
        # Get existing users
        print("👥 Fetching users...")
        users = Users.query.limit(20).all()
        if len(users) < 4:
            print("❌ Need at least 4 users in the database!")
            return
        print(f"✅ Found {len(users)} users\n")

        # Create event
        print("📅 Creating Bingo event...")
        now = datetime.datetime.now(timezone.utc)
        event = Event(
            name="Winter Bingo 2026",
            start_date=now - timedelta(days=1),
            end_date=now + timedelta(days=30),
            thread_id="1234567890"  # Discord thread ID
        )
        db.session.add(event)
        db.session.flush()
        print(f"✅ Event created: {event.name}\n")

        # Create 4 teams
        print("🎯 Creating 4 teams...")
        team_data = [
            {"name": "Team Zamorak", "image_url": "https://oldschool.runescape.wiki/images/Zamorak_symbol.png"},
            {"name": "Team Saradomin", "image_url": "https://oldschool.runescape.wiki/images/Saradomin_symbol.png"},
            {"name": "Team Guthix", "image_url": "https://oldschool.runescape.wiki/images/Guthix_symbol.png"},
            {"name": "Team Armadyl", "image_url": "https://oldschool.runescape.wiki/images/Armadyl_symbol.png"}
        ]

        teams = []
        for i, team_info in enumerate(team_data):
            team = Team(
                event_id=event.id,
                name=team_info["name"],
                image_url=team_info["image_url"],
                points=0
            )
            db.session.add(team)
            db.session.flush()
            teams.append(team)

            # Assign users to teams (distribute evenly)
            team_users = users[i::4][:5]  # Up to 5 users per team
            for user in team_users:
                member = TeamMember(team_id=team.id, user_id=user.id)
                db.session.add(member)

            print(f"  ✅ {team.name} created with {len(team_users)} members")

        db.session.flush()
        print()

        # Create triggers (OSRS bosses, items, achievements)
        print("🎯 Creating triggers...")
        triggers_data = [
            # Bosses
            ("Vorkath", "KC"), ("Zulrah", "KC"), ("The Gauntlet", "KC"),
            ("Chambers of Xeric", "KC"), ("Theatre of Blood", "KC"),
            ("General Graardor", "KC"), ("Kree'arra", "KC"), ("Commander Zilyana", "KC"),
            ("K'ril Tsutsaroth", "KC"), ("Corporeal Beast", "KC"),
            ("Venenatis", "KC"), ("Callisto", "KC"), ("Vet'ion", "KC"),
            ("Dagannoth Rex", "KC"), ("Dagannoth Prime", "KC"), ("Dagannoth Supreme", "KC"),
            ("Barrows", "KC"), ("King Black Dragon", "KC"), ("Kraken", "KC"),
            ("Thermonuclear Smoke Devil", "KC"), ("Cerberus", "KC"), ("Abyssal Sire", "KC"),

            # Items/Drops
            ("Dragon Warhammer", "DROP"), ("Twisted Bow", "DROP"), ("Elysian Spirit Shield", "DROP"),
            ("Dragon Pickaxe", "DROP"), ("Zenyte Shard", "DROP"), ("Primordial Crystal", "DROP"),
            ("Pegasian Crystal", "DROP"), ("Eternal Crystal", "DROP"), ("Smouldering Stone", "DROP"),
            ("Draconic Visage", "DROP"), ("Abyssal Whip", "DROP"), ("Trident of the Seas", "DROP"),
            ("Tanzanite Fang", "DROP"), ("Magic Fang", "DROP"), ("Serpentine Visage", "DROP"),
            ("Dragon Crossbow", "DROP"), ("Dragon Hunter Lance", "DROP"), ("Avernic Defender Hilt", "DROP"),

            # Skills
            ("99 Attack", "SKILL"), ("99 Strength", "SKILL"), ("99 Defence", "SKILL"),
            ("99 Hitpoints", "SKILL"), ("99 Prayer", "SKILL"), ("99 Magic", "SKILL"),
            ("99 Ranged", "SKILL"), ("99 Runecraft", "SKILL"), ("99 Slayer", "SKILL"),

            # Quests
            ("Dragon Slayer II", "QUEST"), ("Song of the Elves", "QUEST"), ("Sins of the Father", "QUEST"),
            ("A Kingdom Divided", "QUEST"), ("Desert Treasure", "QUEST"),

            # Achievements
            ("Fire Cape", "ACHIEVEMENT"), ("Infernal Cape", "ACHIEVEMENT"), ("Quest Cape", "ACHIEVEMENT"),
            ("Achievement Diary - Elite", "ACHIEVEMENT"), ("Achievement Diary - Hard", "ACHIEVEMENT")
        ]

        triggers = {}
        for name, ttype in triggers_data:
            trigger = Trigger(name=name, type=ttype)
            db.session.add(trigger)
            db.session.flush()
            triggers[name] = trigger

        print(f"✅ Created {len(triggers)} triggers\n")

        # Create 25 tiles (5x5 bingo board)
        print("📋 Creating 25 tiles with tasks and challenges...")

        tile_configs = [
            # Row 1
            {"name": "GWD Starter", "tasks": [
                {"name": "Bronze: 10 GWD KC", "challenges": [("General Graardor", 3), ("Kree'arra", 3), ("Commander Zilyana", 2), ("K'ril Tsutsaroth", 2)]},
                {"name": "Silver: 25 GWD KC", "challenges": [("General Graardor", 7), ("Kree'arra", 6), ("Commander Zilyana", 6), ("K'ril Tsutsaroth", 6)]},
                {"name": "Gold: 50 GWD KC", "challenges": [("General Graardor", 15), ("Kree'arra", 12), ("Commander Zilyana", 12), ("K'ril Tsutsaroth", 11)]}
            ]},
            {"name": "Vorkath Grind", "tasks": [
                {"name": "Bronze: 25 Vorkath", "challenges": [("Vorkath", 25)]},
                {"name": "Silver: 50 Vorkath", "challenges": [("Vorkath", 50)]},
                {"name": "Gold: 100 Vorkath", "challenges": [("Vorkath", 100)]}
            ]},
            {"name": "Zulrah Farm", "tasks": [
                {"name": "Bronze: 25 Zulrah", "challenges": [("Zulrah", 25)]},
                {"name": "Silver: 50 Zulrah", "challenges": [("Zulrah", 50)]},
                {"name": "Gold: 100 Zulrah", "challenges": [("Zulrah", 100)]}
            ]},
            {"name": "Wilderness Boss", "tasks": [
                {"name": "Bronze: 10 Wildy Boss", "challenges": [("Venenatis", 4), ("Callisto", 3), ("Vet'ion", 3)]},
                {"name": "Silver: 25 Wildy Boss", "challenges": [("Venenatis", 9), ("Callisto", 8), ("Vet'ion", 8)]},
                {"name": "Gold: 50 Wildy Boss", "challenges": [("Venenatis", 17), ("Callisto", 17), ("Vet'ion", 16)]}
            ]},
            {"name": "DKs Tribrid", "tasks": [
                {"name": "Bronze: Get 1 of each DK", "challenges": [("Dagannoth Rex", 1), ("Dagannoth Prime", 1), ("Dagannoth Supreme", 1)], "require_all": True},
                {"name": "Silver: 25 DK KC", "challenges": [("Dagannoth Rex", 9), ("Dagannoth Prime", 8), ("Dagannoth Supreme", 8)]},
                {"name": "Gold: 50 DK KC", "challenges": [("Dagannoth Rex", 17), ("Dagannoth Prime", 17), ("Dagannoth Supreme", 16)]}
            ]},

            # Row 2
            {"name": "Raids Beginner", "tasks": [
                {"name": "Bronze: 1 Raid", "challenges": [("Chambers of Xeric", 1), ("Theatre of Blood", 1)]},
                {"name": "Silver: 5 Raids", "challenges": [("Chambers of Xeric", 3), ("Theatre of Blood", 2)]},
                {"name": "Gold: 10 Raids", "challenges": [("Chambers of Xeric", 6), ("Theatre of Blood", 4)]}
            ]},
            {"name": "Corp Beast", "tasks": [
                {"name": "Bronze: 10 Corp", "challenges": [("Corporeal Beast", 10)]},
                {"name": "Silver: 25 Corp", "challenges": [("Corporeal Beast", 25)]},
                {"name": "Gold: 50 Corp", "challenges": [("Corporeal Beast", 50)]}
            ]},
            {"name": "Slayer Bosses", "tasks": [
                {"name": "Bronze: 25 Slayer Boss", "challenges": [("Kraken", 10), ("Thermonuclear Smoke Devil", 8), ("Cerberus", 7)]},
                {"name": "Silver: 50 Slayer Boss", "challenges": [("Kraken", 20), ("Thermonuclear Smoke Devil", 15), ("Cerberus", 15)]},
                {"name": "Gold: 100 Slayer Boss", "challenges": [("Kraken", 40), ("Thermonuclear Smoke Devil", 30), ("Cerberus", 30)]}
            ]},
            {"name": "The Gauntlet", "tasks": [
                {"name": "Bronze: 10 Gauntlet", "challenges": [("The Gauntlet", 10)]},
                {"name": "Silver: 25 Gauntlet", "challenges": [("The Gauntlet", 25)]},
                {"name": "Gold: 50 Gauntlet", "challenges": [("The Gauntlet", 50)]}
            ]},
            {"name": "Barrows", "tasks": [
                {"name": "Bronze: 50 Chests", "challenges": [("Barrows", 50)]},
                {"name": "Silver: 100 Chests", "challenges": [("Barrows", 100)]},
                {"name": "Gold: 200 Chests", "challenges": [("Barrows", 200)]}
            ]},

            # Row 3
            {"name": "Mega Rares", "tasks": [
                {"name": "Get Twisted Bow", "challenges": [("Twisted Bow", 1)]},
                {"name": "Get Ely", "challenges": [("Elysian Spirit Shield", 1)]},
                {"name": "Get DWH", "challenges": [("Dragon Warhammer", 1)]}
            ]},
            {"name": "Zulrah Uniques", "tasks": [
                {"name": "Get Tanzanite Fang", "challenges": [("Tanzanite Fang", 1)]},
                {"name": "Get Magic Fang", "challenges": [("Magic Fang", 1)]},
                {"name": "Get Serpentine Visage", "challenges": [("Serpentine Visage", 1)]}
            ]},
            {"name": "FREE SPACE", "tasks": [
                {"name": "Participate in Event", "challenges": [("Barrows", 1)]}  # Easy freebie
            ]},
            {"name": "Cerberus Crystals", "tasks": [
                {"name": "Get Primordial", "challenges": [("Primordial Crystal", 1)]},
                {"name": "Get Pegasian", "challenges": [("Pegasian Crystal", 1)]},
                {"name": "Get Eternal", "challenges": [("Eternal Crystal", 1)]}
            ]},
            {"name": "Combat 99s", "tasks": [
                {"name": "Any Combat 99", "challenges": [("99 Attack", 1), ("99 Strength", 1), ("99 Defence", 1), ("99 Hitpoints", 1), ("99 Prayer", 1), ("99 Magic", 1), ("99 Ranged", 1)]},
                {"name": "3 Combat 99s", "challenges": [("99 Attack", 1), ("99 Strength", 1), ("99 Defence", 1), ("99 Hitpoints", 1), ("99 Prayer", 1), ("99 Magic", 1), ("99 Ranged", 1)], "quantity": 3},
                {"name": "Max Combat", "challenges": [("99 Attack", 1), ("99 Strength", 1), ("99 Defence", 1), ("99 Hitpoints", 1), ("99 Prayer", 1), ("99 Magic", 1), ("99 Ranged", 1)], "require_all": True}
            ]},

            # Row 4
            {"name": "Quest Master", "tasks": [
                {"name": "DS2", "challenges": [("Dragon Slayer II", 1)]},
                {"name": "SOTE", "challenges": [("Song of the Elves", 1)]},
                {"name": "Quest Cape", "challenges": [("Quest Cape", 1)]}
            ]},
            {"name": "Grandmaster Quests", "tasks": [
                {"name": "Complete DS2", "challenges": [("Dragon Slayer II", 1)]},
                {"name": "Complete SOTE", "challenges": [("Song of the Elves", 1)]},
                {"name": "Complete SOTF", "challenges": [("Sins of the Father", 1)]}
            ]},
            {"name": "Capes", "tasks": [
                {"name": "Fire Cape", "challenges": [("Fire Cape", 1)]},
                {"name": "Infernal Cape", "challenges": [("Infernal Cape", 1)]},
                {"name": "Quest Cape", "challenges": [("Quest Cape", 1)]}
            ]},
            {"name": "Elite Diaries", "tasks": [
                {"name": "1 Elite Diary", "challenges": [("Achievement Diary - Elite", 1)]},
                {"name": "3 Elite Diaries", "challenges": [("Achievement Diary - Elite", 3)]},
                {"name": "All Elite Diaries", "challenges": [("Achievement Diary - Elite", 12)]}
            ]},
            {"name": "Skill Grind", "tasks": [
                {"name": "Any 99", "challenges": [("99 Runecraft", 1), ("99 Slayer", 1)]},
                {"name": "RC or Slayer 99", "challenges": [("99 Runecraft", 1), ("99 Slayer", 1)]},
                {"name": "Both RC and Slayer", "challenges": [("99 Runecraft", 1), ("99 Slayer", 1)], "require_all": True}
            ]},

            # Row 5
            {"name": "ToB Purples", "tasks": [
                {"name": "Avernic Hilt", "challenges": [("Avernic Defender Hilt", 1)]},
                {"name": "Any ToB Drop", "challenges": [("Avernic Defender Hilt", 1)]},
                {"name": "Complete ToB", "challenges": [("Theatre of Blood", 1)]}
            ]},
            {"name": "CoX Purples", "tasks": [
                {"name": "Get 2 CoX Mega Rares", "challenges": [("Twisted Bow", 1), ("Dragon Hunter Lance", 1), ("Dragon Crossbow", 1)], "parent_quantity": 2},
                {"name": "Any Visage OR Both Fangs", "challenges": [
                    ("Draconic Visage", 1), ("Serpentine Visage", 1),  # Either visage (OR)
                    (("Tanzanite Fang", 1), ("Magic Fang", 1))  # OR both fangs (AND)
                ], "complex_or": True}
            ]},
            {"name": "Zenytes", "tasks": [
                {"name": "1 Zenyte", "challenges": [("Zenyte Shard", 1)]},
                {"name": "2 Zenytes", "challenges": [("Zenyte Shard", 2)]},
                {"name": "4 Zenytes", "challenges": [("Zenyte Shard", 4)]}
            ]},
            {"name": "Visages", "tasks": [
                {"name": "Draconic Visage", "challenges": [("Draconic Visage", 1)]},
                {"name": "Serpentine Visage", "challenges": [("Serpentine Visage", 1)]},
                {"name": "Any Visage", "challenges": [("Draconic Visage", 1), ("Serpentine Visage", 1)]}
            ]},
            {"name": "Rare Uniques", "tasks": [
                {"name": "D Pick", "challenges": [("Dragon Pickaxe", 1)]},
                {"name": "Abyssal Whip", "challenges": [("Abyssal Whip", 1)]},
                {"name": "Trident", "challenges": [("Trident of the Seas", 1)]}
            ]}
        ]

        for index, tile_config in enumerate(tile_configs):
            tile = Tile(
                event_id=event.id,
                index=index,
                name=tile_config["name"]
            )
            db.session.add(tile)
            db.session.flush()

            for task_config in tile_config["tasks"]:
                task = Task(
                    tile_id=tile.id,
                    name=task_config["name"],
                    require_all=task_config.get("require_all", False)
                )
                db.session.add(task)
                db.session.flush()

                # Create challenges for this task
                # Check if this task uses parent challenge pattern
                parent_quantity = task_config.get("parent_quantity")

                if parent_quantity:
                    # Create parent challenge (need X of Y options)
                    # Use first trigger as dummy for parent
                    first_trigger = task_config["challenges"][0]
                    if isinstance(first_trigger, tuple):
                        trigger_name, _ = first_trigger
                    else:
                        trigger_name = first_trigger

                    parent_challenge = Challenge(
                        task_id=task.id,
                        trigger_id=triggers[trigger_name].id,  # Dummy trigger
                        quantity=parent_quantity,  # e.g., need 2 of the children
                        require_all=False
                    )
                    db.session.add(parent_challenge)
                    db.session.flush()

                    # Create child challenges
                    for challenge_data in task_config["challenges"]:
                        if isinstance(challenge_data, tuple):
                            trigger_name, quantity = challenge_data
                        else:
                            trigger_name = challenge_data
                            quantity = 1

                        if trigger_name in triggers:
                            child_challenge = Challenge(
                                task_id=task.id,
                                parent_challenge_id=parent_challenge.id,
                                trigger_id=triggers[trigger_name].id,
                                quantity=quantity,
                                require_all=False
                            )
                            db.session.add(child_challenge)
                else:
                    # Regular challenges (no parent)
                    for challenge_data in task_config["challenges"]:
                        if isinstance(challenge_data, tuple):
                            trigger_name, quantity = challenge_data
                        else:
                            trigger_name = challenge_data
                            quantity = 1

                        if trigger_name in triggers:
                            challenge = Challenge(
                                task_id=task.id,
                                trigger_id=triggers[trigger_name].id,
                                quantity=quantity,
                                require_all=task.require_all
                            )
                            db.session.add(challenge)

            print(f"  ✅ Tile {index}: {tile.name} ({len(tile_config['tasks'])} tasks)")

        db.session.commit()
        print(f"\n✅ Created all 25 tiles successfully!\n")

        # Print summary
        print("="*70)
        print("🎉 TEST DATA SUMMARY")
        print("="*70)
        print(f"Event: {event.name}")
        print(f"Teams: {len(teams)}")
        for team in teams:
            member_count = TeamMember.query.filter_by(team_id=team.id).count()
            print(f"  - {team.name}: {member_count} members")
        print(f"Tiles: 25 (5x5 bingo board)")
        print(f"Triggers: {len(triggers)}")
        print(f"\nEvent runs from {event.start_date.strftime('%Y-%m-%d')} to {event.end_date.strftime('%Y-%m-%d')}")
        print("\n" + "="*70)
        print("✅ READY FOR TESTING!")
        print("="*70 + "\n")

if __name__ == "__main__":
    main()
