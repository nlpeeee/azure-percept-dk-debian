# Two-path Percept installer

This candidate adds a shared preparation path for source-built and downloaded
generic bundles. Hardware qualification of the new first-boot route is pending.
Nothing here uploads settings, connects to the board, or flashes automatically.

## Fast installation

Unzip the application package for your operating system. Open PerceptInstaller
for the wizard, or use the percept executable for terminal commands. Packaged
applications include Python, required libraries and native uuu; WSL and Git are
not required for preparation. Windows and Linux x64 are the initial targets.
macOS remains unqualified.

1. Select a signed release version, or select a local `.bundle.tar.gz` and
   explicitly confirm that you trust its source. Check its kernel, VPU capability,
   CPU variant and qualification status. Use `unchanged` unless you intend to
   select `rated` or explicitly experimental `oc1500`.
2. Create or reuse a saved board configuration. The wizard supports main and
   recovery usernames/passwords, optional public keys, Ethernet and Wi-Fi.
   Review the summary before preparation. The settings editor can update saved
   settings; secrets.toml is private. An encrypted private SSH key stays on your
   PC and needs its passphrase or a working SSH agent for login.
   Use **Import settings** to copy an existing board.toml together with its
   secrets.toml into the application's saved boards. Existing names are never
   overwritten, and the source files are preserved. References to local public-key
   and secret files retain absolute paths to their originals.
3. Supply the original pinned Microsoft recovery ZIP or allow its download from
   Microsoft. The application combines it locally with the generic bundle.
   Microsoft boot files are excluded from public bundles. Cached verified inputs
   allow offline preparation.
4. Prepare the image. Allow enough disk space for the expanded bundle, output
   disk and vendor inputs: preparation checks approximately twice the expanded
   bundle size plus 3 GiB. The output directory is private. A failed operation
   without a PERSONAL.manifest.json is incomplete and must not be flashed.
5. Follow [USB entry and flashing instructions](install.md#enter-usb-recovery-and-flash).
   Power off before changing the internal DIP block from 1001 to 0101, using the
   official photo orientation; connect USB-C and power on before detection.
   The wrapper detects one device before requesting typed `ERASE BOARD`.
6. After successful flashing, power off, restore 1001, and power on. First boot
   applies settings before network/login services, expands storage, and generates
   unique host keys. Allow several minutes and use the chosen network address.

On Linux, USB access needs an active desktop-session ACL or an appropriate udev
rule. If detection or flashing reports access denied, install the rules described
in the [official uuu guide](https://github.com/nxp-imx/mfgtools/wiki/UUU), reload
udev rules, and reconnect the device before retrying. The bundled uuu source and
upstream instructions accompany the candidate. Do not run the entire settings
application as root. On Windows, confirm the USB recovery device appears in
Device Manager and follow the original recovery package's driver instructions
if its driver is missing; keep the board's recovery-mode and cable checks separate.

Source CLI equivalents (packaged CLI omits `python`):

```text
python percept setup --board my-percept --mode prepare
python percept doctor --mode installer
python percept prepare --board my-percept --bundle PATH.bundle.tar.gz --trust-local --recovery PATH.zip
python percept prepare --board my-percept --release VERSION
python percept flash --board my-percept --manifest PATH-PRINTED-BY-PREPARE
```

Bundle CPU and build-time capabilities must match the saved configuration.
Kernel replacement, extra packages, mirror changes, custom root sizes and
camera runtime require the source workflow rather than silently modifying a
downloaded bundle. Portable preparation currently supports fill-to-eMMC root.

An empty trusted-key list in a development candidate deliberately disables release
downloads. Maintainers add their public key before packaging a publishable app;
no private key belongs in the source tree. Local builds remain available through
the explicit trust choice. Application executable signing is separate from
bundle-manifest signing; these development packages are not OS-signed releases.

## Build your own

Use [the Windows/WSL prerequisites](build-wsl.md), or a Linux build host. Preserve
any active build and local changes before synchronizing source. The baseline
includes e5f3b79 and follow-up 047708d: the stateless GStreamer stack is installed
with APT after bootstrap when VPU is enabled. It is not passed to debootstrap's
limited dependency resolver.

```text
python percept configure --name my-percept
python percept fetch --recovery PATH.zip
python percept build --board my-percept --target bundle --recovery PATH.zip
```

On Windows select `--distro` and `--wsl-repo` if necessary; committed source must
match. The bundle contains no personal board settings, even though an existing
board configuration supplies build-time OS/feature choices. Its package inventory,
kernel, CPU policy, source revision and all payload hashes are recorded. Use a
separate configuration/build for each CPU variant. Existing `--target image`
personalized builds continue to work.

The root filesystem has no login account or SSH host keys. Before first boot the
PC writes recovery credentials and a separate Debian payload into the ESP. The
first-boot service is ordered before network/login and boot-success marking. An
interrupted attempt resumes with the same settings; a changed payload is rejected.
After success it records completion and removes the consumed Debian payload.
Recovery configuration remains available independently.

Personal disk images and credentials.txt remain sensitive. Removal of a consumed
payload is not guaranteed secure erasure from flash storage. Keep personal outputs
private; never publish them. The application retains them for manual reuse and
does not silently delete failed artifacts.

## VPU validation and qualification

VPU-enabled bundle creation verifies the actual installed package inventory has:

```text
gstreamer1.0-tools
gstreamer1.0-plugins-base
gstreamer1.0-plugins-good
gstreamer1.0-plugins-bad
```

Existing successful hardware decoding used these packages installed after flashing.
It does not qualify a rebuilt image or the new generic first-boot route. After an
authorized flash of each candidate, run `board-tests/installer-vpu-check.sh` locally
on the board and repeat the proven hardware decoding vectors without installing
additional packages. `gst-inspect-1.0 v4l2codecs` is discovery, not proof of decoding.
Record source revision, image hashes, package/kernel versions and actual results.

Keep separate pending gates for Windows/Linux flash, first login, storage growth,
three cold boots, interrupted-provisioning recovery, kernel-update rollback and
each CPU variant. Build completion never changes hardware_tested to true.

## Maintainer packaging and signatures

Use Python 3.13 and install requirements-installer.txt in an isolated environment.
Linux packagers also need binutils, a Python shared library, Tk/Tcl development
runtime and a desktop/font environment; these are packaging prerequisites, not
requirements for end users of the packaged application. Build on
each native OS; PyInstaller does not cross-compile. Use a reviewed uuu 1.5.243
binary and its digest:

```text
python dev/package-installer.py --uuu PATH --uuu-sha256 EXPECTED-DIGEST --output NEW-DIRECTORY
python dev/release-manifest.py --version VERSION --output release.json BUNDLE-PATHS
python dev/sign-release.py --manifest release.json --key EXTERNAL-ED25519-PEM --key-id KEY-ID --output release.sig
```

Before release packaging, configure release/policy.json with your Ed25519 public
key, base64 encoded raw 32-byte form, under the same key ID. release.sig signs the
exact bytes of release.json; that document authenticates each bundle's digest.
Keep the private key offline/outside Git. Upload only after separate authorization.

Native uuu, Python and dependency notices accompany the application. Include the
reviewed native tool's corresponding source/build details and third-party license
texts in release materials. Public bundle packaging uses a fixed file allowlist;
the extraction recipe contains byte offsets/hashes, not Microsoft binaries.

Validation commands:

```text
python -m unittest discover -s tests/unit -v
python dev/scrub-scan.py
git diff --check
```

Install installer requirements to exercise FAT and Ed25519 tests. On Linux run
the suite to exercise Unix permissions, service staging and shell behavior too.
Clean-machine preparation tests and real-board qualification remain release gates.

For the destructive offline integration test, use a disposable copy of a generic
root inside private mapped-user and mount namespaces with private /dev and /proc.
Run `tests/generic-firstboot-offline.py --disposable-root PATH`, then verify its
systemd service graph with `systemd-analyze --root=PATH --man=no verify` for
percept-provision.service, ssh.service, systemd-networkd.service and
percept-boot-ok.service. Treat any ordering-cycle diagnostic as a failure even
if systemd-analyze exits successfully. Never point this test at a live or personal
root. It exercises interruption after account creation, retry and identity
preservation; it does not replace booting the new image on the board.
