/* SPDX-License-Identifier: GPL-2.0-only */
#define _POSIX_C_SOURCE 200809L
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <libfdt.h>
static void die(const char *s) { fprintf(stderr,"percept-pmic: %s\n",s);exit(1); }
static void check(int r) { if(r<0) die(fdt_strerror(r)); }
static int node(const void *f,const char *p) { int n=fdt_path_offset(f,p);check(n);return n; }
static void exact(const void *f,const char *p,const char *key,const unsigned char *b,int len) {
 int n;const void *v=fdt_getprop(f,node(f,p),key,&n);
 if(!v || n!=len || memcmp(v,b,(size_t)len)) die(key);
}
static void propcount(const void *f,const char *p,int want) {
 int off,count=0; fdt_for_each_property_offset(off,f,node(f,p)) count++;
 if(count!=want) die("unexpected properties");
}
static void setcells(void *f,const char *p,const char *key,const uint32_t *v,int count) {
 fdt32_t b[8];if(count>8)die("cells");
 for(int i=0;i<count;i++)b[i]=cpu_to_fdt32(v[i]);
 check(fdt_setprop(f,node(f,p),key,b,count*4));
}
static void flag(void *f,const char *p,const char *key) { check(fdt_setprop(f,node(f,p),key,NULL,0)); }
static void string(void *f,const char *p,const char *key,const char *s) {check(fdt_setprop_string(f,node(f,p),key,s));}
static void del(void *f,const char *p,const char *key) {check(fdt_delprop(f,node(f,p),key));}
static void guards(const void *f) {
 exact(f,"/soc@0/bus@30000000/gpio@30200000","compatible",(const unsigned char *)"fsl,imx8mq-gpio\0fsl,imx35-gpio",31);
 exact(f,"/soc@0/bus@30000000/gpio@30200000","#interrupt-cells",(const unsigned char *)"\x00\x00\x00\x02",4);
 exact(f,"/soc@0/bus@30000000/gpio@30200000","interrupt-controller",(const unsigned char *)"",0);
 exact(f,"/soc@0/bus@30000000/gpio@30200000","phandle",(const unsigned char *)"\x00\x00\x00\x2e",4);
 exact(f,"/soc@0/bus@30000000/iomuxc@30330000/pmicirq","phandle",(const unsigned char *)"\x00\x00\x00\x2d",4);
 exact(f,"/soc@0/bus@30000000/iomuxc@30330000/pmicirq","fsl,pins",(const unsigned char *)"\x00\x00\x00\x44\x00\x00\x02\xac\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x41",24);
 propcount(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b",4);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b","reg",(const unsigned char *)"\x00\x00\x00\x4b",4);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b","compatible",(const unsigned char *)"\x72\x6f\x68\x6d\x2c\x62\x64\x37\x31\x38\x34\x30\x00\x72\x6f\x68\x6d\x2c\x62\x64\x37\x31\x38\x33\x37\x00",26);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b","pinctrl-0",(const unsigned char *)"\x00\x00\x00\x2d",4);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b","gpio_intr",(const unsigned char *)"\x00\x00\x00\x2e\x00\x00\x00\x07\x00\x00\x00\x01",12);
 propcount(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/gpo",1);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/gpo","rohm,drv",(const unsigned char *)"\x00\x00\x00\x0c",4);
 propcount(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators",4);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators","#address-cells",(const unsigned char *)"\x00\x00\x00\x01",4);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators","#size-cells",(const unsigned char *)"\x00\x00\x00\x00",4);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators","bd71837,pmic-buck2-uses-i2c-dvs",(const unsigned char *)"",0);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators","bd71837,pmic-buck2-dvs-voltage",(const unsigned char *)"\x00\x0f\x42\x40\x00\x0d\xbb\xa0\x00\x00\x00\x00",12);
 propcount(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@0",7);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@0","reg",(const unsigned char *)"\x00\x00\x00\x00",4);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@0","regulator-compatible",(const unsigned char *)"\x62\x75\x63\x6b\x31\x00",6);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@0","regulator-min-microvolt",(const unsigned char *)"\x00\x0a\xae\x60",4);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@0","regulator-max-microvolt",(const unsigned char *)"\x00\x13\xd6\x20",4);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@0","regulator-boot-on",(const unsigned char *)"",0);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@0","regulator-always-on",(const unsigned char *)"",0);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@0","regulator-ramp-delay",(const unsigned char *)"\x00\x00\x04\xe2",4);
 propcount(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@1",7);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@1","reg",(const unsigned char *)"\x00\x00\x00\x01",4);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@1","regulator-compatible",(const unsigned char *)"\x62\x75\x63\x6b\x32\x00",6);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@1","regulator-min-microvolt",(const unsigned char *)"\x00\x0d\xbb\xa0",4);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@1","regulator-max-microvolt",(const unsigned char *)"\x00\x0f\x42\x40",4);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@1","regulator-boot-on",(const unsigned char *)"",0);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@1","regulator-always-on",(const unsigned char *)"",0);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@1","phandle",(const unsigned char *)"\x00\x00\x00\x07",4);
 propcount(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@2",4);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@2","reg",(const unsigned char *)"\x00\x00\x00\x02",4);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@2","regulator-compatible",(const unsigned char *)"\x62\x75\x63\x6b\x33\x00",6);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@2","regulator-min-microvolt",(const unsigned char *)"\x00\x0a\xae\x60",4);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@2","regulator-max-microvolt",(const unsigned char *)"\x00\x13\xd6\x20",4);
 propcount(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@3",4);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@3","reg",(const unsigned char *)"\x00\x00\x00\x03",4);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@3","regulator-compatible",(const unsigned char *)"\x62\x75\x63\x6b\x34\x00",6);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@3","regulator-min-microvolt",(const unsigned char *)"\x00\x0a\xae\x60",4);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@3","regulator-max-microvolt",(const unsigned char *)"\x00\x13\xd6\x20",4);
 propcount(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@4",6);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@4","reg",(const unsigned char *)"\x00\x00\x00\x04",4);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@4","regulator-compatible",(const unsigned char *)"\x62\x75\x63\x6b\x35\x00",6);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@4","regulator-min-microvolt",(const unsigned char *)"\x00\x0a\xae\x60",4);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@4","regulator-max-microvolt",(const unsigned char *)"\x00\x14\x99\x70",4);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@4","regulator-boot-on",(const unsigned char *)"",0);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@4","regulator-always-on",(const unsigned char *)"",0);
 propcount(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@5",6);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@5","reg",(const unsigned char *)"\x00\x00\x00\x05",4);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@5","regulator-compatible",(const unsigned char *)"\x62\x75\x63\x6b\x36\x00",6);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@5","regulator-min-microvolt",(const unsigned char *)"\x00\x2d\xc6\xc0",4);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@5","regulator-max-microvolt",(const unsigned char *)"\x00\x32\x5a\xa0",4);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@5","regulator-boot-on",(const unsigned char *)"",0);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@5","regulator-always-on",(const unsigned char *)"",0);
 propcount(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@6",6);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@6","reg",(const unsigned char *)"\x00\x00\x00\x06",4);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@6","regulator-compatible",(const unsigned char *)"\x62\x75\x63\x6b\x37\x00",6);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@6","regulator-min-microvolt",(const unsigned char *)"\x00\x18\x7d\x88",4);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@6","regulator-max-microvolt",(const unsigned char *)"\x00\x1e\x70\xf8",4);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@6","regulator-boot-on",(const unsigned char *)"",0);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@6","regulator-always-on",(const unsigned char *)"",0);
 propcount(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@7",6);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@7","reg",(const unsigned char *)"\x00\x00\x00\x07",4);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@7","regulator-compatible",(const unsigned char *)"\x62\x75\x63\x6b\x38\x00",6);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@7","regulator-min-microvolt",(const unsigned char *)"\x00\x0c\x35\x00",4);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@7","regulator-max-microvolt",(const unsigned char *)"\x00\x15\x5c\xc0",4);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@7","regulator-boot-on",(const unsigned char *)"",0);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@7","regulator-always-on",(const unsigned char *)"",0);
 propcount(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@8",6);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@8","reg",(const unsigned char *)"\x00\x00\x00\x08",4);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@8","regulator-compatible",(const unsigned char *)"\x6c\x64\x6f\x31\x00",5);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@8","regulator-min-microvolt",(const unsigned char *)"\x00\x2d\xc6\xc0",4);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@8","regulator-max-microvolt",(const unsigned char *)"\x00\x32\x5a\xa0",4);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@8","regulator-boot-on",(const unsigned char *)"",0);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@8","regulator-always-on",(const unsigned char *)"",0);
 propcount(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@9",6);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@9","reg",(const unsigned char *)"\x00\x00\x00\x09",4);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@9","regulator-compatible",(const unsigned char *)"\x6c\x64\x6f\x32\x00",5);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@9","regulator-min-microvolt",(const unsigned char *)"\x00\x0d\xbb\xa0",4);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@9","regulator-max-microvolt",(const unsigned char *)"\x00\x0d\xbb\xa0",4);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@9","regulator-boot-on",(const unsigned char *)"",0);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@9","regulator-always-on",(const unsigned char *)"",0);
 propcount(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@10",6);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@10","reg",(const unsigned char *)"\x00\x00\x00\x0a",4);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@10","regulator-compatible",(const unsigned char *)"\x6c\x64\x6f\x33\x00",5);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@10","regulator-min-microvolt",(const unsigned char *)"\x00\x1b\x77\x40",4);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@10","regulator-max-microvolt",(const unsigned char *)"\x00\x32\x5a\xa0",4);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@10","regulator-boot-on",(const unsigned char *)"",0);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@10","regulator-always-on",(const unsigned char *)"",0);
 propcount(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@11",6);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@11","reg",(const unsigned char *)"\x00\x00\x00\x0b",4);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@11","regulator-compatible",(const unsigned char *)"\x6c\x64\x6f\x34\x00",5);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@11","regulator-min-microvolt",(const unsigned char *)"\x00\x0d\xbb\xa0",4);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@11","regulator-max-microvolt",(const unsigned char *)"\x00\x1b\x77\x40",4);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@11","regulator-boot-on",(const unsigned char *)"",0);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@11","regulator-always-on",(const unsigned char *)"",0);
 propcount(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@13",6);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@13","reg",(const unsigned char *)"\x00\x00\x00\x0d",4);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@13","regulator-compatible",(const unsigned char *)"\x6c\x64\x6f\x36\x00",5);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@13","regulator-min-microvolt",(const unsigned char *)"\x00\x0d\xbb\xa0",4);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@13","regulator-max-microvolt",(const unsigned char *)"\x00\x1b\x77\x40",4);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@13","regulator-boot-on",(const unsigned char *)"",0);
 exact(f,"/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators/regulator@13","regulator-always-on",(const unsigned char *)"",0);
 propcount(f,"/regulator-buck2",9);
 exact(f,"/regulator-buck2","pinctrl-names",(const unsigned char *)"\x64\x65\x66\x61\x75\x6c\x74\x00",8);
 exact(f,"/regulator-buck2","pinctrl-0",(const unsigned char *)"\x00\x00\x00\x5f",4);
 exact(f,"/regulator-buck2","compatible",(const unsigned char *)"\x72\x65\x67\x75\x6c\x61\x74\x6f\x72\x2d\x67\x70\x69\x6f\x00",15);
 exact(f,"/regulator-buck2","regulator-name",(const unsigned char *)"\x76\x64\x64\x5f\x61\x72\x6d\x00",8);
 exact(f,"/regulator-buck2","regulator-min-microvolt",(const unsigned char *)"\x00\x0d\xbb\xa0",4);
 exact(f,"/regulator-buck2","regulator-max-microvolt",(const unsigned char *)"\x00\x0f\x42\x40",4);
 exact(f,"/regulator-buck2","gpios",(const unsigned char *)"\x00\x00\x00\x2e\x00\x00\x00\x0d\x00\x00\x00\x00",12);
 exact(f,"/regulator-buck2","states",(const unsigned char *)"\x00\x0f\x42\x40\x00\x00\x00\x00\x00\x0d\xbb\xa0\x00\x00\x00\x01",16);
 exact(f,"/regulator-buck2","phandle",(const unsigned char *)"\x00\x00\x00\x5e",4);
 exact(f,"/cpus/cpu@0","cpu-supply",(const unsigned char *)"\x00\x00\x00\x5e",4);
 exact(f,"/cpus/cpu@1","cpu-supply",(const unsigned char *)"\x00\x00\x00\x5e",4);
 exact(f,"/cpus/cpu@2","cpu-supply",(const unsigned char *)"\x00\x00\x00\x5e",4);
 exact(f,"/cpus/cpu@3","cpu-supply",(const unsigned char *)"\x00\x00\x00\x5e",4);
}
static void adapt(void *f) {
 const char *pmic="/soc@0/bus@30800000/i2c@30a20000/bd71837@4b";
 const char *regs="/soc@0/bus@30800000/i2c@30a20000/bd71837@4b/regulators";
 char old[256],p[256];int child,count=0;
 guards(f);
 fdt_for_each_subnode(child,f,node(f,regs))count++;
 if(count!=13)die("unexpected rail count");
 del(f,pmic,"gpio_intr");
 uint32_t gpio=0x2e,irq[]={7,8};
 setcells(f,pmic,"interrupt-parent",&gpio,1);
 setcells(f,pmic,"interrupts",irq,2);
 string(f,pmic,"pinctrl-names","default");
 flag(f,pmic,"rohm,reset-snvs-powered");
 del(f,regs,"#address-cells");del(f,regs,"#size-cells");
 del(f,regs,"bd71837,pmic-buck2-uses-i2c-dvs");
 del(f,regs,"bd71837,pmic-buck2-dvs-voltage");
 for(int i=0;i<15;i++) {
  snprintf(p,sizeof(p),"%s/%s%d",regs,i<8?"BUCK":"LDO",i<8?i+1:i-7);
  if(i==12 || i==14) {
   if(fdt_path_offset(f,p)!=-FDT_ERR_NOTFOUND)die("rail exists");
   char name[16];snprintf(name,sizeof(name),"LDO%d",i-7);
   check(fdt_add_subnode(f,node(f,regs),name));
  } else {
   snprintf(old,sizeof(old),"%s/regulator@%d",regs,i);
   char name[16];snprintf(name,sizeof(name),"%s%d",i<8?"BUCK":"LDO",i<8?i+1:i-7);
   check(fdt_set_name(f,node(f,old),name));
   del(f,p,"reg");del(f,p,"regulator-compatible");
  }
  flag(f,p,"rohm,no-regulator-enable-control");
 }
 snprintf(p,sizeof(p),"%s/BUCK1",regs);del(f,p,"regulator-ramp-delay");
 snprintf(p,sizeof(p),"%s/BUCK2",regs);uint32_t ramp=5000;
 setcells(f,p,"regulator-ramp-delay",&ramp,1);
 string(f,"/regulator-buck2","status","disabled");
 uint32_t supply=7;
 for(int i=0;i<4;i++) {snprintf(p,sizeof(p),"/cpus/cpu@%d",i);setcells(f,p,"cpu-supply",&supply,1);}
 puts("percept-pmic: single BUCK2 owner; existing DVS slots unchanged; 0x24 monitor mask 00->30 intentional");
}
int main(int argc,char **argv)
{
    unsigned char *input, *out;
    const size_t max=2*1024*1024;
    size_t len=0, pos=0; ssize_t n;
    int fd, output;
    if (argc!=3)
        die("usage: percept-fdt-pmic INPUT OUTPUT");
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
    adapt(out); check(fdt_pack(out)); check(fdt_check_full(out,fdt_totalsize(out)));
    output=open(argv[2],O_WRONLY|O_CREAT|O_EXCL,0644);
    if(output<0) die("cannot create output (must not exist)");
    while(pos<fdt_totalsize(out)) {
        n=write(output,out+pos,fdt_totalsize(out)-pos);
        if(n<=0) die("output write failed");
        pos+=(size_t)n;
    }
    if(fsync(output) || close(output)) die("output flush failed");
    printf("percept-pmic: input=%zu output=%u bytes\n",len,fdt_totalsize(out));
    free(input); free(out); return 0;
}
