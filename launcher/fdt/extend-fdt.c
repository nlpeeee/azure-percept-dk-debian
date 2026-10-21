/* SPDX-License-Identifier: GPL-2.0 */
/* Extend only the known Percept memory bank; retain all other live FDT bytes.
 * Exit status: 0 applied, 3 not applicable (already 4 GiB), 1 anything else. */
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static void fail(const char *message)
{
    fprintf(stderr, "percept-upper-ram: %s\n", message);
    exit(1);
}
static uint32_t be32(const unsigned char *p)
{
    return (uint32_t)p[0]<<24 | (uint32_t)p[1]<<16 | (uint32_t)p[2]<<8 | p[3];
}
static size_t align4(size_t n) { return (n+3)&~(size_t)3; }
static void span(size_t off, size_t len, size_t end)
{
    if (off > end || len > end-off) fail("invalid FDT bounds");
}
int main(int argc, char **argv)
{
    unsigned char *data;
    size_t size=0, capacity=2*1024*1024, pos, end, strings, nstrings, reg=0;
    int in, out, depth=-1, memory_depth=-1, chosen_depth=-1, finished=0;
    unsigned int memories=0, addr_cells=0, size_cells=0, regs=0, secure_boot=0;
    ssize_t n;
    static const unsigned char expected[16] = {
        0,0,0,0, 0x40,0,0,0, 0,0,0,0, 0xc0,0,0,0
    };
    static const unsigned char extended[16] = {
        0,0,0,0, 0x40,0,0,0, 0,0,0,1, 0,0,0,0
    };
    int already = 0;
    if (argc != 3) fail("usage: extend-fdt INPUT OUTPUT");
    data=malloc(capacity);
    if (!data) fail("allocation failed");
    in=open(argv[1],O_RDONLY);
    if (in<0) fail("cannot open input");
    while ((n=read(in,data+size,capacity-size))>0) {
        size+=(size_t)n;
        if (size==capacity) fail("FDT too large");
    }
    if (n<0 || close(in)) fail("input read failed");
    if (size<40 || be32(data)!=0xd00dfeed || be32(data+4)!=size ||
        be32(data+20)!=17 || be32(data+24)>17) fail("unexpected FDT header");
    pos=be32(data+8); strings=be32(data+12); nstrings=be32(data+32);
    span(pos,be32(data+36),size); end=pos+be32(data+36);
    span(strings,nstrings,size);
    while (pos<end) {
        uint32_t token, length, nameoff;
        const char *name;
        const unsigned char *nul;
        span(pos,4,end); token=be32(data+pos); pos+=4;
        if (token==1) {
            nul=memchr(data+pos,0,end-pos);
            if (!nul) fail("unterminated node");
            name=(const char *)data+pos; depth++;
            if (depth==1 && !strcmp(name,"memory@40000000")) {
                memories++; memory_depth=depth;
            }
            if (depth==1 && !strcmp(name,"chosen")) chosen_depth=depth;
            pos=align4((size_t)(nul-data)+1);
            if (pos>end) fail("invalid node padding");
        } else if (token==2) {
            if (depth<0) fail("unbalanced nodes");
            if (depth==memory_depth) memory_depth=-1;
            if (depth==chosen_depth) chosen_depth=-1;
            depth--;
        } else if (token==3) {
            span(pos,8,end); length=be32(data+pos); nameoff=be32(data+pos+4); pos+=8;
            span(pos,length,end);
            if (nameoff>=nstrings || !memchr(data+strings+nameoff,0,nstrings-nameoff))
                fail("invalid property name");
            name=(const char *)data+strings+nameoff;
            if (depth==0 && !strcmp(name,"#address-cells") && length==4)
                addr_cells=be32(data+pos);
            if (depth==0 && !strcmp(name,"#size-cells") && length==4)
                size_cells=be32(data+pos);
            if (depth==1 && memory_depth==depth && !strcmp(name,"reg")) {
                if (length!=16) fail("unexpected memory bank");
                if (!memcmp(data+pos,extended,16)) already=1;
                else if (memcmp(data+pos,expected,16)) fail("unexpected memory bank");
                reg=pos; regs++;
            }
            if (depth==1 && chosen_depth==depth && !strcmp(name,"linux,uefi-secure-boot"))
                secure_boot++;
            pos=align4(pos+length);
            if (pos>end) fail("invalid property padding");
        } else if (token==4) {
            continue;
        } else if (token==9) {
            if (depth!=-1) fail("unclosed nodes");
            finished=1; break;
        } else fail("invalid FDT token");
    }
    if (!finished || memories!=1 || regs!=1 || addr_cells!=2 || size_cells!=2)
        fail("unexpected memory layout");
    if (secure_boot) fail("complete EFI handover requires a separate memory-map extension");
    if (already) {
        fprintf(stderr, "percept-upper-ram: memory bank is already 4 GiB; nothing to do\n");
        return 3;
    }
    /* reg = <0 0x40000000 1 0>: [0x40000000, 0x140000000). */
    data[reg+11]=1;
    data[reg+12]=0;
    out=open(argv[2],O_WRONLY|O_CREAT|O_EXCL,0600);
    if (out<0) fail("cannot create output (must not already exist)");
    pos=0;
    while (pos<size) {
        n=write(out,data+pos,size-pos);
        if (n<0 && errno==EINTR) continue;
        if (n<=0) { unlink(argv[2]); fail("output write failed"); }
        pos+=(size_t)n;
    }
    if (fsync(out) || close(out)) { unlink(argv[2]); fail("output flush failed"); }
    printf("percept-upper-ram: extended live DT memory reg at %#zx; 3 GiB -> 4 GiB; all other bytes unchanged\n",reg);
    free(data);
    return 0;
}
