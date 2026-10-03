UV ?= uv

.PHONY: setup hooks lint format typecheck skill-check tests webhook-tests check

setup:
	$(UV) sync

hooks:
	$(UV) tool run pre-commit install

lint:
	$(UV) run ruff check .
	$(UV) run ruff format --check .

format:
	$(UV) run ruff check --fix .
	$(UV) run ruff format .

typecheck:
	$(UV) run mypy

skill-check:
	$(UV) run python .agents/skills/scripts/validate_skills.py

tests: skill-check
	$(UV) run pytest

# Needs Bun, which is not a Python dependency.
webhook-tests:
	bun test ./tests/pr_review_webhook.test.ts

check: lint typecheck tests
