# SPDX-License-Identifier: MIT
"""Post-bootstrap packages: use APT's resolver for the VPU and audio runtimes."""
import json
import sys

VPU_RUNTIME = ('gstreamer1.0-tools', 'gstreamer1.0-plugins-base',
               'gstreamer1.0-plugins-good', 'gstreamer1.0-plugins-bad')
AUDIO_RUNTIME = ('alsa-utils',)


def vpu_packages(cfg):
    return list(VPU_RUNTIME) if cfg['os']['features'].get('vpu', True) is not False else []


def audio_enabled(cfg, features=None):
    """Resolved features (profile defaults applied) win; otherwise an omitted
    board setting means the debian-trixie default, which is on."""
    if features is not None and 'audio' in features:
        return bool(features['audio'])
    return cfg['os']['features'].get('audio') is not False


def feature_packages(cfg, features=None):
    out = vpu_packages(cfg)
    if audio_enabled(cfg, features):
        out += AUDIO_RUNTIME
    return out


def check_inventory(packages, vpu, audio=False):
    installed = {p.split('=')[0].split(':')[0] for p in packages}
    missing = set(VPU_RUNTIME) - installed if vpu else set()
    if missing:
        raise ValueError('VPU image is missing runtime packages: ' + ', '.join(sorted(missing)))
    missing = set(AUDIO_RUNTIME) - installed if audio else set()
    if missing:
        raise ValueError('audio image is missing runtime packages: ' + ', '.join(sorted(missing)))


if __name__ == '__main__':
    with open(sys.argv[1], encoding='utf-8') as source:
        data = json.load(source)
    print(' '.join(feature_packages(data['config'], data.get('features'))))
