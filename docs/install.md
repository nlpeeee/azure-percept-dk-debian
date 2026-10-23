# Guided USB installation

The source-built personalized installer first booted successfully on one board
on 22 October 2026. Three cold boots, rescue fallback and kernel-update rollback
remain separate, unqualified acceptance checks. A completed manifest proves a
build completed, not that its particular image has been hardware-tested.

## Prepare and review

Use Windows Python 3.9+, Git, WSL2 with Debian/Ubuntu, a data-capable USB-C cable,
the DK power supply and at least 30 GB free for the build. Keep the original
Microsoft factory restoration package and a backup of needed board data.
Flashing replaces the installed system.

From the Windows repository:

```text
python percept setup --board my-percept
python percept doctor
```

Setup creates a board or reuses its saved configuration without overwriting it.
Review the summary; choose edit, save changes with your editor, then press Enter
to reload and validate. The exact folder name remains my-percept; hostname is
independent. `configure --name my-percept` also fixes the folder name explicitly.
For advanced fields see [configuration.md](configuration.md). Both board.toml
and secrets.toml are local files; keep passwords/hashes in secrets.toml.

Password login is supported for Debian and recovery, with optional public keys.
Recovery can have a separate username/password. Never copy a private SSH key to
the board. Selecting an existing public key does not unlock its encrypted PC
private key: interactive SSH prompts for its passphrase. For unattended checks,
load that key into a working PC SSH agent with `ssh-add PATH-TO-PRIVATE-KEY`
and confirm it appears with `ssh-add -l`. Do not remove the passphrase to work
around an unattended check. Password login remains an independent option.

Choose Ethernet DHCP/static, optional Wi-Fi, recovery addressing and CPU policy.
The default is the experimental `oc1500` (800/1300/1500 MHz); `rated` selects
800/1300 MHz and `unchanged` leaves CPU frequency control off. SSH conversion is not yet implemented;
use USB (`install.method = "uuu"`).

## Synchronize, download and build

Windows is authoritative. Commit only reviewed source paths first. In the WSL
build checkout, check `git status --short`; preserve any local changes before
synchronizing. A local transfer needs no public push (adapt the drive/path):

```sh
git fetch /mnt/e/azure-percept-dk-debian HEAD
git merge --ff-only FETCH_HEAD
```

Do not reset a diverged checkout. Resolve the divergence before building. The
Windows command checks matching commits; WSL also rejects dirty source. Board
settings are resolved on Windows and passed privately over stdin. They are not
copied by Git. Downloads and build caches stay in WSL.

```text
python percept fetch
python percept build --board my-percept
```

Use `--distro Debian --wsl-repo /home/YOU/azure-percept-dk-debian` on both
commands if the defaults select the wrong distro or checkout. Fetch can reuse
an existing ZIP with `--recovery PATH-TO-RECOVERY.zip`; hashes must match.
First downloads and emulated ARM64 builds can take tens of minutes or longer;
there is no measured universal ETA. Long subprocess stages report elapsed time
every 30 seconds; inspect the private build.log for detailed output.

Each build uses a timestamp directory. A directory without a PERSONAL manifest
is incomplete: never flash its raw image. After a failure, fix the reported
problem and rerun; completed cached downloads can be reused. A cached hash
mismatch requires replacing the named damaged download, not bypassing hashes.
Keep failed logs private because settings and generated credentials are nearby.

Successful Windows builds copy their new artifacts back to Windows and print an
exact flash command. Use that command, not an older directory or a guessed path.
Copy failure leaves the completed WSL artifacts available: copy the matching
manifest and every artifact it names together before flashing. Multiple completed
builds can coexist; only the manifest from your intended build should be selected.
See [build-wsl.md](build-wsl.md) for artifact layout and technical details.

## Enter USB recovery and flash

Follow the orientation in the archived Microsoft [DIP switch photo](https://github.com/MicrosoftDocs/azure-docs/blob/30ca9855dea6dbafd43ac456e9c1965633e3676d/articles/azure-percept/media/how-to-usb-update/dip-switch-03.jpg)
and [USB update instructions](https://github.com/MicrosoftDocs/azure-docs/blob/30ca9855dea6dbafd43ac456e9c1965633e3676d/articles/azure-percept/how-to-update-via-usb.md).
Do not infer up/down from a rotated board or photograph.

1. Power the board off before moving switches.
2. Locate the internal four-way DIP block at the board corner. Change normal
   **1001 (up-down-down-up)** to USB **0101 (down-up-down-up)** in the official
   photo orientation. There is no established external recovery button.
3. Connect USB-C to the PC, then power the board on.
4. Run the exact flash command printed by the build. It verifies hashes, detects
   one known USB device, then requires `ERASE my-percept`. This wrapper requires
   recovery mode *before* starting; do not follow a wait-first vendor sequence.
5. Wait for uuu to finish successfully. Keep power and USB connected throughout.
6. Power off, restore **1001**, then power on for the installed system.

If detection finds zero devices, check switch orientation, power and a USB data
cable. If it finds more than one, disconnect other recovery devices and retry.
Detection or confirmation failure performs no flash. A uuu failure may leave a
partial installation: retain its error output and use the original Microsoft
factory restoration procedure if needed. This project adds no restoration tool.

## First login and checks

First boot expands the eMMC root and creates SSH host keys. Allow several minutes;
find the DHCP address in your router, or use the configured static address.
Connect with `ssh YOUR-USER@BOARD-IP`. Use the password selected in setup, or
the matching private key on your PC. Generated passwords are in the private
credentials.txt beside the image. If SSH reports a changed host key after a
reinstall, independently verify the board identity before updating known_hosts.

Once logged in, run these read-only checks:

```sh
hostnamectl
uname -r
nproc
free -h
lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINTS
df -h /
ip -brief address
systemctl --failed
sudo -v
```

Expect your chosen hostname, the manifest's Debian kernel, four CPUs, roughly
3.5 GiB usable memory after reservations, and a root filesystem expanded to the
available eMMC space. Check the selected network interface has an address and
sudo accepts your configured login. For CPU policy/service errors, inspect
`journalctl -b` locally. A successful SSH connection establishes authentication,
not hardware qualification. An encrypted-key signing failure on the PC does not
prove the board rejected the installed public key.

If login fails, check the IP and username, normal DIP position, and whether the
chosen password/key belongs to Debian or recovery. Use local console diagnostics
if available. Do not repeatedly power-cycle as a substitute for diagnosis.
Record cold-boot, rescue and kernel-update rollback results separately; do not
assume they passed because the first boot worked.
