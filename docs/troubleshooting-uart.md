# Percept serial connector: photo identification

## Working console confirmed

The user confirmed readable UART output on 21 October 2026 using **<serial-port>,
115200 baud, 8 data bits, no parity, 1 stop bit, no flow control**. Windows
identified an FTDI USB serial interface. The exact adapter model and logic
voltage have not been recorded.

### User-confirmed pinout

Viewed from the LED/button edge toward the heatsink, as in
[Microsoft's reference photo](../sources/hardware-reference/microsoft-apdk-serial-pins.jpg),
the user confirmed the following on 21 October 2026:

| Position, left to right | Board signal | Receive-only adapter connection |
|---|---|---|
| Left, toward the fault LED | Not yet verified | Leave disconnected |
| Middle | TX (output from the board) | Adapter RX |
| Right, toward the DC input connector | GND | Adapter GND |

The middle-TX/right-GND connection produced readable output at the settings
above. The left pin has not been verified as RX.

The live board independently reports 115200, CS8, parity disabled, one stop bit
and hardware/software flow control disabled. `ttymxc0` belongs to
`30860000.serial`. The reconstructed matching kernel has
`CONFIG_SERIAL_EARLYCON=y` and the `ec_imx6q` early-console declaration.
The next diagnostic can add `earlycon=ec_imx6q,0x30860000` alongside the existing
`console=ttymxc0,115200` argument and retain serial output through the handoff.
An early-console log begins after early C initialization; silence alone does
not prove that the CPU never entered the kernel.

The most recently observed boot ID during this verification is
`1c5eb7fc-bdc3-4fd5-8c5c-b4e81b5ead0a`. No test hook is installed. The old
later-only bundle remains stale and testing remains paused pending the user
being ready for the next reboot. Configure PuTTY session output logging before
that run so the complete shutdown, handoff and subsequent boot can be preserved.

Logging was subsequently enabled at `<lab-checkout>\UART\putty.log` and verified
by finding the labelled `PERCEPT_UART_CAPTURE_CHECK percept-entry-20261021-03`
message written through the board console. A fresh **stock Image / quiet
purgatory / UART-only** bundle was prepared for that boot and passed staging.
All LED instrumentation is inactive in this new bundle. The test remains
unarmed; no reboot was issued during this preparation.

## Connector research

The user supplied `pics/board1.jpeg`, `board2.jpeg` and `board3.jpeg` on
21 October 2026. Microsoft's original serial-console guide was recovered from
the last repository commit before archival:

https://github.com/MicrosoftDocs/azure-docs/blob/30ca9855dea6dbafd43ac456e9c1965633e3676d/articles/azure-percept/how-to-connect-to-percept-dk-over-serial.md

Its original connector photo is saved, unmodified, at
`sources/hardware-reference/microsoft-apdk-serial-pins.jpg`; the Markdown source
is beside it. The marked connector is **three pins along the LED/button edge,
between the fault LED and the large DC input connector**. That is the location
to compare with the user's first photo. The header labelled `SPI_TPM` and the
TPM daughterboard connector are separate interfaces.

The original guide specifies 115200 baud and links Adafruit cable 954. Its
connector picture does not label GND/TX/RX, and it does not explicitly state the
board's logic voltage. The pinout above comes from the user's working connection,
not labels in Microsoft's picture. Logic voltage remains unverified; the
repository's existing 1.8V assertion should not be treated as confirmed by these
photos.

Removing the TPM does not remove the i.MX8MQ's on-chip ROM/fuse-rooted HAB
authentication, nor inherently disable UEFI image-signature policy. It may alter
attestation or cause firmware initialization failures. It is not an unsigned-boot
route. NXP's own description of the i.MX8M authentication mechanism is here:

https://github.com/nxp-imx/uboot-imx/blob/lf_v2022.04/doc/imx/habv4/guides/mx8m_secure_boot.txt

After the user's manual reboot, the observed source boot ID is
`e21bc17e-4e80-409b-96ee-e43574ad66a4`, running `5.4.3-26.cm1`. No test hook is
installed. The previously staged later-only bundle belongs to boot
`6e56d27c-7817-4f46-b83a-3bf3f2d631e9` and must not be re-armed. Capture a new
bundle with the current live FDT before the next authorized test. Testing remains
paused; no reboot was requested during this inspection.
