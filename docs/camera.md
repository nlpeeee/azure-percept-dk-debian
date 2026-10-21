# Azure Percept Vision camera on Debian 13

Status, 21 October 2026, Debian `6.12.113+deb13-arm64` on the Percept DK. The
Vision SoM enumerates, the Myriad X boots, and the board captures real 720p video
and runs the bundled detector. No Docker, kernel patch or firmware update was
needed. Inference *accuracy* has not been validated.

## Hardware path

| Piece | Evidence |
|---|---|
| USB-C host port | The vendor DT's `extcon` phandle pointed at an `ite,it5201` with no Linux driver, so dwc3 deferred for ever. Stripping that one property fixed it; see [usb-c.md](usb-c.md). |
| SoM controller `045e:066f` | `bcdDevice 3.00`, so it is already on the updated firmware. **The unsupported SoM update is not needed** and was never run. Enumerates as `cdc_acm` (`/dev/ttyACM0`), not probed. |
| Myriad X `03e7:2485` | In its USB boot-ROM state until an application uploads `mx.mvcmd`; it then re-enumerates as `03e7:f63b` ("VSC Loopback Device") until the board is power-cycled or rebooted. |
| Sensor | The IMX219 sits behind the Myriad X. There is no `/dev/video*` for it and no UVC; frames only come out of the VPU through Microsoft's `mxIf` protocol. |

## Software: the extracted Microsoft runtime

Microsoft's retired `azureeyemodule` image (`2301-1-noauth`, ARM64) is the only
thing that speaks `mxIf`. It brings its own userspace (Mariner glibc, Intel
OpenCV/OpenVINO 2021.1, GStreamer), so it cannot be rebuilt from Debian
packages. A Docker image is only a tarball of layers, so it is unpacked into a
plain directory and run from a `chroot`:

- `experiments/percept-camera/assemble-eye-runtime.sh ARCHIVE /opt/eyesom`
  verifies the archive (`1a6dbe58…`), applies the ten layers in the order in its
  own `manifest.json` (613 whiteouts), and checks `/app/inference`,
  `/eyesom/mx.mvcmd`, the model, labels and the dynamic linker landed. 1.1 GB.
  The dynamic loader resolves every dependency inside the chroot (zero not-found).
- `experiments/percept-camera/percept-eye-run.sh record|preview [SECONDS]` checks
  that the SoM is `bcdDevice 3.00` and a Myriad X (`2485` or `f63b`) is present,
  bind-mounts `/proc`, `/sys` and `/dev` (that is how libusb reaches the VPU) and
  runs `/app/inference`. `record` uses `unshare -n`, an empty network namespace,
  so it is offline; `preview` shares the LAN. `EYE_FPS` and `EYE_SIZE` override
  the defaults (`720p` and `1080p` only; `480p` is rejected).
- **Mount isolation matters.** The script re-executes itself under
  `unshare --mount --propagation private`. An earlier version bind-mounted `/sys`
  and `/dev` into the chroot in the host's mount namespace and cleaned up with
  `umount -l`; because those are recursive copies of *shared* mounts, the unmount
  propagated back and removed the real `/sys/fs/cgroup`, `/dev/pts`, `/dev/shm`,
  `/dev/mqueue`, `/sys/kernel/debug`, `/sys/kernel/security`, `/sys/fs/pstore`
  and `/sys/fs/bpf`. Every camera run silently degraded the running system (new
  cgroups and scopes failed with "No such file or directory", leaving dozens of
  failed `session-N.scope` units, and no new ptys) until the next reboot. It was
  caught by `verify-boot.sh`, fixed, and re-tested: after a `record` and a
  `preview` run all seven mounts are intact and the system state is `running`.
  Do not use any copy of the script without that wrapper.
- This is a chroot as root, **not** a security boundary. The RTSP feed is
  unauthenticated and unencrypted: keep it on a trusted LAN.

## Proof of capture

A 30 s offline `record` produced 78 MB of H.264. `ffprobe` reports h264 1280×720
with 782 frames, and a decoded frame is a sharp, correctly exposed picture of the
desk with legible on-screen text. A non-empty file alone is not proof; the
decoded image is. `sources/firmware-audit/camera-20261021/` has the recording,
log and decoded frames.

Expected log noise that is not a fault: `IOTEDGE_AUTHSCHEME not set` and "Could
not create an Azure IoT SDK client handle" (no IoT Edge here; it continues),
GStreamer plugins that cannot load optional libraries, `Blocked event would cause
dispatching thread to wait on semaphore infinitely`, and `double free or
corruption (fasttop)` when the process is stopped (it aborts on shutdown after
the work is done).

## Streams and the "10 seconds of lag"

`preview` serves RTSP on port 8554: `/raw`, `/rawTCP`, `/result`, `/resultTCP` (MJPEG
over RTP, `/result*` with detector overlay) and `/h264raw`.

Measured from the PC over 15 s, all at 720p:

| Endpoint, camera config | Real-time factor | Notes |
|---|---|---|
| `/rawTCP`, `--fps=30` | **0.62×** (~18 fps arriving) | falls behind, delay grows |
| `/resultTCP`, `--fps=30` | **0.56×** (~16 fps arriving) | falls behind, delay grows |
| `/h264raw`, `--fps=30` | **1.08×** (~29 fps) | real time |
| `/rawTCP` and `/resultTCP`, `--fps=15` | **1.14×** | real time, no growth |

Cause: the MJPEG endpoints use a single-threaded software JPEG encode that adds
a whole CPU core (inference process 128% alone, 229% with a `/resultTCP` client)
and manages ~17 fps at 720p on a 1.3 GHz A53, while the stream is stamped 30 fps.
A producer slower than its timestamps behind an unbounded queue is exactly an
ever-growing delay. The H.264 path is encoded on the Myriad X and adds only ~20%.

Recommendations: for low latency use **`/h264raw`** (no overlay) or run
`EYE_FPS=15 percept-eye-run.sh preview` for the annotated MJPEG endpoints. A
client can also help (`ffplay -fflags nobuffer -flags low_delay -rtsp_transport
tcp`). I did not measure glass-to-glass latency, only delivery rate and CPU.

The camera's own frame rate varies: frame timestamps showed 30.0 fps in one run
and 15.0 fps later, when the room was darker, consistent with the IMX219's
auto-exposure lengthening frame time. `--fps` does not set it.

## Not done

Detection accuracy (every `nn:` result in the desk scene was empty, which proves
only that the loop runs), a custom model, audio (the Ear SoM was not attached),
the SoM serial protocol on `/dev/ttyACM0`, and anything on the Azure/IoT side.
