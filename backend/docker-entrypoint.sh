#!/bin/sh
set -e
# Migrations-on-boot is a single-instance-only pattern (Phase 1 scope). Multiple
# replicas racing "alembic upgrade head" against a fresh DB isn't guarded against —
# re-evaluate before running more than one backend replica.
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
