#!/bin/bash
# SPDX-License-Identifier: MIT
# Only run inside build/common.sh's private arm64 builder namespace.
set -euo pipefail
export SOURCE_DATE_EPOCH=1700000000 TZ=UTC LC_ALL=C
export KBUILD_BUILD_USER=builder KBUILD_BUILD_HOST=percept
export KBUILD_BUILD_TIMESTAMP='Tue Nov 14 22:13:20 UTC 2023'
export KBUILD_BUILD_VERSION=1
work=/tmp/kexecmod-build
rm -rf "$work"
mkdir -p "$work"
cd "$work"
tar -xf /dl/linux-5.4.3.tar.xz
tar -xf /dl/kexec-mod-4ba956f.tar.gz
mod=$work/kexec-mod-4ba956fd60b29d2fea324515596b392afdcfa2c5
( cd "$mod" && patch -p1 < /src/kexecmod/patches/0001-kexec-mod-percept-port.patch )
python3 /src/kexecmod/inspect_stock_modules.py /vendor/modules "$work/metadata"
python3 /src/kexecmod/extract_kernel_exports.py /vendor/Image /vendor/System.map \
    "$work/metadata/imported-symbol-crcs.csv" "$work/metadata"
cp /vendor/config linux-5.4.3/.config
linux-5.4.3/scripts/config --file linux-5.4.3/.config \
    -d GCC_PLUGINS -d GCC_PLUGIN_RANDSTRUCT -d MODULE_SIG -d MODULE_SIG_ALL \
    -d SYSTEM_TRUSTED_KEYRING -d DEBUG_INFO -d LOCALVERSION_AUTO
make -C linux-5.4.3 ARCH=arm64 HOSTCFLAGS='-O2 -fcommon' olddefconfig
make -C linux-5.4.3 ARCH=arm64 HOSTCFLAGS='-O2 -fcommon' -j4 modules_prepare
cp "$work/metadata/Module.symvers.kernel" linux-5.4.3/Module.symvers
make -C linux-5.4.3 ARCH=arm64 M="$mod/kernel" PARAM_LOADER=1 \
    CONFIG_SYSTEM_TRUSTED_KEYRING=n HOSTCFLAGS='-O2 -fcommon' -j4 modules
rm -f /out/arch.ko /out/core.ko
python3 /src/kexecmod/prepare_hello_probe.py "$mod/kernel/arch/arm64/kexec_mod_arm64.ko" \
    "$work/metadata/stock-sample.ko" "$work/metadata/Module.symvers.kernel" /out/arch.ko --kexec-experiment
python3 /src/kexecmod/prepare_hello_probe.py "$mod/kernel/kexec_mod.ko" \
    "$work/metadata/stock-sample.ko" "$work/metadata/Module.symvers.kernel" /out/core.ko \
    --kexec-experiment --extra-symvers "$mod/kernel/Module.symvers"
cp linux-5.4.3/.config /out/build.config
cp "$work/metadata/kernel-exports.json" /out/kernel-exports.json
objdump -dr /out/arch.ko > /out/arch.disassembly
objdump -dr /out/core.ko > /out/core.disassembly
python3 /src/kexecmod/check-disassembly.py /out/arch.disassembly /out/core.disassembly linux-5.4.3/include/generated/asm-offsets.h > /out/disassembly-check.json
# Exercise the actual reset code with a fake register file; never real MMIO.
gcc -O2 -Wall -Wextra -Werror -I"$mod/kernel" /src/kexecmod/tests/test_reset.c -o "$work/test-reset"
"$work/test-reset" > /out/test-reset.log
python3 /src/build/write-manifest.py --output /out/modules.manifest.json --kind kexecmod \
    --source-commit "$SOURCE_COMMIT" --artifact /out/arch.ko --artifact /out/core.ko \
    --input /vendor/Image --input /vendor/System.map --input /vendor/config \
    --input /dl/linux-5.4.3.tar.xz --input /dl/kexec-mod-4ba956f.tar.gz \
    --input /src/kexecmod/patches/0001-kexec-mod-percept-port.patch
