# SPDX-License-Identifier: MIT
# Pure configuration logic of the Percept launcher, sourced by /init and by the
# host-side tests (tests/launcher). No hardware access except the explicitly
# named helpers at the end. Needs from the caller:
#   BB         path of busybox
#   cr         a carriage-return character
#   local_log  function taking one message
# Format reference: docs/launcher-conf.md

PERCEPT_DEFAULT_ESP=/dev/mmcblk0p1     # stock-kernel enumeration of the eMMC
PERCEPT_DEFAULT_ROOT=/dev/mmcblk0p3

valid_path() {
    case "$1" in
        /*) ;;
        *) return 1 ;;
    esac
    case "$1" in
        *..*|*//*|*[!A-Za-z0-9_./+-]*) return 1 ;;
    esac
}

valid_hash() {
    case "$1" in
        '') return 0 ;;
        *[!0-9a-f]*) return 1 ;;
    esac
    [ "${#1}" = 64 ]
}

valid_cmdline() {
    case "$1" in
        ''|*[!A-Za-z0-9_.,=:/+\ -]*) return 1 ;;
    esac
}

# /dev/NAME, UUID=..., LABEL=..., PARTUUID=...
valid_devspec() {
    case "$1" in
        /dev/*) valid_path "$1" ;;
        UUID=?*|PARTUUID=?*|LABEL=?*)
            case "${1#*=}" in
                *[!A-Za-z0-9_-]*) return 1 ;;
            esac
            [ "${#1}" -le 60 ]
            ;;
        *) return 1 ;;
    esac
}

valid_ipv4() {
    case "$1" in
        ''|*[!0-9.]*|.*|*.|*..*) return 1 ;;
    esac
    oldifs=$IFS
    IFS=.
    set -- $1
    IFS=$oldifs
    [ "$#" = 4 ] || return 1
    for octet in "$1" "$2" "$3" "$4"; do
        [ "${#octet}" -le 3 ] && [ "$octet" -le 255 ] || return 1
    done
}

valid_uint() {   # valid_uint VALUE MIN MAX
    case "$1" in
        ''|*[!0-9]*) return 1 ;;
    esac
    [ "${#1}" -le 5 ] && [ "$1" -ge "$2" ] && [ "$1" -le "$3" ]
}

valid_iface_spec() {
    case "$1" in
        auto) return 0 ;;
        *:*:*:*:*:*) case "$1" in *[!0-9a-fA-F:]*) return 1 ;; esac ;;
        *[!A-Za-z0-9_.-]*|'') return 1 ;;
    esac
}

valid_fstype_opts() {
    case "$1" in
        ''|*[!A-Za-z0-9_,=-]*) return 1 ;;
    esac
}

# Reset every setting to its default.
config_defaults() {
    conf_mode=kexec
    conf_profile=percept-dk
    conf_kernel=
    conf_initrd=
    conf_kernel_format=auto
    conf_cmdline=
    conf_kernel_sha256=
    conf_initrd_sha256=
    conf_root=
    conf_root_fstype=ext4
    conf_root_opts=ro,noload
    conf_net_mode=dhcp
    conf_net_if=auto
    conf_net_ip=
    conf_net_prefix=
    conf_net_gw=
    conf_log_receiver_ip=
    conf_log_receiver_port=
    conf_fail_limit=3
    conf_rescue_console=ttymxc0
    conf_fixups=
    conf_fixups_policy=skip-inapplicable
    conf_board_model=
    conf_cpu_profile=unchanged
    legacy_upper_ram=
    legacy_thermal_fix=
    legacy_media=
    have_fixups=0
}

# Turn the three legacy keys into a fixup list.
legacy_fixups() {
    list=
    [ "$legacy_upper_ram" = 1 ] && list=upper-ram
    [ "$legacy_thermal_fix" = 1 ] && list=${list:+$list,}thermal
    case "$legacy_media" in
        gpu) list=${list:+$list,}media-gpu ;;
        gpu-vpu) list=${list:+$list,}media-gpu-vpu ;;
    esac
    printf '%s' "$list"
}

valid_fixup_list() {
    [ -z "$1" ] && return 0
    oldifs=$IFS
    IFS=,
    set -- $1
    IFS=$oldifs
    for name in "$@"; do
        case "$name" in
            upper-ram|thermal|media-gpu|media-gpu-vpu) ;;
            *) return 1 ;;
        esac
    done
}

# read_config FILE : parse and validate; returns non-zero (after local_log) on any problem.
read_config() {
    config_defaults
    [ -r "$1" ] || { local_log "config_missing"; return 1; }
    while IFS= read -r line || [ -n "$line" ]; do
        # Tolerate files edited on Windows.
        line=${line%"$cr"}
        case "$line" in
            ''|'#'*) continue ;;
            *=*) ;;
            *) local_log "config_malformed_line"; return 1 ;;
        esac
        key=${line%%=*}
        value=${line#*=}
        case "$key" in
            mode) conf_mode=$value ;;
            profile) conf_profile=$value ;;
            kernel) conf_kernel=$value ;;
            initrd) conf_initrd=$value ;;
            kernel_format) conf_kernel_format=$value ;;
            cmdline) conf_cmdline=$value ;;
            kernel_sha256) conf_kernel_sha256=$value ;;
            initrd_sha256) conf_initrd_sha256=$value ;;
            root) conf_root=$value ;;
            root_fstype) conf_root_fstype=$value ;;
            root_opts) conf_root_opts=$value ;;
            net_mode) conf_net_mode=$value ;;
            net_if) conf_net_if=$value ;;
            net_ip) conf_net_ip=$value ;;
            net_prefix) conf_net_prefix=$value ;;
            net_gw) conf_net_gw=$value ;;
            log_receiver_ip) conf_log_receiver_ip=$value ;;
            log_receiver_port) conf_log_receiver_port=$value ;;
            fail_limit) conf_fail_limit=$value ;;
            rescue_console) conf_rescue_console=$value ;;
            dtb_fixups) conf_fixups=$value; have_fixups=1 ;;
            dtb_fixups_policy) conf_fixups_policy=$value ;;
            board_model) conf_board_model=$value ;;
            upper_ram) legacy_upper_ram=$value ;;
            thermal_fix) legacy_thermal_fix=$value ;;
            media) legacy_media=$value ;;
            cpu_profile) conf_cpu_profile=$value ;;
            *) local_log "config_unknown_key_$key"; return 1 ;;
        esac
    done <"$1"

    case "$conf_mode" in
        kexec|rescue) ;;
        *) local_log "config_invalid_mode"; return 1 ;;
    esac
    # Settings used in both modes (rescue still needs a network and a limit).
    case "$conf_net_mode" in dhcp|static|none) ;; *) local_log "config_invalid_net_mode"; return 1 ;; esac
    valid_iface_spec "$conf_net_if" || { local_log "config_invalid_net_if"; return 1; }
    valid_uint "$conf_fail_limit" 1 10 || { local_log "config_invalid_fail_limit"; return 1; }
    case "$conf_rescue_console" in
        ''|*[!A-Za-z0-9]*) local_log "config_invalid_rescue_console"; return 1 ;;
    esac
    if [ "$conf_net_mode" = static ]; then
        valid_ipv4 "$conf_net_ip" || { local_log "config_invalid_net_ip"; return 1; }
        valid_uint "$conf_net_prefix" 1 30 || { local_log "config_invalid_net_prefix"; return 1; }
        [ -z "$conf_net_gw" ] || valid_ipv4 "$conf_net_gw" || { local_log "config_invalid_net_gw"; return 1; }
    fi
    if [ -n "$conf_log_receiver_ip" ] || [ -n "$conf_log_receiver_port" ]; then
        valid_ipv4 "$conf_log_receiver_ip" || { local_log "config_invalid_log_receiver_ip"; return 1; }
        valid_uint "$conf_log_receiver_port" 1 65535 || { local_log "config_invalid_log_receiver_port"; return 1; }
    fi
    [ "$conf_profile" = percept-dk ] || { local_log "config_invalid_profile"; return 1; }
    [ -z "$conf_board_model" ] || case "$conf_board_model" in
        *[!A-Za-z0-9\ ._+-]*) local_log "config_invalid_board_model"; return 1 ;;
    esac
    [ "$conf_mode" = rescue ] && return 0

    # kexec-mode settings.
    case "$legacy_upper_ram" in ''|0|1) ;; *) local_log "config_invalid_upper_ram"; return 1 ;; esac
    case "$legacy_thermal_fix" in ''|0|1) ;; *) local_log "config_invalid_thermal_fix"; return 1 ;; esac
    case "$legacy_media" in ''|none|gpu|gpu-vpu) ;; *) local_log "config_invalid_media"; return 1 ;; esac
    if [ -n "$legacy_upper_ram$legacy_thermal_fix$legacy_media" ]; then
        if [ "$have_fixups" = 1 ]; then local_log "config_mixed_fixup_keys"; return 1; fi
        conf_fixups=$(legacy_fixups)
    fi
    valid_fixup_list "$conf_fixups" || { local_log "config_invalid_dtb_fixups"; return 1; }
    case "$conf_fixups_policy" in skip-inapplicable|strict) ;; *) local_log "config_invalid_dtb_fixups_policy"; return 1 ;; esac
    [ "$conf_cpu_profile" = unchanged ] || { local_log "config_unsupported_cpu_profile"; return 1; }
    valid_path "$conf_kernel" || { local_log "config_invalid_kernel"; return 1; }
    [ -z "$conf_initrd" ] || valid_path "$conf_initrd" || { local_log "config_invalid_initrd"; return 1; }
    case "$conf_kernel_format" in auto|Image|Image.gz) ;; *) local_log "config_invalid_kernel_format"; return 1 ;; esac
    valid_hash "$conf_kernel_sha256" || { local_log "config_invalid_kernel_sha256"; return 1; }
    valid_hash "$conf_initrd_sha256" || { local_log "config_invalid_initrd_sha256"; return 1; }
    [ -z "$conf_root" ] || valid_devspec "$conf_root" || { local_log "config_invalid_root"; return 1; }
    valid_fstype_opts "$conf_root_fstype" && valid_fstype_opts "$conf_root_opts" ||
        { local_log "config_invalid_root_fs"; return 1; }
    valid_cmdline "$conf_cmdline" || { local_log "config_invalid_cmdline"; return 1; }
    return 0
}

# The root device spec: conf `root`, else UUID=/LABEL=/PARTUUID= taken from the
# root= word of the new kernel's own command line, else the factory default.
root_spec() {
    if [ -n "$conf_root" ]; then
        printf '%s' "$conf_root"
        return
    fi
    for word in $conf_cmdline; do
        case "$word" in
            root=UUID=*|root=LABEL=*|root=PARTUUID=*)
                if valid_devspec "${word#root=}"; then
                    printf '%s' "${word#root=}"
                    return
                fi
                ;;
        esac
    done
    printf '%s' "$PERCEPT_DEFAULT_ROOT"
}

# The ESP spec comes from the *stock kernel's* command line (percept.esp=...),
# because the configuration file lives on the ESP and cannot name it.
esp_spec() {
    for word in $1; do
        case "$word" in
            percept.esp=*)
                if valid_devspec "${word#percept.esp=}"; then
                    printf '%s' "${word#percept.esp=}"
                    return
                fi
                ;;
        esac
    done
    printf '%s' "$PERCEPT_DEFAULT_ESP"
}

# resolve_device SPEC : print the /dev path for SPEC, return 1 if it does not exist (yet).
resolve_device() {
    case "$1" in
        /dev/*) [ -b "$1" ] && printf '%s' "$1" ;;
        *) $BB findfs "$1" 2>/dev/null ;;
    esac
}
