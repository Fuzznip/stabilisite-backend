#!/usr/bin/env python3
"""
Fix OR challenges (require_all=False) where parent has quantity > 1
Set all child/grandchild quantities to NULL so submissions can repeat
"""

from app import app, db
from models.new_events import Task, Challenge

def fix_challenge_tree(challenge, level=0):
    """Recursively fix a challenge and its children"""
    fixed_count = 0
    
    children = Challenge.query.filter_by(parent_challenge_id=challenge.id).all()
    
    if children:
        # This is a parent/grandparent
        for child in children:
            # Set child quantity to NULL if parent has quantity > 1
            if challenge.quantity and challenge.quantity > 1:
                if child.quantity != None:
                    indent = "  " * (level + 1)
                    print(f"{indent}Setting child {child.id[:8]}... quantity: {child.quantity} -> NULL")
                    child.quantity = None
                    fixed_count += 1
            
            # Recursively fix child's children
            fixed_count += fix_challenge_tree(child, level + 1)
    
    return fixed_count

def main():
    with app.app_context():
        # Find all OR tasks (require_all=False)
        tasks = Task.query.filter_by(require_all=False).all()
        
        print(f"Found {len(tasks)} OR tasks (require_all=False)\n")
        
        total_fixed = 0
        tasks_affected = 0
        
        for task in tasks:
            challenges = Challenge.query.filter_by(task_id=task.id).all()
            top_level = [c for c in challenges if c.parent_challenge_id is None]
            
            task_fixed = 0
            for top in top_level:
                if top.quantity and top.quantity > 1:
                    # This parent has quantity > 1, fix its children
                    print(f"Task {task.id[:8]}... - Parent quantity={top.quantity}")
                    task_fixed += fix_challenge_tree(top, 0)
                    
            if task_fixed > 0:
                print(f"  Fixed {task_fixed} challenges\n")
                total_fixed += task_fixed
                tasks_affected += 1
        
        if total_fixed > 0:
            print(f"\n{'='*60}")
            print(f"Total: Fixed {total_fixed} challenges across {tasks_affected} tasks")
            print(f"{'='*60}\n")
            
            db.session.commit()
            print("✅ Changes committed!")
        else:
            print("✅ No changes needed - all challenges already correct!")

if __name__ == "__main__":
    main()
