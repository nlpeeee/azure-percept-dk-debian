# Architecture notes

- [boot-chain.md](boot-chain.md): firmware → shim → GRUB → stock kernel → launcher → your kernel
- [device-tree.md](device-tree.md): what is wrong with the vendor device tree for mainline and how it is adapted
- [upper-ram.md](upper-ram.md): how the fourth GiB of RAM is exposed
- [usb-c.md](usb-c.md): getting the USB-C port to probe

These were written while the first board was being brought up; examples use
placeholders such as `<board-ip>` where the original named a specific device.
