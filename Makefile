.PHONY: install install-dev run test sidecar-up sidecar-down clean help

help:
	@echo "make install       - set up venv + install facecore/ai_service/edge_client"
	@echo "make install-dev   - install with dev/test tooling"
	@echo "make run           - run the AI service on :8080 (loads ./.env)"
	@echo "make test          - run the ai_service test suite"
	@echo "make sidecar-up    - bring up the DeepFace analytics sidecar (Docker)"
	@echo "make sidecar-down  - stop the DeepFace sidecar"
	@echo "make clean         - remove the venv"

install:
	./install.sh

install-dev:
	./install.sh --dev

run:
	set -a; [ -f ./.env ] && . ./.env; set +a; \
	venv/bin/uvicorn ai_service.app:app --host 127.0.0.1 --port 8080

test:
	cd ai_service && ../venv/bin/pytest -v

sidecar-up:
	git submodule update --init vendor/deepface
	@[ -f vendor/deepface/docker/.env ] || cp vendor/deepface/docker/.env.example vendor/deepface/docker/.env
	docker compose up -d

sidecar-down:
	docker compose down

clean:
	rm -rf venv
