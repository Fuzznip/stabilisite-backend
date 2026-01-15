#!/usr/bin/env python3
"""
Fix Barrows set intermediate parents to require all 4 pieces (quantity=4)
"""

from app import app, db
from models.new_events import Tile, Task, Challenge

def main():
    with app.app_context():
        tile3 = Tile.query.filter_by(index=3, name="Ironman Pun Here").first()
        
        if not tile3:
            print("ERROR: Tile 3 not found")
            return
        
        tasks = Task.query.filter_by(tile_id=tile3.id).all()
        task3 = tasks[2]
        
        print(f"Fixing Tile 3 Task 3: {task3.id}")
        
        challenges = Challenge.query.filter_by(task_id=task3.id).all()
        grandparent = [c for c in challenges if c.parent_challenge_id is None][0]
        
        print(f"Grandparent: {grandparent.id}")
        print(f"  Current quantity: {grandparent.quantity}")
        
        # Get intermediate parents (Barrows sets)
        intermediate_parents = Challenge.query.filter_by(parent_challenge_id=grandparent.id).all()
        print(f"\nFound {len(intermediate_parents)} Barrows sets")
        
        fixed_count = 0
        for parent in intermediate_parents:
            # Count how many pieces this set has
            pieces = Challenge.query.filter_by(parent_challenge_id=parent.id).all()
            piece_count = len(pieces)
            
            if parent.quantity != piece_count:
                print(f"  Fixing set {parent.id}: quantity {parent.quantity} -> {piece_count}")
                parent.quantity = piece_count
                fixed_count += 1
            else:
                print(f"  Set {parent.id}: already correct (quantity={piece_count})")
        
        if fixed_count > 0:
            print(f"\nCommitting changes...")
            db.session.commit()
            print(f"✅ Fixed {fixed_count} Barrows sets!")
        else:
            print("\n✅ All sets already correct!")

if __name__ == "__main__":
    main()
