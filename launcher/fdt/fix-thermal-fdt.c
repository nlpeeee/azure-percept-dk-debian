/* SPDX-License-Identifier: GPL-2.0 */
/* Target-only adaptation of the vendor Percept FDT to the Linux 6.12 binding.
 * Build: musl-gcc -std=c99 -O2 -Wall -Wextra -Werror -static -o percept-fdt-thermal fix-thermal-fdt.c
 * No calibration, addresses, phandles, reservations or firmware data are changed.
 */
#define _POSIX_C_SOURCE 200809L
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static void fail(const char *s) { fprintf(stderr, "percept-thermal: %s\n", s); exit(1); }
static uint32_t be32(const unsigned char *p)
{ return (uint32_t)p[0]<<24 | (uint32_t)p[1]<<16 | (uint32_t)p[2]<<8 | p[3]; }
static void span(size_t p, size_t n, size_t end)
{ if (p > end || n > end-p) fail("invalid FDT bounds"); }
static size_t align4(size_t n) { return (n+3)&~(size_t)3; }

int main(int argc, char **argv)
{
    const size_t capacity=2*1024*1024;
    unsigned char *data=malloc(capacity);
    size_t size=0, pos, end, strings, ns, patch=0, pathlen[64];
    char path[4096]="";
    unsigned cells=0, compatible=0, reg=0, little=0, range=0, cal=0;
    unsigned phandle=0, consumer=0, consumer_id=~0U, sensor=0, done=0;
    int depth=-1, in, out;
    ssize_t n;
    const char *tmu="/soc@0/bus@30000000/tmu@30260000";
    const char *zone="/thermal-zones/cpu-thermal";
    static const unsigned char ranges[]={0,0x0b,0,0, 0,0x0a,0,0x26, 0,8,0,0x48, 0,7,0,0x61};
    if (argc!=3) fail("usage: percept-fdt-thermal INPUT OUTPUT");
    if (!data) fail("allocation failed");
    in=open(argv[1], O_RDONLY);
    if (in<0) fail("cannot open input");
    while ((n=read(in,data+size,capacity-size))>0) {
        size+=(size_t)n;
        if (size==capacity) fail("FDT too large");
    }
    if (n<0 || close(in)) fail("input read failed");
    if (size<40 || be32(data)!=0xd00dfeed || be32(data+4)!=size ||
        be32(data+20)!=17 || be32(data+24)>17) fail("unexpected FDT header");
    pos=be32(data+8); strings=be32(data+12); ns=be32(data+32);
    span(pos,be32(data+36),size); end=pos+be32(data+36); span(strings,ns,size);
    while (pos<end) {
        uint32_t token, len, noff;
        const unsigned char *nul;
        const char *name;
        span(pos,4,end); token=be32(data+pos); pos+=4;
        if (token==1) {
            size_t old=strlen(path), extra;
            if (++depth>=64) fail("node nesting too deep");
            nul=memchr(data+pos,0,end-pos);
            if (!nul) fail("unterminated node");
            extra=(size_t)(nul-(data+pos)); pathlen[depth]=old;
            if (depth==0) { if (extra) fail("unexpected root name"); }
            else {
                if (old+1+extra>=sizeof(path)) fail("path too long");
                path[old]='/'; memcpy(path+old+1,data+pos,extra); path[old+1+extra]=0;
            }
            pos=align4((size_t)(nul-data)+1); span(pos,0,end);
        } else if (token==2) {
            if (depth<0) fail("unbalanced nodes");
            path[pathlen[depth--]]=0;
        } else if (token==3) {
            if (depth<0) fail("property outside node");
            span(pos,8,end); len=be32(data+pos); noff=be32(data+pos+4); pos+=8;
            span(pos,len,end);
            if (noff>=ns || !memchr(data+strings+noff,0,ns-noff)) fail("invalid property name");
            name=(const char *)data+strings+noff;
            if (!strcmp(path,tmu)) {
                if (!strcmp(name,"#thermal-sensor-cells")) {
                    if (len!=4 || be32(data+pos)>1) fail("unexpected sensor cells");
                    patch=pos; cells++;
                } else if (!strcmp(name,"compatible")) {
                    if (len!=15 || memcmp(data+pos,"fsl,imx8mq-tmu",15)) fail("unexpected compatible");
                    compatible++;
                } else if (!strcmp(name,"reg")) {
                    if (len!=8 || be32(data+pos)!=0x30260000 || be32(data+pos+4)!=0x10000) fail("unexpected TMU address");
                    reg++;
                } else if (!strcmp(name,"little-endian")) {
                    if (len) fail("unexpected endian property");
                    little++;
                } else if (!strcmp(name,"fsl,tmu-range")) {
                    if (len!=sizeof(ranges) || memcmp(data+pos,ranges,len)) fail("unexpected TMU ranges");
                    range++;
                } else if (!strcmp(name,"fsl,tmu-calibration")) {
                    if (len!=320) fail("unexpected calibration length");
                    cal++;
                } else if (!strcmp(name,"phandle")) {
                    if (len!=4 || phandle) fail("unexpected phandle");
                    phandle=be32(data+pos);
                }
            } else if (!strcmp(path,zone) && !strcmp(name,"thermal-sensors")) {
                if (len!=8) fail("unexpected CPU sensor specifier");
                consumer=be32(data+pos); consumer_id=be32(data+pos+4); sensor++;
            }
            pos=align4(pos+len); span(pos,0,end);
        } else if (token==4) continue;
        else if (token==9) { if (depth!=-1) fail("unbalanced FDT"); done=1; break; }
        else fail("unknown FDT token");
    }
    if (!done || cells!=1 || compatible!=1 || reg!=1 || little!=1 || range!=1 || cal!=1 ||
        !phandle || sensor!=1 || consumer!=phandle || consumer_id!=0) fail("TMU/CPU binding preconditions failed");
    if (be32(data+patch)==1) {
        fprintf(stderr, "percept-thermal: #thermal-sensor-cells is already 1; nothing to do\n");
        return 3;
    }
    data[patch+3]=1;
    out=open(argv[2],O_WRONLY|O_CREAT|O_EXCL,0644);
    if (out<0) fail("cannot create output (must not exist)");
    for (pos=0; pos<size; pos+=(size_t)n) {
        n=write(out,data+pos,size-pos);
        if (n<=0) fail("output write failed");
    }
    if (fsync(out) || close(out)) fail("output flush failed");
    printf("percept-thermal: sensor cells=1 at offset 0x%zx, bytes=%zu; all other bytes preserved\n",patch,size);
    free(data);
    return 0;
}
