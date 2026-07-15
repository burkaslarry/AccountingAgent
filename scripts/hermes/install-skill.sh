#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
SKILL_SRC="$SCRIPT_DIR/skills/receipt-extractor"
SKILL_DST="$HERMES_HOME/skills/receipt-extractor"

mkdir -p "$SKILL_DST"
cp "$SKILL_SRC/SKILL.md" "$SKILL_DST/SKILL.md"

echo "Installed receipt-extractor skill to $SKILL_DST"
echo "Run: hermes chat -s receipt-extractor -q 'Extract receipt fields from this OCR text...'"
