#!/bin/bash
# SPDX-License-Identifier: MIT
source "$(dirname "$0")/common.sh"
root=${1:?root tree}; image=${2:?image}; uuid=${3:?UUID}; size=${4:?MiB}
in_ns mke2fs -q -t ext4 -F -b 4096 -U "$uuid" -L debian \
    -O '^orphan_file,^metadata_csum_seed' -d "$root" "$image" "$((size*1024))K"
e2fsck -fn "$image"
