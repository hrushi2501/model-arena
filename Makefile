.PHONY: install dev stack stack-full stop

install:
	bun install

dev:
	bun run dev

stack:
	docker compose up --build

stack-full:
	docker compose --profile serving --profile observability up --build

stop:
	docker compose down
