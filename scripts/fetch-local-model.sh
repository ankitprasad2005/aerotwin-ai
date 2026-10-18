#!/bin/sh
# Download a GGUF model for the local-LLM compose override into ./models (or $LLM_MODEL_DIR).
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
echo "Set AEROTWIN_LLM_MODEL_FILE=$FILE in .env, then:"
echo "  docker compose -f docker-compose.yml -f docker-compose.local-llm.yml up -d"
