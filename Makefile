.PHONY: install dev test lint migrate seed up
install:
	pip install -r requirements-dev.txt
dev:
	uvicorn app.main:app --reload
test:
	pytest --cov=app
lint:
	ruff check .
migrate:
	alembic upgrade head
seed:
	python -m scripts.seed_demo
up:
	docker compose up --build
