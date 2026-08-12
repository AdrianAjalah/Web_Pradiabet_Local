#!/usr/bin/env sh
set -eu

: "${HPC_SSH_USER:?Isi HPC_SSH_USER}"
: "${HPC_SSH_HOST:?Isi HPC_SSH_HOST}"
HPC_SSH_PORT="${HPC_SSH_PORT:-22}"
LOCAL_OLLAMA_PORT="${LOCAL_OLLAMA_PORT:-11435}"
REMOTE_OLLAMA_PORT="${REMOTE_OLLAMA_PORT:-11434}"

exec ssh \
  -p "$HPC_SSH_PORT" \
  -N \
  -L "${LOCAL_OLLAMA_PORT}:127.0.0.1:${REMOTE_OLLAMA_PORT}" \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  "${HPC_SSH_USER}@${HPC_SSH_HOST}"
