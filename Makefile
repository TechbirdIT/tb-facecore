.PHONY: install install-dev up verify down run test clean help

help:
	@echo "make install       - set up venv + install facecore/ai_service/edge_client"
	@echo "make install-dev   - install with dev/test tooling"
	@echo "make up            - bring up sidecar + ai_service and verify everything is healthy"
	@echo "make verify        - push a real face through /analyze (smoke test)"
	@echo "make down          - stop ai_service + the DeepFace sidecar"
	@echo "make run           - run ai_service in the foreground on :8080 (loads ./.env)"
	@echo "make test          - run the ai_service test suite"
	@echo "make clean         - remove the venv"

install:
	./install.sh

install-dev:
	./install.sh --dev

up:
	./scripts/up.sh

verify:
	./scripts/verify.sh

down:
	./scripts/down.sh

run:
	set -a; [ -f ./.env ] && . ./.env; set +a; \
	venv/bin/uvicorn ai_service.app:app --host 127.0.0.1 --port 8080

test:
	cd ai_service && ../venv/bin/pytest -v

clean:
	rm -rf venv
