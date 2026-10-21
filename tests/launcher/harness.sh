#!/bin/busybox sh
# SPDX-License-Identifier: MIT
# Host-side driver for launcher/lib/percept-config.sh (run by tests/unit/test_launcher_shell.py).
#   harness.sh LIB read CONF            parse CONF, print rc and every conf_* value
#   harness.sh LIB call FUNCTION ARG..  call a library function, print rc and its output
BB=busybox
cr=$(printf '\r')
local_log() { printf 'LOG %s\n' "$*"; }
lib=$1; mode=$2; shift 2
. "$lib"
case "$mode" in
    read)
        read_config "$1"
        printf 'rc=%s\n' "$?"
        for v in mode profile kernel initrd kernel_format cmdline root root_fstype root_opts net_mode net_if net_ip \
                 net_prefix net_gw log_receiver_ip log_receiver_port fail_limit rescue_console fixups fixups_policy board_model cpu_profile cpu_pmic; do
            eval "printf 'conf_%s=%s\n' $v \"\$conf_$v\""
        done
        printf 'root_spec=%s\n' "$(root_spec)"
        ;;
    call)
        fn=$1; shift
        out=$($fn "$@")
        printf 'rc=%s\nout=%s\n' "$?" "$out"
        ;;
esac
