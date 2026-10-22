# SPDX-License-Identifier: MIT
"""Post-bootstrap packages: use APT's resolver for the VPU runtime."""
import json
import sys

VPU_RUNTIME = ('gstreamer1.0-tools', 'gstreamer1.0-plugins-base',
               'gstreamer1.0-plugins-good', 'gstreamer1.0-plugins-bad')


def vpu_packages(cfg):
    return list(VPU_RUNTIME) if cfg['os']['features'].get('vpu', True) is not False else []


def check_inventory(packages, vpu):
    installed = {p.split('=')[0].split(':')[0] for p in packages}
    missing = set(VPU_RUNTIME) - installed if vpu else set()
    if missing:
        raise ValueError('VPU image is missing runtime packages: ' + ', '.join(sorted(missing)))


if __name__ == '__main__':
    with open(sys.argv[1], encoding='utf-8') as source:
        print(' '.join(vpu_packages(json.load(source)['config'])))
