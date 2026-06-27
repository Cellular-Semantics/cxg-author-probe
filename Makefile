.PHONY: help models test lint build clean

help:
	@echo "make models   - regenerate Pydantic models from schemas/*.schema.json"
	@echo "make test     - run pytest"
	@echo "make lint     - ruff"
	@echo "make build    - build sdist + wheel"
	@echo "make clean    - remove build artefacts"

models:
	python scripts/generate_models.py

test:
	pytest -v

lint:
	ruff check src tests scripts

build:
	python -m build

clean:
	rm -rf build dist *.egg-info src/*.egg-info
	find . -name __pycache__ -type d -exec rm -rf {} +
