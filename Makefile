PYTHON ?= python3

.PHONY: install test run bench record demo

install:
	$(PYTHON) -m pip install -e ".[dev]"

test:
	$(PYTHON) -m pytest

run:
	HL_DATASET_URI=$${HL_DATASET_URI:-demo/data} $(PYTHON) -m toolrouter serve

bench:
	HL_DATASET_URI=$${HL_DATASET_URI:-demo/data} $(PYTHON) -m toolrouter bench

record:
	HL_DATASET_URI=$${HL_DATASET_URI:-demo/data} $(PYTHON) -m toolrouter record

demo: record
