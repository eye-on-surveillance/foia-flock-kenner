# Flock FOIA Data Pipeline
#
# Usage:
#   make db         Download raw data, aggregate, and build SQLite database
#   make viz        Regenerate all visualizations from the database
#   make test       Run tests (no database required)
#   make all        Full pipeline: db + viz
#   make download   Download raw FOIA data only
#   make clean      Remove generated artifacts
#
# Prerequisites: Python 3.10+, uv (https://docs.astral.sh/uv/)

.DELETE_ON_ERROR:
.PHONY: all db viz test download clean help

PYTHON := python3
UV := uv

CACHE := cache
DB := $(CACHE)/flock.db
DOWNLOAD_STAMP := $(CACHE)/.downloaded

# Intermediate CSVs built by stage 1
EVENTS_CSV := $(CACHE)/events.csv
ORG_CSV := $(CACHE)/org_audit.csv
NET_CSV := $(CACHE)/network_audit.csv

# Visualization scripts (exclude test files)
VIZ_SCRIPTS := $(filter-out %/test_%.py,$(wildcard results/*/[a-z]*.py))

# Default target
all: db viz

help:
	@echo "make db         Download raw data, aggregate, and build SQLite database"
	@echo "make viz        Regenerate all visualizations from the database"
	@echo "make test       Run tests (no database required)"
	@echo "make all        Full pipeline: db + viz"
	@echo "make download   Download raw FOIA data only"
	@echo "make clean      Remove generated artifacts"

# --- Stage 0: Download raw FOIA data ---

$(DOWNLOAD_STAMP):
	$(PYTHON) setup-scripts/00_download_foia_result.py
	@touch $@

download: $(DOWNLOAD_STAMP)

# --- Stage 1: Aggregate monthly CSVs ---

$(EVENTS_CSV): $(DOWNLOAD_STAMP)
	$(PYTHON) setup-scripts/01_aggregate_events.py

$(ORG_CSV): $(DOWNLOAD_STAMP)
	$(PYTHON) setup-scripts/01_aggregate_org_audit.py

$(NET_CSV): $(DOWNLOAD_STAMP)
	$(PYTHON) setup-scripts/01_aggregate_network_audit.py

# --- Stage 2: Build SQLite database ---

$(DB): $(EVENTS_CSV) $(ORG_CSV) $(NET_CSV)
	$(PYTHON) setup-scripts/02_load_sqlite.py

db: $(DB)

# --- Visualizations ---

viz: $(DB)
	@set -e; for script in $(VIZ_SCRIPTS); do \
		echo "Running $$script ..."; \
		$(UV) run $$script; \
		echo; \
	done

# --- Tests ---

TEST_FILES := $(wildcard results/*/test_*.py)

test:
ifdef TEST_FILES
	$(PYTHON) -m pytest $(TEST_FILES) -v
else
	@echo "No test files found."
endif

# --- Cleanup ---

clean:
	rm -f $(EVENTS_CSV) $(ORG_CSV) $(NET_CSV) $(DB) $(DOWNLOAD_STAMP)
	@echo "Cleaned generated artifacts. Raw data in raw-response/ preserved."
