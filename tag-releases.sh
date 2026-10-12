#!/usr/bin/env bash
set -euo pipefail
[ -z "${BASH_VERSION:-}" ] && exec bash "$0" "$@"

cd "$HOME/git/fun-cli"

echo "==> Current history:"
git log --oneline
echo

# Find the commit hash whose subject starts with a given prefix
hash_for() {
    git log --format='%H %s' | awk -v p="$1" '$2==p {print $1; exit}'
}

H_010=$(hash_for "v0.1.0")
H_020=$(hash_for "v0.2.0")
H_100=$(hash_for "v1.0.0")

if [ -z "$H_010" ] || [ -z "$H_020" ] || [ -z "$H_100" ]; then
    echo "ERROR: couldn't locate all three version commits."
    echo "v0.1.0=$H_010  v0.2.0=$H_020  v1.0.0=$H_100"
    exit 1
fi

echo "==> Found commits:"
echo "    v0.1.0 -> $H_010"
echo "    v0.2.0 -> $H_020"
echo "    v1.0.0 -> $H_100"
echo

# Skip tags that already exist (idempotent re-runs)
make_tag() {
    local tag="$1" hash="$2" msg="$3"
    if git rev-parse -q --verify "refs/tags/$tag" >/dev/null; then
        echo "    tag $tag already exists, skipping"
    else
        git tag -a "$tag" "$hash" -m "$msg"
        echo "    created tag $tag"
    fi
}

echo "==> Creating tags:"
make_tag v0.1.0 "$H_010" "v0.1.0 — initial Tkinter MVP"
make_tag v0.2.0 "$H_020" "v0.2.0 — animated UI, dashboard, AI companion"
make_tag v1.0.0 "$H_100" "v1.0.0 — significant upgrade"

echo
echo "==> Local tags:"
git tag -l
echo

echo "==> Pushing tags to origin..."
git push origin --tags

echo
echo "==> Done. Tags pushed."
echo
echo "Next: create the releases on GitHub's web UI:"
echo "    https://github.com/AbduLz0/fun-cli/releases/new"
echo "  For each tag (v0.1.0, v0.2.0, v1.0.0):"
echo "    - Choose the tag"
echo "    - Give it a title like 'v0.1.0 — Initial Tkinter MVP'"
echo "    - Paste a short description"
echo "    - Optionally attach a zip of that version's folder"
echo "    - Click 'Publish release'"
