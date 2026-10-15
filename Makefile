.PHONY: install demo demo-http test up down fmt

install:        ## install for local offline demo
	pip install -e '.[dev]'

demo:           ## run the full pause/resume flow in-process (no servers needed)
	python client/demo.py

test:           ## smoke test the graph (no network, no keys)
	pytest -q

up:             ## start both services in containers
	docker compose up --build

down:
	docker compose down -v

demo-http:      ## drive the running services over HTTP (run `make up` first)
	python client/demo.py --http
