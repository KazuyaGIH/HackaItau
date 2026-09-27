# Um terminal só. `make` mostra os alvos.
#   make install   dependências (backend venv + frontend)
#   make run       demo: build do frontend + FastAPI servindo tudo em http://localhost:8000
#   make dev       hot reload: vite (5173, proxy /api) + uvicorn --reload (8000); Ctrl+C encerra os dois
#   make test      pytest + ruff + build/lint do frontend
#   make benchmark comparativo real (API paga): 8 casos × 2 arquiteturas × 2 modelos
#   make benchmark-plan mostra os casos e modelos sem chamar a API
#   make benchmark-audit confere offline os 48 registros publicados e seus custos

SHELL := /bin/bash
.ONESHELL:

PYTHON ?= python3
VENV   := backend/.venv
PY     := $(CURDIR)/$(VENV)/bin/python
PORT   ?= 8000

.PHONY: help install install-backend install-frontend env run dev backend frontend build test clean benchmark benchmark-plan benchmark-audit

help:
	@grep -E '^#   make' Makefile | sed 's/^#   //'

install: install-backend install-frontend env

install-backend:
	test -d $(VENV) || $(PYTHON) -m venv $(VENV)
	$(PY) -m pip install -q --upgrade pip
	$(PY) -m pip install -q -e "backend[dev]"

install-frontend:
	cd $(CURDIR)/frontend && npm install

env:
	test -f .env || { cp .env.example .env; echo ">> .env criado a partir de .env.example — preencha LLM_API_KEY"; }

build:
	cd $(CURDIR)/frontend && npm run build

run: build
	cd $(CURDIR)/backend && $(PY) -m uvicorn app.main:app --port $(PORT)

backend:
	cd $(CURDIR)/backend && $(PY) -m uvicorn app.main:app --reload --port $(PORT)

frontend:
	cd $(CURDIR)/frontend && API_PORT=$(PORT) npm run dev

dev:
	trap 'kill 0' INT TERM EXIT
	$(MAKE) --no-print-directory backend &
	$(MAKE) --no-print-directory frontend &
	wait

test:
	cd $(CURDIR)/backend && $(PY) -m pytest -q && $(PY) -m ruff check app tests && $(PY) -m ruff format --check app tests
	cd $(CURDIR)/frontend && npm run build && npm run lint

benchmark:
	$(PY) -m app.evaluation.runner $(ARGS)

benchmark-audit:
	$(PY) -m app.evaluation.audit

benchmark-plan:
	$(PY) -m app.evaluation.runner --dry-run $(ARGS)

clean:
	rm -rf frontend/dist backend/.pytest_cache backend/.ruff_cache
	find backend -name __pycache__ -type d -prune -exec rm -rf {} +
