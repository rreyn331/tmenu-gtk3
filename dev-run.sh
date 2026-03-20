#!/bin/bash

# Run TMenu directly from source tree

set -e

cd "$(dirname "$0")"

echo "Running TMenu from development tree..."

PYTHONPATH=. python3 -m tmenu.main


