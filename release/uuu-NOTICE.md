# Native flashing utility

This candidate bundles NXP uuu 1.5.243 from the official release:
https://github.com/nxp-imx/mfgtools/releases/tag/uuu_1.5.243

The Windows executable and the Linux Ubuntu 20.04 x64 executable are pinned in
vendor/vendor-manifest.toml. NXP describes uuu as BSD licensed; its linked libusb
component remains LGPL licensed. The exact corresponding source release archive,
including upstream license texts and build files, accompanies this package as
uuu-source-1.5.243.tar.gz. The repository source is available at:
https://github.com/nxp-imx/mfgtools

Python dependency licenses are included alongside this notice. The application
does not redistribute Microsoft's recovery firmware or signed boot components.
