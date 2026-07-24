#!/usr/bin/env bash
# Render the ER diagram in docs/reference/db-schema.md (its first
# ```mermaid block) to a high-resolution dark-themed PNG for review.
#
#   scripts/render-er-diagram.sh [-o output/db-schema-er-v<N>.png] [-s scale] [file.md]
#
# Needs mermaid-cli (mmdc) — Arch: pacman -S mermaid-cli, elsewhere:
# npx -y @mermaid-js/mermaid-cli. Uses the system chromium when
# puppeteer has no downloaded browser of its own. Nothing here touches
# the Python package; output/ is untracked.
set -euo pipefail

repo=$(cd "$(dirname "$0")/.." && pwd)
# name the render after the schema version it depicts
ver=$(sed -n 's/^SCHEMA_VERSION = "\(.*\)"/\1/p' \
      "$repo/src/x4analyzer/db/schema.py")
out="$repo/output/db-schema-er-v${ver:-unknown}.png"
scale=8                       # 8 x ~800px layout ≈ 6300px long edge
while getopts "o:s:" opt; do
    case $opt in
        o) out=$OPTARG ;;
        s) scale=$OPTARG ;;
        *) exit 2 ;;
    esac
done
shift $((OPTIND - 1))
src=${1:-$repo/docs/reference/db-schema.md}

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

# first ```mermaid fence in the doc, verbatim
awk '/^```mermaid$/{f=1;next} /^```$/{if(f)exit} f' "$src" > "$tmp/er.mmd"
[ -s "$tmp/er.mmd" ] || { echo "no mermaid block found in $src" >&2; exit 1; }

# mmdc's puppeteer downloads its own chrome unless told otherwise; prefer
# the system chromium so the script works offline with zero setup
pptr=()
if command -v chromium >/dev/null; then
    printf '{"executablePath": "%s"}\n' "$(command -v chromium)" > "$tmp/pptr.json"
    pptr=(-p "$tmp/pptr.json")
fi

# dashboard dark theme: DARK_BG from viz/common.py
mkdir -p "$(dirname "$out")"
mmdc -i "$tmp/er.mmd" -o "$out" -t dark -b '#1e1e1e' \
     --scale "$scale" "${pptr[@]}" --quiet
identify "$out" 2>/dev/null || ls -la "$out"
