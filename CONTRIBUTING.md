# Contributing

Thanks for helping. Hardware reports are the most valuable contribution: this
project has been verified on very few boards.

## Before you open a PR

```bash
python dev/scrub-scan.py          # no board identifiers, secrets or big files
python -m unittest discover -s tests/unit -v
```

- Never commit per-board data: MAC addresses, IPs, UUIDs, serials, keys,
  Wi-Fi details, logs from your board. `dev/scrub-scan.py` enforces most of
  this; `dev/scrub-debt.txt` lists legacy files still awaiting cleanup.
- Add an SPDX header to new files (`MIT` for installer code, `GPL-2.0-only`
  for kernel-side derivatives); see `REUSE.toml`.
- Shell that mounts anything must run in a private mount namespace
  (`unshare --mount --propagation private`) - see `camera/percept-eye-run.sh`
  for what happens otherwise.
- Do not add Microsoft/ASUS/Intel/NXP binaries. Add the vendor URL and SHA-256 to
  `vendor/vendor-manifest.toml` instead.

## Reporting a board result

Run `board-tests/verify-boot.sh --vpu` (see its header for `PERCEPT_HOST`) and
attach the output with your kernel release and profile name.

## Adding an OS profile

Copy `profiles/_template/`, fill in `profile.toml`, run
`python -m percept profile check profiles/<yours>`, build, boot, and submit
the verify output. See `docs/profiles.md`.
