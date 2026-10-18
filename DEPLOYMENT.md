# Deployment: choosing where the LLM runs

All agent reasoning goes through one OpenAI-compatible endpoint
(`AEROTWIN_OPENAI_BASE_URL`, `AEROTWIN_OPENAI_MODEL`, `AEROTWIN_OPENAI_API_KEY`) using JSON-schema
structured outputs. Anything that speaks that protocol works, so the same backend can run against
OpenAI, an Azure endpoint, or a model on your own hardware. Nothing else in the stack (Postgres,
SearXNG, the datasets) calls a third-party LLM.

| Option | LLM runs on | Needs | Best for |
|---|---|---|---|
| Hosted (default) | OpenAI / Azure | API key | Quickest start, best output quality |
| Local (this document) | Same host, in a `llm` compose service | A GGUF model file, 2-6 GB RAM | Edge boards, air-gapped sites |
| External on-prem | Another machine you own | `AEROTWIN_OPENAI_BASE_URL` pointing at it | Raspberry Pi 4 front end, GPU server back end |

## Quick start: local inference with llama.cpp

```sh
scripts/fetch-local-model.sh                       # Qwen2.5-1.5B-Instruct Q4_K_M, ~1.1 GB, into ./models
docker compose -f docker-compose.yml -f docker-compose.local-llm.yml up -d --build
```

The override adds an `llm` service (official `ghcr.io/ggml-org/llama.cpp` server image, pinned to a
build tag, multi-arch amd64 and arm64) and points the backend at `http://llm:8080/v1` with a dummy
API key. The `llm` service publishes no host port; only the backend can reach it. The backend waits
for its `/health` check.

Settings (all optional, put them in `.env`):

| Variable | Default | Meaning |
|---|---|---|
| `AEROTWIN_LLM_MODEL_FILE` | `qwen2.5-1.5b-instruct-q4_k_m.gguf` | File inside the model directory |
| `AEROTWIN_LLM_MODEL_DIR` | `./models` | Host directory mounted read-only at `/models` |
| `AEROTWIN_LLM_CTX` | `8192` | Context size in tokens. Agent prompts run about 2-4k tokens, so keep at least 8192 |
| `AEROTWIN_LLM_THREADS` | `4` | CPU threads. Set to the number of fast cores (4 on a ROCK 5C's A76 cluster) |
| `AEROTWIN_LLM_ALIAS` | `local` | Model name the API reports; also sent as `AEROTWIN_OPENAI_MODEL` |

A larger model: `scripts/fetch-local-model.sh Qwen/Qwen2.5-3B-Instruct-GGUF qwen2.5-3b-instruct-q4_k_m.gguf`
and set `AEROTWIN_LLM_MODEL_FILE` to match.

To use an LLM server on a different machine instead, skip the override and set in `.env`:

```
AEROTWIN_OPENAI_BASE_URL=http://10.0.0.20:8080/v1
AEROTWIN_OPENAI_API_KEY=anything
AEROTWIN_OPENAI_MODEL=local
```

The override already raises the LLM request timeout to 1800 s and runs one agent at a time (the 60 s cloud
default is far too short for CPU inference of a full agent prompt). Tune them in `.env` with
`AEROTWIN_LLM_TIMEOUT_SECONDS` and `AEROTWIN_LLM_AGENT_CONCURRENCY`.

## Hardware guidance

* **Edge board with local inference (for example Radxa ROCK 5C, RK3588S, 8-16 GB RAM).** Run the whole
  stack plus the 1.5B Q4_K_M model (about 1.1 GB on disk, roughly 1.5-2 GB resident with an 8k context).
  Use 4 threads (the Cortex-A76 cores). Expect CPU-class speed: see the measured numbers below and scale
  down for the board. A ROCK 5C is slower per core than a desktop x86 server, so budget minutes per
  orchestration, not seconds. The 3B model fits in 16 GB boards but is about twice as slow.
* **Raspberry Pi 4 (4 GB) with external inference.** Too little RAM and too slow a CPU to host the
  model next to Postgres and the backend. Run the stack on the Pi and point
  `AEROTWIN_OPENAI_BASE_URL` at an inference box on the same network (another board, a workstation,
  or a GPU server). Drop the SearXNG service if memory is tight (`AEROTWIN_SEARXNG_URL` blank disables web search).
* **VPS or GPU server with on-prem inference.** Same override on a server; for a GPU use a CUDA build of
  the llama.cpp server image (`ghcr.io/ggml-org/llama.cpp:server-cuda-<tag>`), add the NVIDIA device
  reservation to the `llm` service, and add `--n-gpu-layers 99` to its command. This is the route to a
  7B-14B model whose output quality is closer to a hosted one while data stays inside your boundary.

## Security and compliance rationale

* **Data residency.** Fleet, crew, maintenance and route-economics data, and the prompts built from
  them, never leave your infrastructure. There is no outbound call to an LLM vendor, which simplifies
  data-localisation and vendor-risk reviews.
* **Air-gapped operation.** After the image pull and one model download, the system runs with no
  internet access (leave `AEROTWIN_SEARXNG_URL` blank; public dataset fetches are optional).
* **Smaller attack surface.** No API key to leak or rotate, no per-token billing to abuse, and the `llm`
  service is reachable only on the private compose network.
* **Auditability and cost.** Model file and image tag are pinned and the exact weights are known, so
  results can be reproduced; inference cost is fixed hardware cost.
* **Trade-off.** Small local models are weaker at following long structured-output instructions than a
  hosted frontier model. Every agent output is validated against its JSON schema; an invalid output fails
  that agent and the run (it is never silently accepted), so check the measured reliability below before relying on it.

## Measured on a CPU-only host

One full 10-agent orchestration ("Should we add a weekly flight on MAA-CCU?") against
Qwen2.5-1.5B-Instruct Q4_K_M (llama.cpp `server-b11681`, 8192 context, 8 threads, one slot, agents run one at a time)
on an 8-vCPU x86 VM (QEMU virtual CPU, SSE4.2 only, no AVX/AVX2, 7 GB RAM):

* Prompt processing about 20 tokens/s, generation about 6.4 tokens/s (4.4-8.7 depending on prompt length).
* Agent prompts were 2.0k-7.1k tokens; each agent took 2-7 minutes; the whole run took 36.7 minutes and ended
  with a valid decision (REJECT, score 51.18). All 10 structured outputs validated.
* Reliability is not perfect: in one earlier attempt the model looped until it filled the context window and the
  first agent's output was invalid, which fails the run. Of 13 agent calls in total, 12 were valid. Retry the run, or use a larger
  model (Qwen2.5-3B/7B) where quality matters. The 3B model was not measured.
* This CPU lacks AVX; an AVX2 x86 machine or an RK3588 board should be several times faster, so treat these as a
  worst case, and measure your own hardware. Set `AEROTWIN_OPENAI_TIMEOUT_SECONDS` generously (3600 was used).
