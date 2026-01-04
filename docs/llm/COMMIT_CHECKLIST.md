# Commit Checklist - Event System Improvements

## Summary
Two major improvements implemented:
1. Challenge proof optimization (50% reduction in database records)
2. Action type classification (semantic clarity for KC/DROP/QUEST/etc)

## Files to Commit

### Core Implementation (8 modified)
- [x] `models/new_events.py` - Added type column to Action model
- [x] `services/action_processor.py` - Proof optimization + action_type support
- [x] `endpoints/v2/actions.py` - Type validation and processing
- [x] `endpoints/v2/events.py` - (Previous session work)
- [x] `endpoints/v2/teams.py` - (Previous session work)
- [x] `helper/helpers.py` - (Previous session work)
- [x] `endpoints/events/sp3_game.py` - (Previous session work)
- [x] `event_handlers/stability_party/stability_party_handler.py` - (Previous work)

### Documentation & Config (4 new)
- [x] `static/swagger/v2_events.json` - Corrected API documentation
- [x] `static/swagger/base.json` - Verified tags
- [x] `IMPROVEMENT_SUGGESTIONS.md` - Analysis and recommendations
- [x] `SESSION_SUMMARY.md` - Complete session documentation
- [x] `migrations/versions/002_add_action_type_and_optimize_proofs.py` - DB migration

### Should NOT Commit
- [ ] `.venv/` - Virtual environment (add to .gitignore if not already)
- [ ] `railway_dump.sql` - Database backup (add to .gitignore or delete)

## Pre-Commit Checks

### 1. Swagger Validation
```bash
python3 scripts/combine_swagger.py
# Should output: Successfully created combined swagger file
```

### 2. Code Syntax
```bash
python3 -m py_compile models/new_events.py
python3 -m py_compile services/action_processor.py
python3 -m py_compile endpoints/v2/actions.py
```

### 3. Migration Syntax
```bash
python3 -m py_compile migrations/versions/002_add_action_type_and_optimize_proofs.py
```

## Commit Message Suggestion

```
feat: optimize challenge proofs and add action type classification

Major improvements to the new event system:

1. Challenge Proof Optimization (50% reduction)
   - Added intelligent proof creation logic in action_processor.py
   - Only create proofs for active tasks and completions
   - Prevents 3x proof creation for bronze/silver/gold tiers
   - Results: 1.5 proofs per action (down from 3.0)

2. Action Type Classification
   - Added 'type' column to actions table (KC/DROP/QUEST/ACHIEVEMENT/DIARY/SKILL)
   - Added type index for filtering performance
   - Updated API to validate and accept action_type parameter
   - Backward compatible (defaults to 'DROP')

3. Swagger Documentation Fixes
   - Corrected all v2 endpoint schemas to match implementations
   - Fixed NewChallenge, NewTask, NewTrigger schemas
   - Added action type examples and enum values

Files changed:
- models/new_events.py - Action.type column
- services/action_processor.py - Proof optimization logic
- endpoints/v2/actions.py - Type validation
- static/swagger/v2_events.json - Complete rewrite
- migrations/versions/002_*.py - Migration for type column

Testing:
- Verified 50% reduction in proof creation (4 actions = 6 proofs vs 12)
- Tested KC and DROP action types
- Confirmed backward compatibility
- Swagger combined successfully

🤖 Generated with Claude Code
Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
```

## Post-Commit Steps

### Railway Deployment
1. Push to repository
2. Connect to Railway DB:
   ```bash
   # Use Railway CLI or direct connection
   railway connect
   ```
3. Run migration:
   ```bash
   flask db upgrade
   # OR manually:
   # psql -h [host] -U [user] -d [db] < migrations/versions/002_add_action_type_and_optimize_proofs.py
   ```
4. Verify type column exists:
   ```sql
   SELECT column_name, data_type, is_nullable, column_default
   FROM information_schema.columns
   WHERE table_schema = 'new_stability'
     AND table_name = 'actions'
     AND column_name = 'type';
   ```

### Frontend Updates Needed
1. Update action submission to include `type` parameter
2. Add type selection UI (dropdown: KC/DROP/QUEST/etc)
3. Display proofs with associated task difficulty
4. Add type-based filtering to action logs

## Rollback Plan

If issues arise:
```bash
# Revert migration
flask db downgrade

# OR manually:
DROP INDEX new_stability.idx_actions_type;
ALTER TABLE new_stability.actions DROP COLUMN type;
```

## Testing in Production

After deployment, test:
1. Submit KC action: `{"type": "KC", "name": "Vorkath", "quantity": 1}`
2. Submit DROP action: `{"type": "DROP", "name": "Magic fang", "source": "Zulrah"}`
3. Submit action without type (backward compat): `{"name": "Some item"}`
4. Verify proofs created correctly (check challenge_proofs table)
5. Verify bingo detection still works
