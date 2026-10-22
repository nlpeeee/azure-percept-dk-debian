# SPDX-License-Identifier: MIT
"""Finish a generic root tree as a portable, vendor-free bundle."""
import json
from pathlib import Path
import shutil
import hashlib
from .. import bundles, packages, vendor_recipe
from .pipeline import inputs


def finish_bundle(repo, cfg, out, work, root, root_uuid, esp_uuid, release, resolved, commit, run, recovery):
    inventory = (root/'percept-package-versions').read_text().splitlines()
    packages.check_inventory(inventory, resolved['features']['vpu'])
    if resolved['features'].get('camera'):
        raise ValueError('camera runtime is not supported in redistributable bundles')
    folder = work/'bundle'; folder.mkdir()
    run(['bash', repo/'build/pack-rootfs.sh', root, folder/'rootfs.img', root_uuid, '4096'])
    shutil.copy2(repo/'out/launcher/launcher.cpio.gz', folder/'launcher.cpio.gz')
    shutil.copy2(repo/'profiles'/cfg['os']['profile']/'profile.toml', folder/'profile.toml')
    from .pipeline import grub
    (folder/'grub.cfg').write_text(grub(repo), encoding='utf-8')
    zip_path = Path(recovery) if recovery else repo/'cache/downloads/recovery.zip'
    if not zip_path.is_file():
        raise ValueError('bundle needs the verified recovery ZIP; pass build --recovery PATH')
    recipe = vendor_recipe.generate(zip_path, repo/'cache/vendor/ms', inputs(repo)['ms-recovery-zip'])
    (folder/'vendor-recipe.json').write_text(json.dumps(recipe, indent=2)+'\n', encoding='utf-8')
    manifest = {'schema':1, 'kind':'percept-bundle', 'personal':False,
        'source_commit':commit, 'profile':cfg['os']['profile'], 'cpu_profile':cfg['os']['cpu_profile'],
        'features':resolved['features'], 'kernel_release':release, 'root_uuid':root_uuid,
        'esp_uuid':esp_uuid, 'rootfs_packages':inventory, 'hardware_tested':False,
        'launcher_build':json.loads((repo/'out/launcher/build.manifest.json').read_text()),
        'module_build':json.loads((repo/'out/kexecmod/modules.manifest.json').read_text()),
        'build_options':{'extra_packages':cfg['os']['packages']['extra'],
            'mirror_sha256':hashlib.sha256((cfg['os'].get('mirror') or '').encode()).hexdigest(),
            'cmdline_extra_sha256':hashlib.sha256((cfg['os']['kernel'].get('cmdline_extra') or '').encode()).hexdigest()},
        'qualification':{'generic_firstboot':'pending', 'vpu_from_image':'pending',
                         'cold_boots':'pending', 'rescue':'pending', 'kernel_rollback':'pending'}}
    destination = out/(cfg['os']['cpu_profile']+'.bundle.tar.gz')
    bundles.write_bundle(folder, manifest, destination)
    (work/'settings.json').unlink()
    print('Portable bundle: '+str(destination)+' (hardware qualification pending)', flush=True)
    return out
