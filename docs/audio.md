# Azure Percept Audio (Ear SoM) on Debian 13

Status, 23 October 2026, Debian `6.12.113+deb13-arm64` on the Percept DK. After a
one-time firmware update of the SoM controller, the Ear SoM enumerates as a standard
USB Audio Class 2 device and records from its four microphones and plays to its
3.5 mm jack with the stock `snd-usb-audio` driver. No kernel patch is needed.
Voice processing (beamforming, wake word) has not been evaluated yet.

## Hardware

Per Microsoft's datasheet: an XMOS XUF208 audio processor, four MEMS microphones
(MSM261D3526Z1CM) in a linear array with 40 mm spacing, and an STM32L462CE security
controller. Microsoft designed the speech processing to run on the host CPU (the
Microsoft Audio Stack in the Speech SDK), not on the SoM.

| USB device | Meaning |
|---|---|
| `045e:0673` "Azure Ear SoM Controller" | Security controller, `cdc_acm` (`/dev/ttyACM0`). Its `bcdDevice` is the firmware version. |
| `045e:0671` "Azure Ear SoM USB" | The audio device, `bcdDevice 2.31`. Appears only after the controller is updated. Interfaces 0-2 are audio (`snd-usb-audio`); interface 3 is HID (`usbhid`, one input-only 1-byte report with report ID 1, probably buttons). |

## Firmware requirement

| Controller `bcdDevice` | State |
|---|---|
| `1.00` | Old, cloud-authenticated firmware. The audio device stays locked and does not appear. |
| `3.00` | Updated firmware (attestation removed). Audio works. |

Check from the board:

```sh
lsusb -v -d 045e:0673 | grep bcdDevice
percept-ear-status          # installed by the audio feature; needs no lsusb
```

`percept-ear-status` is read-only. Exit codes: 0 healthy, 1 no Ear SoM attached,
2 firmware too old (it prints these instructions), 3 attached but no audio card.

### Update procedure

Use Microsoft's "Azure Percept DK SoM Attestation Update Tool". This repository does
not vendor or run it; you download and run it yourself.

- URL: <https://download.microsoft.com/download/7/7/a/77a2f57a-0ede-48be-988c-11796f7948da/Azure%20Percept%20DK%20SoM%20Attestation%20Update%20Tool.zip>
- Zip SHA-256: `b2e10ec2a5928f3e538d8705e4174088a2a322d0dd2e5572469daee4e0e55142`
- Binary `input/AP_Peripheral_Installer_v0.1` SHA-256:
  `a76b4e3ce55d0bfec1a284dc6cb89d72ab0a4f5e912008191d879ad226dfcbd0`

The binary is an aarch64 glibc executable and needs libusb-1.0 and libudev. It ran
natively on the board's Debian and works offline:

```sh
sha256sum Azure*Update*Tool.zip            # compare with the zip hash above
unzip Azure*Update*Tool.zip -d som-update
cd som-update
sha256sum input/AP_Peripheral_Installer_v0.1
chmod +x input/AP_Peripheral_Installer_v0.1   # if needed
sudo ./input/AP_Peripheral_Installer_v0.1
```

It prints "Complete" and exits 0 on success; check with `percept-ear-status`.

> **Warning: the update is irreversible.** There is no downgrade. It updates
> whichever Eye (`066f`) and Ear (`0673`) SoMs are attached, so attach only the SoMs
> you want updated. The Vision SoM on the reference board was already on firmware
> 3.00 (see [camera.md](camera.md)).

## What appears after the update

- `045e:0671` on the USB bus, and an ALSA card. The kernel names it generically
  (`USB`); the installer's udev rule renames it to `PerceptEar`.
- Capture: one stream, 5 channels, S32_LE (24 valid bits), 16000 Hz only.
- Playback: 2 channels, S32_LE, 16000 Hz only, to the 3.5 mm jack.
- Mixer: `Mic` capture volume 0-127 (per channel, plus a mono control); playback
  switch and volume controls named `Azure Ear SoM USB Linear4 Mic Array Device `.

### Capture channel map

| Channel | Content |
|---|---|
| ch0-ch3 | The four MEMS microphones. About -62 dBFS RMS in a quiet room. |
| ch4 | Hardware playback reference (loopback). A -20 dBFS tone played to the device appeared on ch4 at -20.0 dBFS peak; silent otherwise. |

The reference channel is what echo cancellation needs.

The mics are raw and in physical order along the array. In a clap test (23 October
2026), claps at the left end (facing the front) reached ch0 first and ch3 up to 4
samples later; claps at the right end reached ch3 first, with ch0 5 samples behind.
The physical maximum for the 120 mm span is about 5.6 samples at 16 kHz. Left to
right, ch0-ch3 sit at x = -60, -20, +20 and +60 mm. Speech at about 1 m peaks
near -40 dBFS: the SoM applies little gain, and the capture mixer is already at
its 0 dB maximum.

## ALSA names

The `audio` feature installs `/etc/alsa/conf.d/50-percept-ear.conf`. The system
default PCM is not changed.

| PCM | What it is |
|---|---|
| `percept_ear_raw` | `hw:PerceptEar,0`: raw 5 ch S32_LE 16 kHz, for beamforming or the Microsoft Audio Stack |
| `percept_mics` | The four microphones only (ch0-3), raw format and rate |
| `percept_mic` | Mono, average of ch0-3, with rate and format conversion, for ordinary applications |
| `percept_speaker` | Playback to the jack with rate and format conversion |

```sh
# raw 5-channel capture, 10 s
arecord -D percept_ear_raw -c 5 -f S32_LE -r 16000 -d 10 raw.wav
# four mics only
arecord -D percept_mics -c 4 -f S32_LE -r 16000 -d 10 mics.wav
# mono, converted for ordinary use
arecord -D percept_mic -f S16_LE -r 48000 -c 1 -d 10 voice.wav
# playback with conversion
aplay -D percept_speaker voice.wav
```

## Installer feature

The `audio` feature installs `alsa-utils` and three files: the udev rule
`/etc/udev/rules.d/70-percept-ear.rules`, the ALSA config
`/etc/alsa/conf.d/50-percept-ear.conf` and `/usr/local/bin/percept-ear-status`
(see `target/`). It is on by default in the `debian-trixie` profile and off in
`byo-kernel`. Installing it does not update the SoM firmware.

## Test scripts

Run from the PC with `PERCEPT_HOST` (and optionally `PERCEPT_KEY`) set, as for
the other board tests:

- `board-tests/verify-boot.sh --audio` fails unless the controller is on firmware
  3.00, `0671` is present, the card `PerceptEar` exists and capture has 5 channels.
  Without `--audio` it prints one INFO line. It can be combined with `--vpu`.
- `board-tests/audio-check.sh [SECONDS]` (default 8) records from
  `hw:PerceptEar,0`, reports per-channel RMS and peak, then plays a -20 dBFS 1 kHz
  tone while recording. It passes if ch0-3 are not silent (RMS above -90 dBFS and
  not all zeros) and ch4 peaks within 1 dB of -20 dBFS. It needs `alsa-utils` and
  `python3` on the board and removes its temporary WAV files.

## Voice processing (Speech SDK / Microsoft Audio Stack)

Microsoft designed the Audio SoM to deliver raw audio and do the voice processing
on the host, using the Microsoft Audio Stack (MAS) in the Speech SDK. MAS does
beamforming, echo cancellation, noise suppression, gain control and dereverberation.
The SoM's 4 mics plus the playback reference on the last channel are exactly the
input MAS expects on Linux. Microsoft's retired speech container
(`azureearspeechclientmodule:1.0.4-noauth`, Speech SDK 1.16) used the `Linear4`
geometry and spotted keywords on the device. Only the audio after a keyword went
to the cloud.

Evaluation on 23 October 2026 used Speech SDK 1.53.0 on this board, run in a
network namespace with only loopback (`unshare -rn`). Status: partial.

| Item | Result |
|---|---|
| SDK on Debian 13 | Python wheel and the C++ Linux tarball (`SpeechSDK-Linux-1.53.0`, SHA-256 `9f88b77c…`) load; every native dependency resolves on trixie. |
| MAS from Python | Not available: the Python package has no `AudioProcessingOptions` and no MAS library. Use C++, C# or Java. |
| MAS from C++ | `libMicrosoft.CognitiveServices.Speech.extension.mas.so` ships for arm64 and initialises with the `Linear4` preset or a custom linear geometry (±60/±20 mm) and `SpeakerReferenceChannel::LastChannel`. |
| Offline keyword spotting | Works with no network and no Azure key or `SpeechConfig`. Microsoft's 2022 `Computer.table` model from the container detected 4 of 5 synthetic "Computer" utterances (mono file). |
| Keyword + MAS | The first keyword on a 5-channel file is detected through MAS. The SDK then aborts inside its own threads when re-armed on file input. Live capture from `hw:PerceptEar,0` through MAS runs cleanly; re-arming after a live detection is not yet tested. |
| CPU (1 of 4 A53 cores) | Keyword alone about 72%, keyword + MAS on 4 mics about 97% (about a quarter of the board). |
| Spoken keyword | Not validated. One live 60 s run and two recordings gave no detections, but neither recording was confirmed to contain clean, repeated "Computer"s. The test was skipped. |
| Still to test | Spoken keyword detection rate and false accepts (preferably with a custom Speech Studio model), echo cancellation while playing, re-arming after a live detection, and whether the post-keyword audio stream is the processed signal. |

The container also includes `Front_Desk`, `HelloConcierge` and `Hi_Elva` keyword
models. Custom models can be made free in Speech Studio, and then run offline.
Speech-to-text after the keyword needs either the cloud service (Azure key) or
Microsoft's limited-access embedded speech models. None of the Speech SDK or
container files are redistributed here.

## Evidence

On 23 October 2026 the controller was on `bcdDevice 1.00` with audio locked. The
update tool was run natively on the board (rc 0, "Complete"); the controller then
reported `3.00` and `045e:0671` appeared. The measurements above (5-channel
S32_LE 16 kHz capture, -62 dBFS idle mic level, ch4 loopback at -20.0 dBFS, 2-channel
playback) were taken the same day. The raw logs, `lsusb` dumps, mixer dumps and WAVs
are lab material kept outside this repository.
