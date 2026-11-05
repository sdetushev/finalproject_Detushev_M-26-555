.PHONY: install run lint format format-check build

install:
	uv sync

run:
	uv run wallet

lint:
	uv run ruff check .

format:
	uv run ruff format .

format-check:
	uv run ruff format --check .

build:
	uv build
