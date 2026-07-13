#!/usr/bin/env sh
set -eu

if [ ! -f "/app/config.yaml" ]; then
  echo "[ERROR] /app/config.yaml not found. Mount or copy config.yaml before start."
  exit 1
fi

exec python main.py

