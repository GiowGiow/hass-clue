#!/usr/bin/env bash
# Vendor a tagged release of the pyclue library into the integration.
#
# Home Assistant cannot pip-install pyclue while its repository is private,
# so the integration ships a pinned copy. Run this to move to a new release:
#
#     scripts/sync_pyclue.sh v0.2.0
#
# Once pyclue is published on PyPI, delete the vendored directory, add it to
# "requirements" in manifest.json and import it as a top-level package.
set -euo pipefail

tag="${1:?usage: $0 <tag>, for example v0.1.0}"
repo="GiowGiow/pyclue"
root="$(cd "$(dirname "$0")/.." && pwd)"
dest="$root/custom_components/clue/pyclue"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

gh repo clone "$repo" "$tmp/pyclue" -- --quiet --depth 1 --branch "$tag"
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
