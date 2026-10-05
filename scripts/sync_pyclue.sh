#!/usr/bin/env bash
# Vendor a tagged release of the pyclue library into the integration.
#
# pyclue is not on PyPI (the name there belongs to an unrelated project), so
# the integration ships a pinned copy that HACS installs along with it. Run
# this to move to a new release:
#
#     scripts/sync_pyclue.sh v0.2.0
set -euo pipefail

tag="${1:?usage: $0 <tag>, for example v0.1.0}"
repo="GiowGiow/pyclue"
root="$(cd "$(dirname "$0")/.." && pwd)"
dest="$root/custom_components/clue/pyclue"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

git -c advice.detachedHead=false clone --quiet --depth 1 --branch "$tag" "https://github.com/$repo.git" "$tmp/pyclue"
sha="$(git -C "$tmp/pyclue" rev-parse HEAD)"

mkdir -p "$dest"
rsync -a --delete --exclude '__pycache__' --exclude 'VENDORED' \
    "$tmp/pyclue/pyclue/" "$dest/"

cat > "$dest/VENDORED" <<VENDORED
repository: https://github.com/$repo
tag: $tag
commit: $sha
VENDORED

echo "Vendored $repo $tag ($sha) into ${dest#"$root"/}"
