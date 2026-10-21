#!/bin/sh
# Assemble Microsoft's azureeyemodule runtime into a plain directory tree, so
# /app/inference can run from a chroot with its own libraries. No Docker, no
# daemon: a Docker image is only a tarball of layers plus an ordering.
#
# Applies each layer in the order given by the archive's own manifest.json, and
# honours OCI/AUFS whiteouts (.wh.NAME deletes NAME, .wh..wh..opq empties the
# directory) before extracting that layer's files, which is what a container
# runtime does.
#
# Run as root on the board. Usage: assemble-eye-runtime.sh ARCHIVE [TARGET]
set -eu

archive=${1:?docker-save archive required}
target=${2:-/opt/eyesom}
expect=1a6dbe58bad37d7a2af1af7211d9fa87e0088ee672934fbcfdd0d40343385a26

[ "$(id -u)" = 0 ] || { echo 'must run as root (ownership/permissions)' >&2; exit 1; }
printf '%s  %s\n' "$expect" "$archive" | sha256sum -c -
[ ! -e "$target" ] || { echo "already exists: $target" >&2; exit 1; }

work=$(mktemp -d /var/tmp/eye-assemble.XXXXXX)
trap 'rm -rf "$work"' EXIT
echo "extracting archive to $work"
tar -xzf "$archive" -C "$work"
[ -r "$work/manifest.json" ] || { echo 'archive has no manifest.json' >&2; exit 1; }

# Layer order straight from the archive, no hand-maintained list. The manifest
# is flat, so sed suffices and the board needs no Python; every entry is then
# shape-checked and must exist.
layers=$(sed -n 's/.*"Layers":[[:space:]]*\[\([^]]*\)\].*/\1/p' "$work/manifest.json" \
    | tr ',' '\n' | sed -n 's/.*"\(.*\)".*/\1/p' \
    | grep -E '^[0-9a-f]{64}/layer\.tar$')
count=$(printf '%s\n' "$layers" | grep -c . || true)
[ "$count" -gt 0 ] || { echo 'could not read the layer order from manifest.json' >&2; exit 1; }
[ "$(printf '%s\n' "$layers" | sort -u | grep -c .)" = "$count" ] ||
    { echo 'duplicate layer entries in manifest.json' >&2; exit 1; }
echo "layers: $count"

mkdir -p "$target"
index=0
whiteouts=0
for layer in $layers; do
    index=$((index + 1))
    path=$work/$layer
    [ -r "$path" ] || { echo "missing layer: $layer" >&2; exit 1; }

    # Apply this layer's whiteouts against the tree built so far, first.
    tar -tf "$path" | grep -E '(^|/)\.wh\.' > "$work/wh.list" || true
    while IFS= read -r entry; do
        [ -n "$entry" ] || continue
        name=${entry##*/}
        dir=${entry%"$name"}
        if [ "$name" = '.wh..wh..opq' ]; then
            if [ -d "$target/$dir" ]; then
                find "$target/$dir" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
            fi
        else
            rm -rf "$target/$dir${name#.wh.}"
        fi
        whiteouts=$((whiteouts + 1))
    done < "$work/wh.list"

    tar -xf "$path" -C "$target" --numeric-owner -p \
        --exclude='.wh.*' --exclude='*/.wh.*'
    printf '  [%2d/%2d] %s\n' "$index" "$count" "${layer%%/*}"
done
echo "whiteouts applied: $whiteouts"

# The pieces the capture test needs.
missing=0
for f in /app/inference /eyesom/mx.mvcmd /app/data/ssd_mobilenet_v2_coco.blob \
         /app/data/labels.txt /lib/ld-linux-aarch64.so.1; do
    if [ -e "$target$f" ]; then
        printf '  ok      %s\n' "$f"
    else
        printf '  MISSING %s\n' "$f"
        missing=$((missing + 1))
    fi
done
[ "$missing" = 0 ] || { echo "$missing expected path(s) absent" >&2; exit 1; }

du -sh "$target"
sha256sum "$target/app/inference" "$target/eyesom/mx.mvcmd" \
    "$target/app/data/ssd_mobilenet_v2_coco.blob"
echo "ASSEMBLED $target"
