#!/usr/bin/env python3
"""
Reset Test Data - Clear all actions and progress for fresh testing

This script will:
1. Delete all ChallengeProof records
2. Delete all ChallengeStatus records
3. Delete all TaskStatus records
4. Delete all TileStatus records
5. Delete all Action records
6. Reset team points to 0

This allows starting fresh with clean test data while keeping the event structure intact.
"""

from app import app, db
from models.new_events import (
    Action, ChallengeProof, ChallengeStatus, TaskStatus, TileStatus, Team
)

def main():
    with app.app_context():
        print("Current state:")
        print(f"  Actions: {Action.query.count()}")
        print(f"  ChallengeProofs: {ChallengeProof.query.count()}")
        print(f"  ChallengeStatuses: {ChallengeStatus.query.count()}")
        print(f"  TaskStatuses: {TaskStatus.query.count()}")
        print(f"  TileStatuses: {TileStatus.query.count()}")

        teams = Team.query.all()
        print(f"\nTeam Points:")
        for team in teams:
            print(f"  {team.name}: {team.points}")

        print("\n" + "="*70)
        print("This will DELETE all test progress and reset to clean state!")
        print("="*70)
        response = input("\nContinue? (yes/no): ")

        if response.lower() != 'yes':
            print("Aborted.")
            return

        print("\nDeleting test data...")

        # Delete in correct order (respecting foreign keys)
        deleted_proofs = ChallengeProof.query.delete()
        print(f"  Deleted {deleted_proofs} ChallengeProof records")

        deleted_challenge_statuses = ChallengeStatus.query.delete()
        print(f"  Deleted {deleted_challenge_statuses} ChallengeStatus records")

        deleted_task_statuses = TaskStatus.query.delete()
        print(f"  Deleted {deleted_task_statuses} TaskStatus records")

        deleted_tile_statuses = TileStatus.query.delete()
        print(f"  Deleted {deleted_tile_statuses} TileStatus records")

        deleted_actions = Action.query.delete()
        print(f"  Deleted {deleted_actions} Action records")

        # Reset team points
        for team in teams:
            team.points = 0
        print(f"  Reset points for {len(teams)} teams")

        db.session.commit()

        print("\n✅ Test data reset complete!")
        print("\nNew state:")
        print(f"  Actions: {Action.query.count()}")
        print(f"  ChallengeProofs: {ChallengeProof.query.count()}")
        print(f"  ChallengeStatuses: {ChallengeStatus.query.count()}")
        print(f"  TaskStatuses: {TaskStatus.query.count()}")
        print(f"  TileStatuses: {TileStatus.query.count()}")
        print(f"\nAll teams now have 0 points. Ready for fresh testing!")

if __name__ == "__main__":
    main()
