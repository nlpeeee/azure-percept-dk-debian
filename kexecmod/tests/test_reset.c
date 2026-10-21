/* Exercise the real reset implementation with a fake CAAM register bank. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#define PERCEPT_CAAM_TEST
#define __iomem
typedef uint32_t u32;
static unsigned char storage[3][4096];
static void *rings[3] = {storage[0], storage[1], storage[2]};
static bool little_endian, percept_caam_reset;
static unsigned int commands[3], status_reads[3], command_reads[3], delays;
static int halt_stuck, reset_stuck, mask_stuck;
#define pr_emerg(...) ((void)0)
static u32 ioread32(void *addr);
static u32 ioread32be(void *addr);
static void iowrite32(u32 value, void *addr);
static void iowrite32be(u32 value, void *addr);
static void udelay(unsigned int usec) { delays += usec; }
#include "../../sources/kexec-mod/kernel/percept_caam.c"

static unsigned int ring_of(void *addr)
{
	unsigned int i;
	for (i = 0; i < 3; i++)
		if ((unsigned char *)addr >= storage[i] &&
		    (unsigned char *)addr < storage[i] + 4096)
			return i;
	assert(0);
	return 0;
}
static u32 raw_read(void *addr)
{
	u32 value;
	memcpy(&value, addr, 4);
	return little_endian ? value : __builtin_bswap32(value);
}
static void raw_write(void *addr, u32 value)
{
	if (!little_endian) value = __builtin_bswap32(value);
	memcpy(addr, &value, 4);
}
static u32 model_read(void *addr)
{
	unsigned int i = ring_of(addr);
	size_t off = (unsigned char *)addr - storage[i];
	if (off == CAAM_JRINT && commands[i] == 1 &&
	    ++status_reads[i] == 5 && (int)i != halt_stuck)
		raw_write(addr, CAAM_HALT_COMPLETE);
	if (off == CAAM_JRCR && commands[i] == 2 &&
	    ++command_reads[i] == 5 && (int)i != reset_stuck) {
		raw_write(addr, 0);
		raw_write(storage[i] + CAAM_JRINT, 1); /* pending W1C interrupt */
		raw_write(storage[i] + CAAM_JRCFG_LO, 0x100); /* reset clears mask */
	}
	return raw_read(addr);
}
static void model_write(void *addr, u32 value)
{
	unsigned int i = ring_of(addr), j;
	size_t off = (unsigned char *)addr - storage[i];
	if (off == CAAM_JRCFG_LO && (int)i == mask_stuck)
		return;
	if (off == CAAM_JRCR) {
		assert(value == CAAM_JRCR_RESET);
		for (j = i; j < 3; j++)
			assert(raw_read(storage[j] + CAAM_JRCFG_LO) & CAAM_JRCFG_IMSK);
		assert(++commands[i] <= 2);
		if (commands[i] == 1)
			raw_write(storage[i] + CAAM_JRINT, 4);
	}
	if (off == CAAM_JRINT)
		value = raw_read(addr) & ~value;
	raw_write(addr, value);
}
static u32 ioread32(void *addr) { assert(little_endian); return model_read(addr); }
static u32 ioread32be(void *addr) { assert(!little_endian); return model_read(addr); }
static void iowrite32(u32 value, void *addr) { assert(little_endian); model_write(addr, value); }
static void iowrite32be(u32 value, void *addr) { assert(!little_endian); model_write(addr, value); }
static void setup(bool le)
{
	unsigned int i;
	memset(storage, 0, sizeof(storage));
	memset(commands, 0, sizeof(commands));
	memset(status_reads, 0, sizeof(status_reads));
	memset(command_reads, 0, sizeof(command_reads));
	little_endian = le;
	percept_caam_reset = true;
	halt_stuck = reset_stuck = mask_stuck = -1;
	delays = 0;
	for (i = 0; i < 3; i++) raw_write(storage[i] + CAAM_JRCFG_LO, 0x100);
}
int main(void)
{
	unsigned int i, le;
	for (le = 0; le < 2; le++) {
		setup(le);
		assert(percept_caam_quiesce() == 0);
		for (i = 0; i < 3; i++) {
			assert(commands[i] == 2);
			assert(raw_read(storage[i] + CAAM_JRCFG_LO) == 0x101);
			assert(raw_read(storage[i] + CAAM_JRINT) == 0);
			assert(raw_read(storage[i] + CAAM_JRCR) == 0);
		}
		setup(le); halt_stuck = 1;
		assert(percept_caam_quiesce() == -ETIMEDOUT);
		assert(commands[0] == 2 && commands[1] == 1 && commands[2] == 0);
		assert(delays >= 100000 && delays < 100020);
		setup(le); reset_stuck = 0;
		assert(percept_caam_quiesce() == -ETIMEDOUT);
		assert(commands[0] == 2 && commands[1] == 0 && commands[2] == 0);
		setup(le); mask_stuck = 1;
		assert(percept_caam_quiesce() == -EIO);
		assert(commands[0] == 0 && commands[1] == 0 && commands[2] == 0);
		setup(le); percept_caam_reset = false;
		assert(percept_caam_quiesce() == 0);
		assert(commands[0] == 0 && commands[1] == 0 && commands[2] == 0);
	}
	puts("PASS: LE/BE reset order, masks, W1C, disabled mode, halt/reset timeouts and mask failure");
	return 0;
}
