/* SPDX-License-Identifier: GPL-2.0-only */
/* Target-only i.MX8MQ CPU OPP adaptation; uses each bootstrap's fresh FDT. */
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <libfdt.h>

static void die(const char *s) { fprintf(stderr,"percept-cpu: %s\n",s); exit(1); }
static void check(int e) { if (e<0) die(fdt_strerror(e)); }
static int node(const void *f,const char *p)
{ int n=fdt_path_offset(f,p); check(n); return n; }
static void cells(const void *f,const char *p,const char *key,const uint32_t *want,int count)
{
    int len; const fdt32_t *v=fdt_getprop(f,node(f,p),key,&len);
    if (!v || len!=count*4) die(key);
    for (int i=0;i<count;i++) if (fdt32_to_cpu(v[i])!=want[i]) die(key);
}

static void adapt(void *f,const char *profile)
{
    static const uint32_t hz[]={800000000,1000000000,1300000000,1500000000};
    static const uint32_t uv[]={900000,900000,1000000,1000000};
    static const uint32_t masks[][2]={{15,4},{14,3},{12,4},{8,3}};
    int table=node(f,"/opp-table"), child, count=0;
    int bytes; const char *compat=fdt_getprop(f,table,"compatible",&bytes);
    if(!compat || bytes!=(int)sizeof("operating-points-v2") || memcmp(compat,"operating-points-v2",bytes)) die("OPP compatible");
    fdt_for_each_subnode(child,f,table) count++;
    if(count!=4) die("unexpected OPP count");
    for(int i=0;i<4;i++) {
        char path[96]; uint32_t freq[]={0,hz[i]}, latency=150000;
        snprintf(path,sizeof(path),"/opp-table/opp-%u",hz[i]);
        cells(f,path,"opp-hz",freq,2);
        cells(f,path,"opp-microvolt",&uv[i],1);
        cells(f,path,"opp-supported-hw",masks[i],2);
        cells(f,path,"clock-latency-ns",&latency,1);
        int n=node(f,path), off, props=0;
        const void *suspend=fdt_getprop(f,n,"opp-suspend",&bytes);
        if(!suspend || bytes) die("opp-suspend");
        fdt_for_each_property_offset(off,f,n) props++;
        if(props!=5) die("unexpected OPP property");
    }
    /* No OPP deletion, no clock/voltage/regulator changes. Fuse filtering stays. */
    if(!strcmp(profile,"oc1500")) {
        fdt32_t mask[]={cpu_to_fdt32(4),cpu_to_fdt32(4)};
        check(fdt_setprop_inplace(f,node(f,"/opp-table/opp-1500000000"),"opp-supported-hw",mask,sizeof(mask)));
    }
    printf("percept-cpu: profile=%s 1500_original_mask=8,3 voltage_max=1000000\n",profile);
}
int main(int argc,char **argv)
{
    unsigned char *input, *out;
    const size_t max=2*1024*1024;
    size_t len=0, pos=0; ssize_t n;
    int fd, output;
    if (argc!=4 || (strcmp(argv[3],"rated") && strcmp(argv[3],"oc1500")))
        die("usage: percept-fdt-cpu INPUT OUTPUT rated|oc1500");
    input=malloc(max); out=malloc(max+65536);
    if (!input || !out) die("allocation failed");
    fd=open(argv[1],O_RDONLY); if(fd<0) die("cannot open input");
    while ((n=read(fd,input+len,max-len))>0) {
        len+=(size_t)n; if(len==max) die("input too large");
    }
    if(n<0 || close(fd)) die("input read failed");
    check(fdt_check_full(input,len));
    if (fdt_totalsize(input)!=len) die("unexpected input size");
    memcpy(out,input,len);
    adapt(out,argv[3]); check(fdt_check_full(out,fdt_totalsize(out)));
    output=open(argv[2],O_WRONLY|O_CREAT|O_EXCL,0644);
    if(output<0) die("cannot create output (must not exist)");
    while(pos<fdt_totalsize(out)) {
        n=write(output,out+pos,fdt_totalsize(out)-pos);
        if(n<=0) die("output write failed");
        pos+=(size_t)n;
    }
    if(fsync(output) || close(output)) die("output flush failed");
    printf("percept-cpu: input=%zu output=%u bytes\n",len,fdt_totalsize(out));
    free(input); free(out); return 0;
}
