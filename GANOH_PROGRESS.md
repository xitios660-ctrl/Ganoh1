# GANOH_PROGRESS.md

## Projeto
GANOH continuity / independence from the legacy Emergent deployment.

## Current production state
- Frontend production: https://ganoh.onrender.com
- Render backend: https://ganoh1.onrender.com
- Repository: xitios660-ctrl/Ganoh1
- Main commit used for infrastructure bootstrap: 6805956bfd3f41b385928151c115f3d4d3c7afc1
- The static frontend rebuild for that commit is live.
- The Render backend was rebuilt from the same commit and is live in maintenance mode.
- Safety flags on Render backend:
  - MIGRATION_PENDING=true
  - SCHEDULER_ENABLED=false
  - WHATSAPP_SEND_ENABLED=false
- No financial migration has been declared complete.
- Do not switch the frontend away from charts-3.emergent.host until destination data has been validated.

## Continuity branch
Branch: ganoh/continuity-sync

### Completed
- Added scripts/sync_from_emergent.py.
- The sync is source-read-only and destination-upsert-only.
- Dry-run is the default.
- No destination deletion is performed.
- Operational continuity coverage:
  - prazo customers
  - unpaid prazo debt reconstruction
  - prazo payment history classification
  - stock
  - menu
  - adicionais
  - latest live orders
  - expenses when source gestor credentials are provided
  - raw latest endpoint snapshots for audit/recovery
- Added .github/workflows/ganoh-hourly-sync.yml.
- Workflow is configured hourly but is not active while it remains off the default branch.
- Workflow defaults to dry-run through GANOH_SYNC_APPLY/GANOH_SYNC_DRY_RUN variables.
- No credentials are stored in repository files.

### Known source limitation
The legacy API does not expose a complete raw historical order export. The sync therefore preserves current operational state and unpaid prazo continuity, and stores endpoint snapshots, but must not be described as a full byte-for-byte database migration.

## Railway
Project: Ganoh Database
- MongoDB-UjdL is the persistent MongoDB service and remains untouched.
- Ganoh-App exists but has never had a usable first deploy because Railway cannot access the private GitHub repository through its current GitHub integration.
- Ganoh-Backend was prepared in maintenance mode but has the same private-repo access blocker.
- Public TCP proxy exists for MongoDB port 27017, but the connector does not reveal the proxy hostname or sealed Mongo credentials.
- Attempts to resolve cross-service secret references in temporary diagnostic image services did not expose or alter the real MongoDB.
- Temporary diagnostic services were scrubbed of source-Mongo/password/proxy references and set to restartPolicy NEVER.

## Render cron
A free Render cron was attempted for the hourly sync, but Render rejected the free plan for cron jobs. No paid cron was created, avoiding an unapproved charge.

## Branch isolation
Financial fixes remain isolated on ganoh/staged-audit.
Continuity work is isolated on ganoh/continuity-sync.
Do not merge either branch into production until its own tests pass.

## Next safe actions
1. Obtain a usable destination MongoDB connection path without exposing root credentials:
   - preferred: dedicated ganoh_render user + public Railway TCP proxy, or
   - another approved MongoDB endpoint.
2. Store that URI only as a secret (Render/GitHub), never in the repository.
3. Run scripts/sync_from_emergent.py in dry-run and verify endpoint counts.
4. Run apply mode once and verify counts/documents in destination.
5. Repeat apply once to prove idempotency/no duplication.
6. Disable MIGRATION_PENDING only after destination verification.
7. Point the production frontend to the Ganoh backend only after the backend has validated data.
8. Then enable the hourly workflow by merging the continuity workflow to the default branch and setting sync secrets/variables.

## Last continuity commits
- e3dd716dc8b9b42c2821a6b7a87c7cf56647d079 — Add safe Emergent continuity sync script
- 11274e97cdb014adef53313f3f46bb4f917f403f — Allow sync apply mode through environment flag
- e794b33c2c9f0f72948fab2179b1dda325a2a1ad — Prepare hourly continuity sync workflow in dry-run mode

## Current blocker
The only blocker to a safe applied sync is destination MongoDB connectivity/credentials. Do not bypass this by publishing secrets or by making the private repository public.
