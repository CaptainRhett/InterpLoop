#!/usr/bin/env bash
set -euo pipefail

cd frontend
conda run -n tz npm install
conda run -n tz npm run build
