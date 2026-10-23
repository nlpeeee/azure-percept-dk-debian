# SPDX-License-Identifier: MIT
"""The per-board configuration schema: one list that drives validation of
unknown keys, defaults, redaction and the generated docs/configuration.md."""
from collections import namedtuple

Field = namedtuple("Field", "path type default secret doc")

SCHEMA_VERSION = 1

# type strings: str int bool list[str] ; "table" marks a section header.
FIELDS = [
    Field("schema", "int", SCHEMA_VERSION, False, "Config schema version. Must be 1."),

    Field("board.name", "str", None, False, "Label for build directories and logs: lowercase letters, digits, `-`, `_` (1-32)."),
    Field("board.hostname", "str", "= board.name", False, "RFC 1123 hostname (letters, digits, `-`; max 63)."),
    Field("board.timezone", "str", "UTC", False, "IANA zone name, e.g. `Europe/London`. Checked again at build time."),
    Field("board.locale", "str", "en_US.UTF-8", False, "A UTF-8 locale such as `en_GB.UTF-8` or `C.UTF-8`."),

    Field("ssh.password_auth", "bool", False, False, "Allow SSH password logins. Off by default; needs a user password hash if on."),
    Field("ssh.root_login", "str", "disabled", False, "`disabled` or `key-only`."),
    Field("ssh.port", "int", 22, False, "sshd port (1-65535)."),

    Field("user[].name", "str", None, False, "Login name. `root` is not allowed here."),
    Field("user[].sudo", "str", "auto", False, "`nopasswd`, `password` or `none`. `auto` = `password` if a password hash is set, else `nopasswd`."),
    Field("user[].groups", "list[str]", ["sudo", "dialout", "audio", "video", "plugdev"], False, "Extra groups."),
    Field("user[].authorized_keys", "list[str]", [], False, "SSH public keys, one per list entry."),
    Field("user[].authorized_keys_file", "str", None, False, "Path to a file of public keys (e.g. `~/.ssh/id_ed25519.pub`)."),
    Field("user[].password_hash", "str", None, True, "A `$6$` SHA-512 crypt hash (never plaintext). Make one with `percept hash-password`."),
    Field("user[].password_hash_file", "str", None, True, "File containing the hash."),
    Field("user[].password_hash_env", "str", None, False, "Environment variable holding the hash."),
    Field("user[].password_mode", "str", "none", False, "`none`, `hash` (use password_hash) or `generate` (a random password is written once to `credentials.txt`)."),

    Field("network.ethernet.mode", "str", "dhcp", False, "`dhcp` or `static`."),
    Field("network.ethernet.address", "str", None, False, "Static IPv4 address (static only)."),
    Field("network.ethernet.prefix", "int", None, False, "Prefix length, 1-30 (static only)."),
    Field("network.ethernet.gateway", "str", None, False, "Default gateway inside the subnet (static only)."),
    Field("network.ethernet.dns", "list[str]", [], False, "DNS servers (static only)."),
    Field("network.ethernet.domain", "str", None, False, "Search domain."),
    Field("network.ethernet.ipv6", "str", "auto", False, "`auto` or `off`."),

    Field("network.wifi.enabled", "bool", False, False, "Configure Wi-Fi."),
    Field("network.wifi.ssid", "str", None, False, "Network name, 1-32 bytes."),
    Field("network.wifi.psk", "str", None, True, "Passphrase (8-63 chars) or 64 hex digits."),
    Field("network.wifi.psk_file", "str", None, True, "File containing the passphrase."),
    Field("network.wifi.psk_env", "str", None, False, "Environment variable holding the passphrase."),
    Field("network.wifi.country", "str", None, False, "ISO 3166 alpha-2 country (regulatory domain). Required when Wi-Fi is enabled."),
    Field("network.wifi.security", "str", "wpa2", False, "`wpa2`, `wpa3` or `open`."),
    Field("network.wifi.hidden", "bool", False, False, "Network does not broadcast its SSID."),

    Field("rescue.username", "str", "root", False, "SSH recovery login name; recovery accounts have administrator UID 0."),
    Field("rescue.enabled", "bool", True, False, "Keep the SSH rescue mode (recommended). Keys by default; passwords if `password_auth` is on."),
    Field("rescue.net_mode", "str", "dhcp", False, "`dhcp` or `static`. Static is easier to find when something is wrong."),
    Field("rescue.address", "str", None, False, "Rescue IPv4 address (static only)."),
    Field("rescue.prefix", "int", None, False, "Rescue prefix length (static only)."),
    Field("rescue.gateway", "str", None, False, "Rescue gateway (optional)."),
    Field("rescue.authorized_keys", "list[str]", [], False, "Rescue SSH keys. Defaults to the first user's keys."),
    Field("rescue.password_auth", "bool", False, False, "Allow password login (as `root`) in rescue mode. Uses `rescue.password_hash`, else the first user's password."),
    Field("rescue.password_hash", "str", None, True, "A `$6$` hash for the rescue `root` password (optional; defaults to the first user's)."),
    Field("rescue.password_hash_file", "str", None, True, "File containing the hash."),
    Field("rescue.password_hash_env", "str", None, False, "Environment variable holding the hash."),
    Field("rescue.fail_limit", "int", 3, False, "Failed boots before the launcher enters rescue (1-10)."),
    Field("rescue.grub_tries", "int", 4, False, "GRUB boot-attempt countdown start (1-4)."),
    Field("rescue.log_receiver_ip", "str", None, False, "Optional UDP boot-log receiver address."),
    Field("rescue.log_receiver_port", "int", None, False, "Port for the log receiver."),

    Field("os.profile", "str", "debian-trixie", False, "Profile directory name under `profiles/`."),
    Field("os.cpu_profile", "str", "oc1500", False, "Experimental `oc1500` (800/1300/1500 MHz, the default), `rated` (800/1300 MHz) or `unchanged`. `rated` and `oc1500` require the profile CPU-power contract."),
    Field("os.mirror", "str", None, False, "Debian mirror URL override."),
    Field("os.kernel.source", "str", "distro", False, "`distro` (profile default), `files` (your Image/initrd/modules) or `custom`."),
    Field("os.kernel.image", "str", None, False, "Path to an arm64 `Image` (files only)."),
    Field("os.kernel.initrd", "str", None, False, "Path to the initramfs (files only)."),
    Field("os.kernel.modules", "str", None, False, "Path to a modules tarball or directory (files only)."),
    Field("os.kernel.config", "str", None, False, "Kernel `.config` for the contract check (files only)."),
    Field("os.kernel.release", "str", None, False, "`uname -r` of the supplied kernel (files only)."),
    Field("os.kernel.cmdline_extra", "str", "", False, "Appended to the profile's baseline kernel command line. Characters: letters, digits and `_ . , = : / + -` and space."),
    Field("os.features.gpu", "bool", None, False, "Enable the Vivante GPU (profile default if omitted)."),
    Field("os.features.vpu", "bool", None, False, "Enable Hantro video decode. Needs gpu."),
    Field("os.features.usb_c_host", "bool", None, False, "USB-C port as host."),
    Field("os.features.camera", "bool", None, False, "Install the Vision camera runtime helpers."),
    Field("os.features.upper_ram", "bool", None, False, "Expose the fourth GiB of RAM."),
    Field("os.features.thermal", "bool", None, False, "Thermal sensor device-tree fix."),
    Field("os.packages.extra", "list[str]", [], False, "Extra Debian packages to install."),

    Field("storage.layout", "str", "auto", False, "`auto` (v2 for image installs, factory for ssh), `v2` or `factory`."),
    Field("storage.root_size", "str", "fill", False, "`fill` or a size in MiB (e.g. `4096`)."),
    Field("storage.esp_size_mib", "int", None, False, "ESP size in MiB (layout default if omitted)."),

    Field("install.method", "str", "uuu", False, "`uuu` (flash an image from Windows/Linux) or `ssh` (convert a running board)."),
    Field("install.ssh_host", "str", None, False, "Board address for `ssh` installs."),
    Field("install.ssh_user", "str", "root", False, "Login for `ssh` installs."),
    Field("install.ssh_port", "int", 22, False, "SSH port for `ssh` installs."),
    Field("install.uuu_path", "str", None, False, "Path to `uuu`/`uuu.exe` (found automatically if omitted)."),
]


def allowed_paths():
    return {f.path.replace("[]", "") for f in FIELDS}


def secret_paths():
    return {f.path.replace("[]", "") for f in FIELDS if f.secret}


def section_paths():
    """All table prefixes (e.g. 'network', 'network.wifi', 'user')."""
    out = set()
    for f in FIELDS:
        parts = f.path.replace("[]", "").split(".")
        for i in range(1, len(parts)):
            out.add(".".join(parts[:i]))
    return out
