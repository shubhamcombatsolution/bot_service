#!/bin/bash
set -e

echo ">>> Starting gunicorn..."
exec gunicorn \
  --bind 0.0.0.0:5000 \
  --workers 4 \
  --threads 2 \
  --timeout 120 \
  run:app
