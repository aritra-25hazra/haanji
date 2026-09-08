# Everything a reviewer needs, without reading the README first.
.PHONY: help setup test selftest demo bench verify docker clean

help:
	@echo "make setup     install the engine and its test dependencies"
	@echo "make demo      run one narrated call at real speed"
	@echo "make test      run the engine test suite"
	@echo "make selftest  run every packaged scenario in every vertical pack"
	@echo "make bench     regenerate research/results.json from scratch"
	@echo "make docker    bring the whole system up with Docker Compose"

setup:
	cd engine && pip install -e ".[dev]"

test:
	cd engine && pytest -q

selftest:
	cd engine && python -m haanji.cli selftest --speed 60

demo:
	cd engine && python -m haanji.cli demo

bench:
	cd engine && python -m haanji.bench --reps 5 --speed 60

verify:
	cd engine && python -m haanji.cli packs

docker:
	docker compose up --build

clean:
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	rm -rf engine/.pytest_cache console/dist core-api/target
