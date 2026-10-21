/* SPDX-License-Identifier: GPL-2.0 */
/* Target-only i.MX8MQ media adaptation; uses each bootstrap's fresh FDT. */
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <libfdt.h>

static void die(const char *s) { fprintf(stderr,"percept-media: %s\n",s); exit(1); }
static void check(int e) { if (e<0) die(fdt_strerror(e)); }
static int node(const void *f,const char *p)
{ int n=fdt_path_offset(f,p); check(n); return n; }
static void cells(const void *f,const char *p,const char *key,const uint32_t *want,int count)
{
    int len; const fdt32_t *v=fdt_getprop(f,node(f,p),key,&len);
    if (!v || len!=count*4) die(key);
    for (int i=0;i<count;i++) if (fdt32_to_cpu(v[i])!=want[i]) die(key);
}
static void string(const void *f,const char *p,const char *key,const char *want,int bytes)
{
    int len; const void *v=fdt_getprop(f,node(f,p),key,&len);
    if (!v || len!=bytes || memcmp(v,want,(size_t)bytes)) die(key);
}
static uint32_t phandle(const void *f,const char *p)
{ uint32_t ph=fdt_get_phandle(f,node(f,p)); if (!ph) die("missing phandle"); return ph; }
static void setcells(void *f,const char *p,const char *key,const uint32_t *v,int count)
{
    fdt32_t be[32];
    if (count>32) die("cell array too large");
    for(int i=0;i<count;i++) be[i]=cpu_to_fdt32(v[i]);
    check(fdt_setprop(f,node(f,p),key,be,count*4));
}
static void setstring(void *f,const char *p,const char *key,const char *s)
{ check(fdt_setprop_string(f,node(f,p),key,s)); }

static void gpu(void *f)
{
    const char *p="/soc@0/gpu@38000000", *old="/gpu3d@38000000";
    const char *ccm="/soc@0/bus@30000000/clock-controller@30380000";
    const char *gpc="/soc@0/bus@30000000/gpc@303a0000";
    const char *domain="/soc@0/bus@30000000/gpc@303a0000/pgc/power-domain@5";
    uint32_t clk=phandle(f,ccm), pd=phandle(f,domain);
    uint32_t reg[]={0x38000000,0x40000}, irq[]={0,3,4};
    uint32_t clocks[]={clk,215,clk,102,clk,111,clk,112};
    uint32_t assigned[]={clk,97,clk,100,clk,111,clk,112,clk,16};
    uint32_t parents[]={clk,17,clk,17,clk,17,clk,17,clk,15};
    uint32_t rates[]={800000000,800000000,800000000,400000000,0};
    uint32_t five=5, zero=0, one=1;
    string(f,p,"compatible","vivante,gc",sizeof("vivante,gc"));
    string(f,old,"compatible","fsl,imx8mq-gpu\0fsl,imx6q-gpu",sizeof("fsl,imx8mq-gpu\0fsl,imx6q-gpu"));
    string(f,gpc,"compatible","fsl,imx8mq-gpc",sizeof("fsl,imx8mq-gpc"));
    string(f,ccm,"compatible","fsl,imx8mq-ccm",sizeof("fsl,imx8mq-ccm"));
    cells(f,"/soc@0","#address-cells",&one,1);
    cells(f,"/soc@0","#size-cells",&one,1);
    cells(f,domain,"reg",&five,1); cells(f,domain,"#power-domain-cells",&zero,1);
    cells(f,p,"reg",reg,2); cells(f,p,"interrupts",irq,3);
    cells(f,p,"clocks",clocks,8); cells(f,p,"assigned-clocks",assigned,10);
    cells(f,p,"assigned-clock-parents",parents,10); cells(f,p,"power-domains",&pd,1);
    string(f,p,"clock-names","core\0shader\0bus\0reg",sizeof("core\0shader\0bus\0reg"));
    setstring(f,old,"status","disabled");
    setcells(f,p,"assigned-clock-rates",rates,5);
    setstring(f,p,"status","okay");
    puts("percept-media: mainline GPU enabled, vendor duplicate disabled, GPU AHB=400MHz");
}

static void addnode(void *f,const char *name)
{
    char path[128]; snprintf(path,sizeof(path),"/soc@0/%s",name);
    if(fdt_path_offset(f,path)!=-FDT_ERR_NOTFOUND) die("media node already exists");
    check(fdt_add_subnode(f,node(f,"/soc@0"),name));
}

static void vpu(void *f)
{
    const char *old="/soc@0/vpu@38300000";
    const char *bc="/soc@0/blk-ctrl@38320000";
    const char *g1="/soc@0/video-codec@38300000", *g2="/soc@0/video-codec@38310000";
    const char *domain="/soc@0/bus@30000000/gpc@303a0000/pgc/power-domain@6";
    uint32_t clk=phandle(f,"/soc@0/bus@30000000/clock-controller@30380000");
    uint32_t pd=phandle(f,domain), six=6, zero=0, one=1, ph;
    uint32_t oldreg[]={0x38300000,0x200000}, oldirq[]={0,7,4,0,8,4};
    uint32_t clocks[]={clk,229,clk,230,clk,223};
    uint32_t assigned[]={clk,120,clk,121,clk,106};
    uint32_t parents[]={clk,22,clk,22,clk,78};
    uint32_t rates[]={600000000,600000000,800000000};
    uint32_t regbc[]={0x38320000,0x100}, reg1[]={0x38300000,0x10000}, reg2[]={0x38310000,0x10000};
    uint32_t irq1[]={0,7,4}, irq2[]={0,8,4}, domains[]={pd,pd,pd};
    uint32_t power1[2],power2[2];
    /* Exactly the v6.12.113 imx8mq.dtsi pgc_vpu node. The vendor VPU domain has
     * neither property; without its clocks the GPC power-up sequence cannot
     * propagate reset into G1/G2 (gpcv2.c enables domain->clks for that, and the
     * VPU domain keeps them), so the first hantro register access hangs the bus
     * and the board resets silently. G2 is 300 MHz upstream, not the vendor 600. */
    uint32_t dclocks[]={clk,223,clk,229,clk,230};
    uint32_t dassigned[]={clk,120,clk,121,clk,106,clk,21};   /* G1 G2 BUS VPU_PLL_BYPASS */
    uint32_t dparents[]={clk,22,clk,22,clk,78,clk,20};       /* PLL_OUT PLL_OUT SYS1_800M VPU_PLL */
    uint32_t drates[]={600000000,300000000,800000000,0};
    string(f,old,"compatible","nxp,imx8mq-hantro",sizeof("nxp,imx8mq-hantro"));
    cells(f,old,"reg",oldreg,2); cells(f,old,"interrupts",oldirq,6);
    cells(f,old,"clocks",clocks,6); cells(f,old,"power-domains",&pd,1);
    cells(f,old,"assigned-clocks",assigned,6); cells(f,old,"assigned-clock-parents",parents,6);
    cells(f,old,"assigned-clock-rates",rates,3);
    cells(f,domain,"reg",&six,1); cells(f,domain,"#power-domain-cells",&zero,1);
    check(fdt_generate_phandle(f,&ph));
    setstring(f,old,"status","disabled");
    addnode(f,"blk-ctrl@38320000");
    setstring(f,bc,"compatible","fsl,imx8mq-vpu-blk-ctrl");
    setcells(f,bc,"reg",regbc,2); setcells(f,bc,"power-domains",domains,3);
    check(fdt_setprop(f,node(f,bc),"power-domain-names","bus\0g1\0g2",sizeof("bus\0g1\0g2")));
    setcells(f,bc,"clocks",clocks,4);
    check(fdt_setprop(f,node(f,bc),"clock-names","g1\0g2",sizeof("g1\0g2")));
    setcells(f,bc,"#power-domain-cells",&one,1); setcells(f,bc,"phandle",&ph,1);
    /* Clock ownership follows mainline: the PGC domain node carries the clocks
     * and the assigned parents/rates, not the block controller. */
    setcells(f,domain,"clocks",dclocks,6);
    setcells(f,domain,"assigned-clocks",dassigned,8);
    setcells(f,domain,"assigned-clock-parents",dparents,8);
    setcells(f,domain,"assigned-clock-rates",drates,4);
    power1[0]=ph; power1[1]=0; power2[0]=ph; power2[1]=1;
    addnode(f,"video-codec@38300000");
    setstring(f,g1,"compatible","nxp,imx8mq-vpu-g1"); setcells(f,g1,"reg",reg1,2);
    setcells(f,g1,"interrupts",irq1,3); setcells(f,g1,"clocks",clocks,2);
    setcells(f,g1,"power-domains",power1,2);
    addnode(f,"video-codec@38310000");
    setstring(f,g2,"compatible","nxp,imx8mq-vpu-g2"); setcells(f,g2,"reg",reg2,2);
    setcells(f,g2,"interrupts",irq2,3); setcells(f,g2,"clocks",clocks+2,2);
    setcells(f,g2,"power-domains",power2,2);
    printf("percept-media: mainline G1/G2 and shared block controller added, phandle=%u\n",ph);
}

int main(int argc,char **argv)
{
    unsigned char *input, *out;
    const size_t max=2*1024*1024;
    size_t len=0, pos=0; ssize_t n;
    int fd, output;
    if (argc!=4 || (strcmp(argv[3],"gpu") && strcmp(argv[3],"gpu-vpu")))
        die("usage: percept-fdt-media INPUT OUTPUT gpu|gpu-vpu");
    input=malloc(max); out=malloc(max+65536);
    if (!input || !out) die("allocation failed");
    fd=open(argv[1],O_RDONLY); if(fd<0) die("cannot open input");
    while ((n=read(fd,input+len,max-len))>0) {
        len+=(size_t)n; if(len==max) die("input too large");
    }
    if(n<0 || close(fd)) die("input read failed");
    check(fdt_check_full(input,len));
    if (fdt_totalsize(input)!=len) die("unexpected input size");
    check(fdt_open_into(input,out,(int)(max+65536)));
    gpu(out);
    if (!strcmp(argv[3],"gpu-vpu")) vpu(out);
    check(fdt_pack(out)); check(fdt_check_full(out,fdt_totalsize(out)));
    output=open(argv[2],O_WRONLY|O_CREAT|O_EXCL,0644);
    if(output<0) die("cannot create output (must not exist)");
    while(pos<fdt_totalsize(out)) {
        n=write(output,out+pos,fdt_totalsize(out)-pos);
        if(n<=0) die("output write failed");
        pos+=(size_t)n;
    }
    if(fsync(output) || close(output)) die("output flush failed");
    printf("percept-media: input=%zu output=%u bytes\n",len,fdt_totalsize(out));
    free(input); free(out); return 0;
}
