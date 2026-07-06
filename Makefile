.PHONY: up down logs migrate test golden requeue

up:
	docker compose up --build

down:
	docker compose down -v

logs:
	docker compose logs -f

migrate:
	docker compose run --rm migrate

test:
	docker compose run --rm backend pytest /app/backend/tests /app/cv-worker/tests

# ゴールデンセット回帰（10 §ゴールデンセット。実装はPhase 1で拡充）
golden:
	docker compose run --rm worker-gpu python -m cvpipeline.golden_runner

# 失敗したmatchの手動再投入（10 §冪等性・リトライ）
requeue:
	docker compose run --rm backend python -m app.jobs.requeue $(MATCH)
