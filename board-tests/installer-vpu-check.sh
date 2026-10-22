#!/bin/sh
# SPDX-License-Identifier: MIT
# Run manually on the installed board; read-only evidence, no package installation.
set -eu
printf 'Kernel: '; uname -r
dpkg-query -W -f='${binary:Package}=${Version}\n' gstreamer1.0-tools \
    gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad
printf '\nStateless decoder discovery (requires real device nodes):\n'
gst-inspect-1.0 v4l2codecs
printf '\nVideo nodes:\n'
ls -l /dev/video* /dev/media* 2>/dev/null || true
printf '\nDiscovery is not a decoding test. Repeat the documented hardware decode vectors without installing packages.\n'
