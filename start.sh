#!/bin/bash
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"

gnome-terminal -- bash -c "cd \"$PROJECT_ROOT\" && source .venv/bin/activate && exec bash"
