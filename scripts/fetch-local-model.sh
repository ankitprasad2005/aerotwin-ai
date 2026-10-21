#!/bin/sh
# Download a GGUF model into ./models (or $LLM_MODEL_DIR) for air-gapped sites.
#
# Not needed normally: with AEROTWIN_LOCAL_LLM=true and COMPOSE_PROFILES=local-llm in .env, the llm service
# downloads its model by itself on first start. Use this script on a machine with internet access, copy the file
# to the target's models directory, and point AEROTWIN_LLM_MODEL_FILE at it so nothing is downloaded there.
#
#   scripts/fetch-local-model.sh                        # Qwen2.5-1.5B-Instruct Q4_K_M (~1.1 GB)
#   scripts/fetch-local-model.sh Qwen/Qwen2.5-3B-Instruct-GGUF qwen2.5-3b-instruct-q4_k_m.gguf
#
# Arguments: <huggingface repo> <file in that repo>. Resumable; safe to re-run.
set -eu

REPO="${1:-Qwen/Qwen2.5-1.5B-Instruct-GGUF}"
FILE="${2:-qwen2.5-1.5b-instruct-q4_k_m.gguf}"
DEST_DIR="${LLM_MODEL_DIR:-$(dirname "$0")/../models}"
URL="https://huggingface.co/${REPO}/resolve/main/${FILE}"

mkdir -p "$DEST_DIR"
DEST="$DEST_DIR/$FILE"
echo "Downloading $URL"
echo "        to  $DEST"
# -C - resumes a partial download; -f fails on HTTP errors instead of saving an error page.
curl -fL -C - --retry 3 -o "$DEST" "$URL"
echo "Done: $DEST ($(wc -c < "$DEST") bytes)"
echo "Add to .env (set AEROTWIN_LLM_MODEL_DIR too if the file is not in ./models):"
echo "  AEROTWIN_LOCAL_LLM=true"
echo "  COMPOSE_PROFILES=local-llm"
echo "  AEROTWIN_LLM_MODEL_FILE=$FILE"
echo "then: docker compose up -d"
