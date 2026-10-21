# SPDX-License-Identifier: MIT
"""Compose sparse GPT disks from filesystem images without loop devices."""
import os
from pathlib import Path
import struct
import uuid
import zlib
ESP_TYPE='c12a7328-f81f-11d2-ba4b-00a0c93ec93b'
LINUX_TYPE='0fc63daf-8483-4772-8e79-3d69d8477de4'
def align(n,unit=2048):return (n+unit-1)//unit*unit
def layout(root_bytes):
    start=120832
    second=align(start+64*2048)
    root=align(second+22528)
    size=align((root_bytes+511)//512)
    return {'sectors':align(root+size+34),'partitions':[
        {'start':start,'size':64*2048,'type':ESP_TYPE,'name':'percept-efi'},
        {'start':second,'size':22528,'type':ESP_TYPE,'name':'factory-efi-b'},
        {'start':root,'size':size,'type':LINUX_TYPE,'name':'debian'}]}
def _header(current,backup,entries_lba,sectors,guid,entries):
    head=struct.pack('<8sIIIIQQQQ16sQIII',b'EFI PART',0x10000,92,0,0,current,backup,
        34,sectors-34,guid.bytes_le,entries_lba,128,128,zlib.crc32(entries))
    return (head[:16]+struct.pack('<I',zlib.crc32(head))+head[20:]).ljust(512,b'\0')
def sparse_copy(source,destination,offset):
    with open(source,'rb') as src:
        size=os.fstat(src.fileno()).st_size;pos=0
        while pos<size:
            try:
                if not hasattr(os,'SEEK_DATA'):raise OSError(22,'extent lookup unavailable')
                data=os.lseek(src.fileno(),pos,os.SEEK_DATA)
                end=min(os.lseek(src.fileno(),data,os.SEEK_HOLE),size)
            except OSError as exc:
                if exc.errno==6:break
                data,end=pos,size
            src.seek(data);destination.seek(offset+data);remaining=end-data
            while remaining:
                block=src.read(min(1024*1024,remaining))
                if not block:raise ValueError('short image read')
                destination.write(block);remaining-=len(block)
            pos=end
def compose(output,esp,secondary,rootfs,prefix,disk_guid=None):
    output=Path(output)
    if output.exists():raise ValueError('refusing to overwrite disk image')
    spec=layout(Path(rootfs).stat().st_size)
    guid=uuid.UUID(str(disk_guid)) if disk_guid else uuid.uuid4()
    entries=bytearray(128*128)
    for i,p in enumerate(spec['partitions']):
        p['uuid']=['e04e7fa1-a30b-4713-95a8-aa82b69c3b38','0eb735c2-1253-4e96-b5e2-dde17c145e5c',str(uuid.uuid4())][i]
        entries[i*128:(i+1)*128]=struct.pack('<16s16sQQQ72s',uuid.UUID(p['type']).bytes_le,
            uuid.UUID(p['uuid']).bytes_le,p['start'],p['start']+p['size']-1,0,
            p['name'].encode('utf-16-le').ljust(72,b'\0'))
    entries=bytes(entries)
    with output.open('xb') as dst:
        dst.truncate(spec['sectors']*512)
        if prefix:sparse_copy(prefix,dst,0)
        for p,src in zip(spec['partitions'],(esp,secondary,rootfs)):
            if Path(src).stat().st_size>p['size']*512:raise ValueError('partition image too large')
            sparse_copy(src,dst,p['start']*512)
        mbr=bytearray(512)
        mbr[446:462]=struct.pack('<B3sB3sII',0,b'\0\x02\0',0xee,b'\xff'*3,1,min(spec['sectors']-1,0xffffffff))
        mbr[510:512]=b'\x55\xaa'
        dst.seek(0);dst.write(mbr)
        dst.seek(512);dst.write(_header(1,spec['sectors']-1,2,spec['sectors'],guid,entries))
        dst.seek(1024);dst.write(entries)
        dst.seek((spec['sectors']-33)*512);dst.write(entries)
        dst.seek((spec['sectors']-1)*512);dst.write(_header(spec['sectors']-1,1,spec['sectors']-33,spec['sectors'],guid,entries))
    spec['disk_guid']=str(guid)
    return spec
