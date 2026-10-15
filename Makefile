.PHONY: install test demo-offline up up-offline down

install:        ## install the project + pytest
	pip install -e '.[dev]'

test:           ## offline tests (scripted model, mock search, SQLite)
	pytest -q

up:             ## real run: needs LiteLLM + Tavily values in .env
	docker compose up --build

up-offline:     ## backup demo in containers: fake LLM/search, real A2A + Postgres
	MODEL_BACKEND=scripted SEARCH_BACKEND=mock MCP_ENABLED=false docker compose up --build

demo-http:      ## drive the running services over HTTP (run `make up-offline` first)
	python client/demo.py --http

demo-offline:   ## no containers at all: in-process, SQLite, scripted model
	MODEL_BACKEND=scripted SEARCH_BACKEND=mock MCP_ENABLED=false CHECKPOINT_BACKEND=sqlite \
	RESEARCH_MODE=inproc python client/demo.py

down:
	docker compose down -v
