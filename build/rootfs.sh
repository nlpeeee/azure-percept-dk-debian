#!/bin/bash
# SPDX-License-Identifier: MIT
source "$(dirname "$0")/common.sh"
require_linux_build_host
root=${1:?root path}; settings=${2:?private settings}; profile=${3:?profile path}
[ ! -e "$root" ] || die 'rootfs output already exists'
read -r suite mirror components packages < <(python3 - "$settings" "$profile" "$PERCEPT_ROOT" <<'PY'
import json,sys
sys.path.insert(0,sys.argv[3]+'/src')
from percept import tomlmini
p=tomlmini.load_file(sys.argv[2]+'/profile.toml');c=json.load(open(sys.argv[1]))['config']
f=p['rootfs'];extra=['python3','tzdata','gdisk','firmware-realtek','wireless-regdb','iw','bluez']
extra+=['libegl-mesa0','libgl1-mesa-dri','mesa-utils','mesa-utils-extra','v4l-utils','ffmpeg'] if c['os']['features'].get('gpu',True) is not False else []
extra+=c['os']['packages']['extra']
print(f['suite'],c['os'].get('mirror') or f['mirror'],','.join(f.get('components',['main'])),','.join(dict.fromkeys(f.get('include',[])+extra)))
PY
)
in_ns debootstrap --arch=arm64 --foreign --variant=minbase --components="$components" --include="$packages" "$suite" "$root" "$mirror"
BINDS="$PERCEPT_ROOT:/src:ro $(dirname "$settings"):/private:ro" \
    chroot_run "$root" BUILD_SETTINGS="/private/$(basename "$settings")" -- bash /src/build/target-setup.sh
PERCEPT_BIND_RESOLV=0 BINDS="$PERCEPT_ROOT:/src:ro $(dirname "$settings"):/private:ro" \
    chroot_run "$root" -- env PYTHONPATH=/src/src python3 -m percept.build.configure_root "/private/$(basename "$settings")" / /src
