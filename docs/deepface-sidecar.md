# DeepFace Analytics Sidecar

## What it is and why it exists

This system runs two engines: **InsightFace** (`ai_service`, port 8080) handles real-time edge embeddings (`POST /embed`) with sub-second latency; **DeepFace** (this sidecar) handles server-side analytics (`POST /analyze` — demographics, and later Weaviate-backed face register/search). Different SLAs, different processes.

## Prerequisite: private submodule

The sidecar is `ekansh-tb/deepface`, a private fork. You need team access to `github.com/ekansh-tb/deepface` before the submodule can be fetched.

## 1. Init the submodule

Fresh clones — always recurse:

```bash
git clone --recurse-submodules https://github.com/TechbirdIT/tb-facecore
```

If you already have the repo cloned without submodules:

```bash
git submodule update --init vendor/deepface
```

## 2. Configure

```bash
cp vendor/deepface/docker/.env.example vendor/deepface/docker/.env
```

Edit `vendor/deepface/docker/.env` to set credentials, secrets, and any port overrides needed for your environment.

## 3. Bring it up (one command)

From the repo root:

```bash
make up        # starts the sidecar + ai_service, warms models, verifies health
make verify    # pushes a real face through /analyze and confirms demographics
make down      # stops ai_service + the sidecar (model weights persist)
```

`make up` is the recommended path — it waits until each service actually
responds (not just "container started"), warms the DeepFace models once (a fresh
container lazy-loads TF models on the first `/analyze`, which can take a few
minutes — `make up` pays that cost upfront so real calls are sub-second), and
prints a clear ✅/❌ with the next action on failure. It also remaps Weaviate's
host port 8080 → 8081 so it doesn't collide with `ai_service` on 8080, and model
weights live in the `deepface_weights` volume so they survive `make down`.

Raw Compose still works if you only want the sidecar (the top-level
`docker-compose.yml` uses Compose v2 `include`):

```bash
docker compose up -d        # sidecar only; ai_service started separately
docker compose ps
docker compose down
```

## 4. Host ports

| Service | Host port | Container port |
|---------|-----------|----------------|
| DeepFace API | 5005 | 5000 |
| Next.js UI | 3000 | 3000 |
| Weaviate HTTP | 8080 | 8080 |
| Weaviate gRPC | 50051 | 50051 |
| MinIO API | 9000 | 9000 |
| MinIO console | 9001 | 9001 |
| Postgres | 5432 | 5432 |

## 5. How `ai_service` reaches it

Set `AI_SERVICE_DEEPFACE_URL` in the environment before starting `ai_service` (default: `http://localhost:5005/api/v1`; see `.env.example` at repo root).

`POST /analyze` on `ai_service` proxies to the sidecar's `POST /api/v1/analyze` and returns `{"results": [...]}` with demographics (age, gender, emotion, race).

## 6. Security note

Inbound `/analyze` on `ai_service` enforces the same `X-Secret` header gate as `/embed` (active when `AI_SERVICE_SECRET` is set), and validates the upload as a decodable image before forwarding.

The `ai_service` → DeepFace API hop is unauthenticated: this increment treats the sidecar as internal/trusted on the Compose network. **Production must restrict access**: the fork contains its own auth blueprint; wiring it to `ai_service` is a later task.
