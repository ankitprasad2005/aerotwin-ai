# Deployment: choosing where the LLM runs

All agent reasoning goes through one OpenAI-compatible endpoint using JSON-schema structured outputs.
By default that is the external endpoint set by `AEROTWIN_OPENAI_BASE_URL`, `AEROTWIN_OPENAI_MODEL` and
`AEROTWIN_OPENAI_API_KEY`. Anything that speaks the protocol works, so the same backend can run against
OpenAI, an Azure endpoint, or a model on your own hardware. Nothing else in the stack (Postgres,
SearXNG, the datasets) calls a third-party LLM.

| Option | LLM runs on | Needs | Best for |
|---|---|---|---|
| Hosted (default) | OpenAI / Azure | API key | Quickest start, best output quality |
| Local | Same host, in the `llm` compose service | Set the switch in `.env`; 2-6 GB RAM | Edge boards, air-gapped sites |
| External on-prem | Another machine you own | `AEROTWIN_OPENAI_BASE_URL` pointing at it | Raspberry Pi 4 front end, GPU server back end |

## Quick start: on-device inference with llama.cpp

`.env.example` has the switch commented out. Uncomment both lines in `.env`:

```
AEROTWIN_LOCAL_LLM=true
COMPOSE_PROFILES=local-llm
```

then start the stack:

```sh
docker compose up -d --build
```

Two lines are needed because Compose starts the `llm` service only when its profile is listed in
`COMPOSE_PROFILES`, and the backend decides which endpoint to call from `AEROTWIN_LOCAL_LLM`. If only one
is set, runs fail with a connection error; the backend never falls back to the external API. The backend
logs the endpoint it uses at startup, either `LLM: local llama.cpp at … (model …)` or
`LLM: external endpoint …`, so check that line first.

The `llm` service is the official `ghcr.io/ggml-org/llama.cpp` server image (pinned to a build tag,
multi-arch amd64 and arm64). It publishes no host port; only the backend can reach it. On first start it
downloads the model from Hugging Face into the Docker volume `aerotwin_llm_models` (`LLAMA_CACHE=/cache`)
and then works offline. Its health check allows about 20 minutes for that download, and the backend
waits for it. On a slower connection `docker compose up` may give up on the backend first; the download
keeps going, so run `docker compose up -d` again once it finishes.

With `AEROTWIN_LOCAL_LLM=true` the backend:

* ignores `AEROTWIN_OPENAI_BASE_URL` and `AEROTWIN_OPENAI_MODEL`;
* calls `AEROTWIN_LOCAL_LLM_BASE_URL` (`http://llm:8080/v1` in compose) with model
  `AEROTWIN_LOCAL_LLM_MODEL` (compose passes `AEROTWIN_LLM_ALIAS`, default `local`);
* uses a placeholder API key if `AEROTWIN_OPENAI_API_KEY` is blank;
* defaults the LLM request timeout to 1800 s and runs one agent at a time, unless
  `AEROTWIN_OPENAI_TIMEOUT_SECONDS` or `AEROTWIN_AGENT_CONCURRENCY` is set explicitly. The 60 s cloud
  default is far too short for CPU inference of a full agent prompt, and one agent at a time keeps a small
  board from swapping (llama.cpp serves one request at a time here anyway).

Settings (all optional, put them in `.env`):

| Variable | Default | Meaning |
|---|---|---|
| `AEROTWIN_LOCAL_LLM` | off | `true` sends every agent to the local server. Pair with `COMPOSE_PROFILES=local-llm` |
| `AEROTWIN_LLM_HF_REPO` | `Qwen/Qwen2.5-1.5B-Instruct-GGUF` | Hugging Face repo the server downloads from on first start |
| `AEROTWIN_LLM_HF_FILE` | `qwen2.5-1.5b-instruct-q4_k_m.gguf` | GGUF file in that repo |
| `AEROTWIN_LLM_MODEL_FILE` | blank | Set to load this file from the model directory instead of downloading |
| `AEROTWIN_LLM_MODEL_DIR` | `./models` | Host directory mounted read-only at `/models` (used with `AEROTWIN_LLM_MODEL_FILE`) |
| `AEROTWIN_LLM_CTX` | `8192` | Context size in tokens. Agent prompts run about 2-4k tokens, so keep at least 8192 |
| `AEROTWIN_LLM_THREADS` | `4` | CPU threads. Set to the number of fast cores (4 on a ROCK 5C's Cortex-A76 cluster) |
| `AEROTWIN_LLM_ALIAS` | `local` | Model name the server reports; the backend sends it as the model |
| `AEROTWIN_LOCAL_LLM_BASE_URL` | `http://localhost:8080/v1` | Local endpoint. Compose sets `http://llm:8080/v1`; the default suits a bare-metal `llama-server` during development |
| `AEROTWIN_LOCAL_LLM_MODEL` | `local` | Model name sent to the local endpoint. Compose sets it from `AEROTWIN_LLM_ALIAS` |

To change model, set `AEROTWIN_LLM_HF_REPO` and `AEROTWIN_LLM_HF_FILE` and restart the `llm` service.

**Air-gapped.** Fetch the model on a connected machine with `scripts/fetch-local-model.sh` (downloads into
`./models`; pass `<repo> <file>` for another model), copy it to the host, and set
`AEROTWIN_LLM_MODEL_FILE=<file>` (and `AEROTWIN_LLM_MODEL_DIR` if it is not `./models`). The server then
loads that file and makes no download.

**Older `-f` override.** `docker compose -f docker-compose.yml -f docker-compose.local-llm.yml up -d`
still works. It is kept for compatibility and still maps `AEROTWIN_LLM_TIMEOUT_SECONDS` and
`AEROTWIN_LLM_AGENT_CONCURRENCY` to the timeout and concurrency settings.

To use an LLM server on a different machine instead, leave `AEROTWIN_LOCAL_LLM` off and set in `.env`:

```
AEROTWIN_OPENAI_BASE_URL=http://10.0.0.20:8080/v1
AEROTWIN_OPENAI_API_KEY=anything
AEROTWIN_OPENAI_MODEL=local
```

Set `AEROTWIN_OPENAI_TIMEOUT_SECONDS` and `AEROTWIN_AGENT_CONCURRENCY` yourself in that case; the local
defaults apply only with the switch on.

### Default model for the Radxa ROCK 5C

The default is Qwen2.5-1.5B-Instruct Q4_K_M (1.1 GB, Apache-2.0). It was chosen as the fastest model
that is still usable for a proof of concept:

* Speed. Published llama-bench figures for the RK3588 at 4 threads
  ([Turing Pi RK1 benchmark](https://turingpi.com/llm-inference-benchmarks-rk3588-gguf-quantization/)):
  about 55 tokens/s prompt processing and 22.6 tokens/s generation for Qwen2.5-1.5B Q4_K_M, against about
  25.5 / 11.3 tokens/s for Llama-3.2-3B Q4_K_M. These are published numbers for the RK3588, the same SoC
  family as the ROCK 5C's RK3588S, not measured on our board.
* Reliability. 12 of 13 structured outputs were valid on the x86 VM (see the measured section below).
* Memory. It fits a 4 GB ROCK 5C next to the rest of the stack.

Smaller models (0.5B) are faster but fail too many JSON-schema outputs to be useful.

For better reliability on an 8 GB or larger board, use Qwen3-4B-Instruct-2507 (2.5 GB, Apache-2.0,
non-thinking, IFEval 83.4). Expect it to be roughly 3x slower.

```
AEROTWIN_LLM_HF_REPO=unsloth/Qwen3-4B-Instruct-2507-GGUF
AEROTWIN_LLM_HF_FILE=Qwen3-4B-Instruct-2507-Q4_K_M.gguf
```

Avoid Qwen2.5-3B for commercial use: it is under the Qwen Research licence, not Apache-2.0.

## Hardware guidance

* **Edge board with local inference (for example Radxa ROCK 5C, RK3588S, 4-16 GB RAM).** Turn on the
  switch and run the whole stack with the default 1.5B Q4_K_M model (about 1.1 GB on disk, roughly
  1.5-2 GB resident with an 8k context). Use 4 threads (the Cortex-A76 cores). Expect CPU-class speed:
  budget minutes per orchestration, not seconds. On 8 GB or more, Qwen3-4B-Instruct-2507 is the more
  reliable choice at about a third of the speed.
* **Raspberry Pi 4 (4 GB) with external inference.** Too little RAM and too slow a CPU to host the
  model next to Postgres and the backend. Leave `AEROTWIN_LOCAL_LLM` off, run the stack on the Pi and point
  `AEROTWIN_OPENAI_BASE_URL` at an inference box on the same network (another board, a workstation,
  or a GPU server). Drop the SearXNG service if memory is tight (`AEROTWIN_SEARXNG_URL` blank disables web search).
* **VPS or GPU server with on-prem inference.** Same switch on a server; for a GPU use a CUDA build of
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
  model (Qwen3-4B-Instruct-2507, or 7B on a GPU server) where quality matters. Larger models were not measured.
* This CPU lacks AVX; an AVX2 x86 machine or an RK3588 board should be several times faster, so treat these as a
  worst case, and measure your own hardware. Set `AEROTWIN_OPENAI_TIMEOUT_SECONDS` generously (3600 was used).
