/* Pass-through GPIO LED checkpoint signal for the ARM64 kexec-tools purgatory.
 *
 * led_signal(unsigned int count) pulses the verified GPIO once per checkpoint
 * and RETURNS so purgatory execution continues to the next checkpoint and on
 * to the kernel. This is the key difference from experiments/percept-led/led.S,
 * whose signature repeats forever because it is a terminal probe.
 *
 * Freestanding and scratch-register-only: it touches no stack or static memory,
 * only the board-verified GPIO MMIO, so it is safe at any point in the purgatory
 * regardless of stack/BSS state. It is AAPCS-safe as a leaf: it clobbers only
 * x0-x16 (caller-saved) and never modifies x19-x29/sp/x30, so C callers and the
 * entry.S caller are unaffected. It does NOT alter DAIF (purgatory already runs
 * with exceptions masked and caches/MMU off).
 *
 * GPIO configuration must come from verified board evidence (see
 * experiments/percept-led/LED-HARDWARE.md); the arm64 purgatory Makefile passes
 * the same -D values as the standalone probe. There are deliberately no defaults.
 */
#if !defined(GPIO_BASE) || !defined(GPIO_BIT) || !defined(ACTIVE_LOW) || !defined(DELAY_LOOPS)
#error Supply verified GPIO_BASE, GPIO_BIT, ACTIVE_LOW and DELAY_LOOPS
#endif
#if GPIO_BIT < 0 || GPIO_BIT > 31 || (ACTIVE_LOW != 0 && ACTIVE_LOW != 1) || DELAY_LOOPS < 1
#error Invalid GPIO configuration
#endif
#if !defined(GPIO_CLOCK_GATE) || !defined(GPIO_MUX_REGISTER)
#error Supply verified GPIO_CLOCK_GATE and GPIO_MUX_REGISTER
#endif
#ifndef GPIO_GAP_UNITS
#define GPIO_GAP_UNITS 3	/* extra dark units AFTER each burst */
#endif
#if GPIO_GAP_UNITS < 1 || GPIO_GAP_UNITS > 16
#error GPIO_GAP_UNITS must be between 1 and 16 (zero would underflow)
#endif

.text
.balign 4
.globl led_signal
.type led_signal, %function
led_signal:				/* w0 = pulse count */
	/* Reject invalid counts before touching GPIO. All callers use 1, 2 or 5. */
	sub	w9, w0, #1
	cmp	w9, #7
	b.hi	12f
	mov	w13, w0
	/* i.MX8M GPIO3 CCGR: gate2 field 0b11 means on in all modes. */
	ldr	x9, =GPIO_CLOCK_GATE
	ldr	w12, [x9]
	orr	w12, w12, #3
	str	w12, [x9]
	dsb	sy
	/* SAI5_RXD2 ALT5 selects GPIO3_IO23; preserve SION and other bits. */
	ldr	x9, =GPIO_MUX_REGISTER
	ldr	w12, [x9]
	and	w12, w12, #0xfffffff8
	mov	w16, #5
	orr	w12, w12, w16
	str	w12, [x9]
	dsb	sy
	ldr	x10, =GPIO_BASE
	mov	w11, #1
	lsl	w11, w11, #GPIO_BIT
	/* i.MX GPIO DR=0x00, GDIR=0x04: set inactive level, then enable output. */
	ldr	w12, [x10]
#if ACTIVE_LOW
	orr	w12, w12, w11
#else
	bic	w12, w12, w11
#endif
	str	w12, [x10]
	dsb	sy
	ldr	w12, [x10, #4]
	orr	w12, w12, w11
	str	w12, [x10, #4]
	dsb	sy
	/* Signal immediately; the previous burst supplies the separation. */
3:	ldr	w12, [x10]		/* led on */
#if ACTIVE_LOW
	bic	w12, w12, w11
#else
	orr	w12, w12, w11
#endif
	str	w12, [x10]
	dsb	sy
	mov	w14, #1
4:	ldr	x15, =DELAY_LOOPS
5:	subs	x15, x15, #1
	b.ne	5b
	subs	w14, w14, #1
	b.ne	4b
	ldr	w12, [x10]		/* led off */
#if ACTIVE_LOW
	orr	w12, w12, w11
#else
	bic	w12, w12, w11
#endif
	str	w12, [x10]
	dsb	sy
	mov	w14, #1
6:	ldr	x15, =DELAY_LOOPS
7:	subs	x15, x15, #1
	b.ne	7b
	subs	w14, w14, #1
	b.ne	6b
	subs	w13, w13, #1
	b.ne	3b
9:	/* trailing dark gap */
	mov	w14, #GPIO_GAP_UNITS
10:	ldr	x15, =DELAY_LOOPS
11:	subs	x15, x15, #1
	b.ne	11b
	subs	w14, w14, #1
	b.ne	10b
12:	ret
.size led_signal, . - led_signal
.ltorg

.section .note.GNU-stack,"",%progbits
