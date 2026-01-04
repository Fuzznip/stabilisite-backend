import json
import pytest
from app import app, db
from models.models import Users, RaidTiers, RaidTierApplication, RaidTierLog
from sqlalchemy.sql import text
import datetime

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            yield client
            db.session.remove()
            db.drop_all()

@pytest.fixture
def setup_raid_tiers():
    raid_tiers = [
        RaidTiers(id="fed63e54-ebc7-4198-8461-95fb7d5e4f0c", tier_name="Chambers of Xeric", tier_order=0, tier_points=0),
        RaidTiers(id="bd9dbfe0-499c-4adb-9f01-d6ee1caf6187", tier_name="Chambers of Xeric", tier_order=1, tier_points=50),
        RaidTiers(id="29273252-7f2b-4a6a-9ff5-5d54e401ed4f", tier_name="Chambers of Xeric", tier_order=2, tier_points=50),
        RaidTiers(id="55e50048-486e-46bc-8667-1d38f746e0a5", tier_name="Chambers of Xeric", tier_order=3, tier_points=50),
        RaidTiers(id="c736c227-bfa8-44db-a9af-24243a9ad501", tier_name="Chambers of Xeric", tier_order=4, tier_points=75),
        RaidTiers(id="38354556-6311-4646-93de-633e2ce29235", tier_name="Chambers of Xeric", tier_order=5, tier_points=75),
        RaidTiers(id="07bcac4f-d3e5-4035-9f49-34bcf8df2a91", tier_name="Chambers of Xeric", tier_order=6, tier_points=100),
        RaidTiers(id="2564d82e-8f00-40eb-803e-0e52ba340d6a", tier_name="Chambers of Xeric", tier_order=7, tier_points=100),
    ]
    db.session.bulk_save_objects(raid_tiers)
    db.session.commit()

def test_create_raid_tier_application(client, setup_raid_tiers):
    # Create a user
    user = Users(discord_id="12345", runescape_name="TestUser", is_active=True)
    db.session.add(user)
    db.session.commit()

    # Create a raid tier application
    data = {
        "user_id": "12345",
        "target_raid_tier_id": "bd9dbfe0499c4adb9f01d6ee1caf6187",
        "runescape_name": "TestUser"
    }
    response = client.post("/applications/raidTier", json=data)
    assert response.status_code == 201
    response_data = json.loads(response.data)
    assert response_data["user_id"] == "12345"
    assert response_data["target_raid_tier_id"] == "bd9dbfe0-499c-4adb-9f01-d6ee1caf6187"
    assert response_data["runescape_name"] == "TestUser"
    assert response_data["status"] == "Pending"

    # Get the user
    user = Users.query.filter_by(discord_id="12345").first()
    assert user is not None
    assert user.runescape_name == "TestUser"
    assert user.raid_tier_points == 0  # Points should be 0 initially
    assert user.rank_points == 0  # Rank points should be 0 initially

def test_accept_raid_tier_application(client, setup_raid_tiers):
    # Create a user
    user = Users(discord_id="12345", runescape_name="TestUser", is_active=True)
    db.session.add(user)
    db.session.commit()
    
    # Create an application for tier 1
    application = {
        "user_id": user.discord_id,
        "runescape_name": user.runescape_name,
        "proof": "http://example.com/proof_tier1",
        "target_raid_tier_id": RaidTiers.query.filter_by(tier_order=1).first().id
    }
    response = client.post("/applications/raidTier", json=application)
    assert response.status_code == 201

    # Accept the application
    application_id = json.loads(response.data)["id"]
    response = client.put(f"/applications/raidTier/{application_id}/accept")
    assert response.status_code == 200

    # Verify points and tier progression
    user = Users.query.filter_by(discord_id=user.discord_id).first()
    assert user.raid_tier_points == 50  # Points from tier 0 to tier 1
    assert user.rank_points == 50  # Rank points should be updated

def test_apply_tier_4_from_0(client, setup_raid_tiers):
    # Create a user
    user = Users(discord_id="12345", runescape_name="TestUser", is_active=True)
    db.session.add(user)
    db.session.commit()

    # Create an application for tier 4
    application = {
        "user_id": user.discord_id,
        "runescape_name": user.runescape_name,
        "proof": "http://example.com/proof_tier4",
        "target_raid_tier_id": RaidTiers.query.filter_by(tier_order=4).first().id
    }
    response = client.post("/applications/raidTier", json=application)
    assert response.status_code == 201

    application_id = json.loads(response.data)["id"]

    # Accept the application
    response = client.put(f"/applications/raidTier/{application_id}/accept")
    assert response.status_code == 200

    # Verify points and tier progression
    user = Users.query.filter_by(discord_id=user.discord_id).first()
    assert user.raid_tier_points == 225  # Points from tier 0 to tier 4

def test_apply_tier_3_then_tier_7(client, setup_raid_tiers):
    # Create a user
    user = Users(discord_id="12345", runescape_name="TestUser", is_active=True)
    db.session.add(user)
    db.session.commit()

    # Apply for tier 3
    application_tier_3 = {
        "user_id": user.discord_id,
        "runescape_name": user.runescape_name,
        "proof": "http://example.com/proof_tier3",
        "target_raid_tier_id": RaidTiers.query.filter_by(tier_order=3).first().id
    }
    response = client.post(
        "/applications/raidTier",
        json=application_tier_3,
        headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 201

    application_id_tier_3 = json.loads(response.data)["id"]

    # Accept the application for tier 3
    response = client.put(f"/applications/raidTier/{application_id_tier_3}/accept")
    assert response.status_code == 200

    # Verify points after tier 3
    user = Users.query.filter_by(discord_id=user.discord_id).first()
    assert user.raid_tier_points == 150  # Points from tier 0 to tier 3

    # Apply for tier 7
    application_tier_7 = {
        "user_id": user.discord_id,
        "runescape_name": user.runescape_name,
        "proof": "http://example.com/proof_tier7",
        "target_raid_tier_id": RaidTiers.query.filter_by(tier_order=7).first().id
    }
    response = client.post(
        "/applications/raidTier",
        json=application_tier_7,
        headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 201

    application_id_tier_7 = json.loads(response.data)["id"]

    # Accept the application for tier 7
    response = client.put(f"/applications/raidTier/{application_id_tier_7}/accept")
    assert response.status_code == 200

    # Verify points after tier 7
    user = Users.query.filter_by(discord_id=user.discord_id).first()
    assert user.raid_tier_points == 500  # Points from tier 0 to tier 7

def test_apply_tier_5_then_tier_3(client, setup_raid_tiers):
    # Create a user
    user = Users(discord_id="12345", runescape_name="TestUser", is_active=True)
    db.session.add(user)
    db.session.commit()

    # Apply for tier 5
    application_tier_5 = {
        "user_id": user.discord_id,
        "runescape_name": user.runescape_name,
        "proof": "http://example.com/proof_tier5",
        "target_raid_tier_id": RaidTiers.query.filter_by(tier_order=5).first().id
    }
    response = client.post("/applications/raidTier", json=application_tier_5)
    assert response.status_code == 201

    application_id_tier_5 = json.loads(response.data)["id"]

    # Accept the application for tier 5
    response = client.put(f"/applications/raidTier/{application_id_tier_5}/accept")
    assert response.status_code == 200

    # Verify points after tier 5
    user = Users.query.filter_by(discord_id=user.discord_id).first()
    assert user.raid_tier_points == 300  # Points from tier 0 to tier 5

    # Attempt to apply for tier 3
    application_tier_3 = {
        "user_id": user.discord_id,
        "runescape_name": user.runescape_name,
        "proof": "http://example.com/proof_tier3",
        "target_raid_tier_id": RaidTiers.query.filter_by(tier_order=3).first().id
    }
    response = client.post("/applications/raidTier", json=application_tier_3)
    assert response.status_code == 400  # Should fail as tier 3 is lower than tier 5

def test_apply_tier_3_then_tier_6(client, setup_raid_tiers):
    # Create a user
    user = Users(discord_id="12345", runescape_name="TestUser", is_active=True)
    db.session.add(user)
    db.session.commit()

    # Apply for tier 3
    application_tier_3 = {
        "user_id": user.discord_id,
        "runescape_name": user.runescape_name,
        "proof": "http://example.com/proof_tier3",
        "target_raid_tier_id": RaidTiers.query.filter_by(tier_order=3).first().id
    }
    response = client.post(
        "/applications/raidTier",
        json=application_tier_3,
        headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 201

    application_id_tier_3 = json.loads(response.data)["id"]

    # Apply for tier 6
    application_tier_6 = {
        "user_id": user.discord_id,
        "runescape_name": user.runescape_name,
        "proof": "http://example.com/proof_tier6",
        "target_raid_tier_id": RaidTiers.query.filter_by(tier_order=6).first().id
    }
    response = client.post(
        "/applications/raidTier",
        json=application_tier_6,
        headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 201

    application_id_tier_6 = json.loads(response.data)["id"]

    # Accept the application for tier 6
    response = client.put(
        f"/applications/raidTier/{application_id_tier_6}/accept",
        headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 200

    # Verify points after tier 6
    user = Users.query.filter_by(discord_id=user.discord_id).first()
    assert user.raid_tier_points == 400  # Points from tier 0 to tier 6

    # Attempt to accept the application for tier 3
    response = client.put(
        f"/applications/raidTier/{application_id_tier_3}/accept",
        headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 400  # Should fail as tier 3 is lower than tier 6
