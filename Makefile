# Everything a reviewer needs, without reading the README first.
.PHONY: help setup test selftest demo bench verify docker clean dist docs-sync docs report

help:
	@echo "make setup     install the engine and its test dependencies"
	@echo "make demo      run one narrated call at real speed"
	@echo "make test      run the engine test suite"
	@echo "make selftest  run every packaged scenario in every vertical pack"
	@echo "make bench     regenerate research/results.json from scratch"
	@echo "make docker    bring the whole system up with Docker Compose"
	@echo "make dist      build the engine sdist and wheel (packs bundled) in engine/dist"
	@echo "make docs      build the documentation site into site/"
	@echo "make report    regenerate research/REPORT.pdf and PAPER.pdf"

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

dist:
	rm -rf engine/dist engine/haanji/packs && mkdir -p engine/haanji/packs
	cp packs/*.yaml engine/haanji/packs/
	cd engine && pip install -q build && python -m build
	rm -rf engine/haanji/packs

docs-sync:
	mkdir -p docs/research && cp research/REPORT.md research/PAPER.md docs/research/
	rm -rf docs/research/figures && cp -R research/figures docs/research/figures

docs: docs-sync
	mkdocs build

report:
	cd engine && python ../research/harness/report_pdf.py && python ../research/harness/report_pdf.py --paper

clean:
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	rm -rf engine/.pytest_cache console/dist core-api/target engine/dist site docs/research engine/haanji/packs
