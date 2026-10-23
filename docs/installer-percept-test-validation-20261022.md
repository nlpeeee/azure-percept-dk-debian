# Personalized installer: first hardware validation

22 October 2026. The user flashed `percept-test` from the generated USB image.
Image source: `42dda5b869ac801395e07492a4fa452598af0921`.
Manifest: `E:\azure-percept-dk-debian\out\percept-test\20261022T072739Z\percept-test-PERSONAL.manifest.json`.
The original manifest and artifact hashes remain unchanged.

## Proven on the installed system

- Stock signed 5.4 launcher hands over to Debian `6.12.113+deb13-arm64`.
- Hostname, main-account password login, SSH public-key login and sudo work.
- All four CPUs are online. One shared policy offers 800/1300/1500 MHz with
  `schedutil`; the clock framework independently reports a 1.5 GHz core clock.
- Four CPU correctness workers passed for 60 seconds at 1.5 GHz. Peak CPU
  temperature was 41 C; ten following idle samples were all 800 MHz.
  `oc1500` remains an experimental profile above the board's factory grade;
  this short check does not replace an extended soak test.
- CPU cooling is registered; passive/critical trips remain 80/90 C.
- The root filesystem expanded to use the eMMC. A temporary 64 MiB write,
  fsync, page-cache eviction request and readback checksum test passed.
- The 64 MiB ESP mounts correctly. Both boot counters reset successfully.
- Wired Ethernet and Wi-Fi each completed an HTTPS request with HTTP 200.
- Bluetooth firmware loads and its controller is powered on.
- Mesa creates a hardware context using Vivante GC7000 rev 6214.
- Hantro G1/G2 decode all five tested codecs at 720p, 30 frames each. H.264,
  HEVC, VP8 and VP9 match software-decoded frames exactly. MPEG-2 achieves
  70.78 dB PSNR, within the established IDCT tolerance. Engine interrupt counts
  rise for each test. These are correctness checks, not throughput benchmarks.
- Both USB controller paths enumerate. No failed services or new kernel
  warnings appeared during these tests. No reboot was initiated.

## Omission discovered and fixed

The image included VPU drivers and FFmpeg but omitted the GStreamer stateless
V4L2 decoder runtime used by the previously proven hardware video tests.
Installed these Debian packages on the flashed OS:

```
gstreamer1.0-tools
gstreamer1.0-plugins-base
gstreamer1.0-plugins-good
gstreamer1.0-plugins-bad
```

Builder commit `e5f3b79` includes them when the VPU feature is enabled. Its
actual package-selection code was checked with VPU enabled and disabled, and
the commit was pulled into WSL. The usability task's separately staged source
changes were preserved. Rebuild commit `047708d` moves these packages to APT
after base bootstrap, because debootstrap missed their virtual dependency
providers. The VPU decoding results above include the post-flash package
installation on the first image.

The corrected image was rebuilt and validated on 22 October from commit
`047708dd4944d8b8c348989f537cabad1c9416ce`. Its directory is
`E:\azure-percept-dk-debian\out\percept-test\20261022T133658Z`.
The manifest and checksums record all versions and hashes; validation confirms
all four runtime packages, both GStreamer tools and the ARM64 stateless V4L2
plugin. The rebuilt image has not been flashed; the working board was untouched.

The PC's dedicated Percept test public key was also added for unattended
validation. Password login remains enabled. Credentials are not recorded here.
The ignored `boards/percept-test/board.toml` now retains this test key alongside
the original PC public-key file reference, so a rebuild preserves both.

## Remaining qualification

Flash and qualify the rebuilt installer when requested, including three cold
boots, booted recovery/fallback login and a kernel update with rollback.
Bluetooth pairing and external USB/SD peripheral tests remain separate.
Known CPU exception-level, unused FEC PHY, SDMA ROM-fallback and CMA-reservation
boot warnings also occurred in the previous working installation; they are not
new test-time faults. Keep the current power-management workarounds.

Sanitized results: `exports/installer-firstboot-20261022/validation.json`.
Private detailed audit, logs and sample results:
`sources/firmware-audit/installer-firstboot-20261022/`.
