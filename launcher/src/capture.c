/* SPDX-License-Identifier: GPL-2.0 */
/* Capture kexec-tools' legacy kexec_load request; never load or execute it. */
#define _DEFAULT_SOURCE
#include <endian.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/syscall.h>
#include <unistd.h>

struct segment {
	const void *buf;
	size_t bufsz;
	unsigned long mem;
	size_t memsz;
};

static int write_all(int fd, const void *buf, size_t size)
{
	while (size) {
		ssize_t n = write(fd, buf, size);
		if (n < 0 && errno == EINTR)
			continue;
		if (n <= 0) {
			if (!n)
				errno = EIO;
			return -1;
		}
		buf = (const char *)buf + n;
		size -= n;
	}
	return 0;
}

long syscall(long number, ...)
{
	va_list ap;
	unsigned long entry, count, flags, i;
	const struct segment *segments;
	const char *path = getenv("KEXEC_BUNDLE");
	uint64_t total = 0;
	uint32_t header32[2];
	uint64_t entry_le, descriptor[3];
	int fd, saved;
	if (number != SYS_kexec_load) {
		errno = ENOSYS;
		return -1;
	}
	va_start(ap, number);
	entry = va_arg(ap, unsigned long);
	count = va_arg(ap, unsigned long);
	segments = va_arg(ap, const struct segment *);
	flags = va_arg(ap, unsigned long);
	va_end(ap);
	/* AArch64 or default architecture, with no crash/preserve flags. */
	if (sizeof(unsigned long) != 8 || !path || path[0] != '/' ||
	    !segments || !count || count > 16 ||
	    (flags != 0 && flags != (183UL << 16))) {
		errno = EINVAL;
		return -1;
	}
	for (i = 0; i < count; i++) {
		if (segments[i].bufsz > segments[i].memsz ||
		    segments[i].bufsz > (256UL << 20) ||
		    total + segments[i].bufsz > (512UL << 20)) {
			errno = EINVAL;
			return -1;
		}
		total += segments[i].bufsz;
	}
	fd = open(path, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0600);
	if (fd < 0)
		return -1;
	header32[0] = htole32(1);
	header32[1] = htole32(count);
	entry_le = htole64(entry);
	if (write_all(fd, "KXMBNDL1", 8) ||
	    write_all(fd, header32, sizeof(header32)) ||
	    write_all(fd, &entry_le, sizeof(entry_le)))
		goto fail;
	for (i = 0; i < count; i++) {
		descriptor[0] = htole64(segments[i].bufsz);
		descriptor[1] = htole64(segments[i].mem);
		descriptor[2] = htole64(segments[i].memsz);
		if (write_all(fd, descriptor, sizeof(descriptor)))
			goto fail;
	}
	for (i = 0; i < count; i++)
		if (write_all(fd, segments[i].buf, segments[i].bufsz))
			goto fail;
	if (fsync(fd))
		goto fail;
	if (close(fd)) {
		saved = errno;
		unlink(path);
		errno = saved;
		return -1;
	}
	fprintf(stderr, "Captured %lu segments to %s; no kernel loaded.\n", count, path);
	return 0;
fail:
	saved = errno;
	close(fd);
	unlink(path);
	errno = saved;
	return -1;
}

int reboot(int command)
{
	(void)command;
	errno = EPERM;
	return -1;
}
