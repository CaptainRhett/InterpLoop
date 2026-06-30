#!/usr/bin/env bash
set -euo pipefail

conda run -n tz python -m pip install -r backend/requirements.txt
conda run -n tz python backend/wsgi.py
