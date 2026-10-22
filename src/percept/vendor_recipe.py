# SPDX-License-Identifier: MIT
"""Portable, bounded extraction from the one hash-pinned Microsoft ZIP.

The recipe contains offsets and hashes, never vendor bytes. It is generated
from the pinned ZIP and compared with the existing Linux extractor's outputs.
"""
import hashlib
import json
from pathlib import Path
import shutil
import struct
import tempfile
import zipfile
from .build.pipeline import sha

FILES = {'Image', 'pe100.dtb', 'bootaa64.efi', 'grubaa64.efi',
         'platform-prefix.bin', 'secondary-esp.img', 'fast-hab-fw.raw', 'emmc_full.txt'}


def read_at(stream, offset, length):
    stream.seek(offset)
    value = stream.read(length)
    if len(value) != length: raise ValueError('truncated vendor image')
    return value


def ext4_file(stream, base, path):
    """Read extents for regular ext4 files and directories; reject unknown layouts."""
    sb = read_at(stream, base+1024, 1024)
    if struct.unpack_from('<H', sb, 56)[0] != 0xef53: raise ValueError('not ext4')
    block = 1024 << struct.unpack_from('<I', sb, 24)[0]
    per_group = struct.unpack_from('<I', sb, 40)[0]
    inode_size = struct.unpack_from('<H', sb, 88)[0]
    desc_size = max(32, struct.unpack_from('<H', sb, 254)[0])
    desc_base = base + (2 if block == 1024 else 1)*block

    def inode(number):
        group, index = divmod(number-1, per_group)
        desc = read_at(stream, desc_base+group*desc_size, desc_size)
        table = struct.unpack_from('<I', desc, 8)[0]
        if desc_size >= 64: table |= struct.unpack_from('<I', desc, 40)[0] << 32
        return read_at(stream, base+table*block+index*inode_size, inode_size)

    def extents(node, depth_limit=6):
        magic, entries, maximum, depth = struct.unpack_from('<HHHH', node)
        if magic != 0xf30a or entries > maximum or depth > depth_limit:
            raise ValueError('unsupported ext4 extent tree')
        result = []
        for n in range(entries):
            entry = 12+n*12
            logical = struct.unpack_from('<I', node, entry)[0]
            if depth:
                lo, hi = struct.unpack_from('<IH', node, entry+4)
                result += extents(read_at(stream, base+((hi << 32)|lo)*block, block), depth-1)
            else:
                length, hi, lo = struct.unpack_from('<HHI', node, entry+4)
                if length > 32768: raise ValueError('uninitialized vendor extents')
                result.append((logical*block, base+((hi << 32)|lo)*block, length*block))
        return sorted(result)

    def data(number):
        node = inode(number)
        size = struct.unpack_from('<I', node, 4)[0]
        if struct.unpack_from('<H', node)[0] & 0xf000 == 0xa000 and size <= 60:
            return node, node[40:40+size], []
        if not struct.unpack_from('<I', node, 32)[0] & 0x80000:
            raise ValueError('vendor file does not use extents')
        ranges = []; cursor = 0
        for logical, offset, length in extents(node[40:100]):
            if logical != cursor: raise ValueError('sparse vendor file not supported')
            length = min(length, size-cursor)
            if length <= 0: break
            ranges.append([offset, length]); cursor += length
        if cursor != size: raise ValueError('incomplete ext4 extents')
        value = b''.join(read_at(stream, offset, length) for offset, length in ranges)
        return node, value, ranges

    parts = path.strip('/').split('/'); number = 2; traversed = []; hops = 0
    while parts:
        part = parts.pop(0)
        _, directory, _ = data(number)
        position = 0; found = None
        while position < len(directory):
            ino, size, name_len, _ = struct.unpack_from('<IHBB', directory, position)
            if size < 8 or position+size > len(directory): raise ValueError('invalid ext4 directory')
            name = directory[position+8:position+8+name_len].decode('utf-8')
            if ino and name == part: found = ino; break
            position += size
        if found is None: raise ValueError('missing vendor path: '+path)
        node, value, ranges = data(found)
        if struct.unpack_from('<H', node)[0] & 0xf000 == 0xa000:
            hops += 1
            if hops > 8: raise ValueError('vendor symlink loop')
            target = value.decode('utf-8')
            joined = ([] if target.startswith('/') else traversed) + target.strip('/').split('/') + parts
            normalized = []
            for item in joined:
                if item == '..':
                    if not normalized: raise ValueError('vendor symlink escapes root')
                    normalized.pop()
                elif item != '.': normalized.append(item)
            parts = normalized; number = 2; traversed = []
        else:
            number = found; traversed.append(part)
    return ranges


def fat_file(stream, base, path):
    boot = read_at(stream, base, 512)
    sector = struct.unpack_from('<H', boot, 11)[0]; cluster_sectors = boot[13]
    reserved = struct.unpack_from('<H', boot, 14)[0]; fats = boot[16]
    roots = struct.unpack_from('<H', boot, 17)[0]
    fat_sectors = struct.unpack_from('<H', boot, 22)[0]
    fat32 = not fat_sectors
    if fat32: fat_sectors = struct.unpack_from('<I', boot, 36)[0]
    cluster_bytes = sector*cluster_sectors
    root_bytes = ((roots*32+sector-1)//sector)*sector
    root_offset = base+(reserved+fats*fat_sectors)*sector
    data_offset = root_offset+root_bytes
    def chain(cluster):
        seen = set(); result = []
        while cluster < (0x0ffffff8 if fat32 else 0xfff8):
            if cluster < 2 or cluster in seen: raise ValueError('invalid FAT chain')
            seen.add(cluster)
            result.append([data_offset+(cluster-2)*cluster_bytes, cluster_bytes])
            offset = base+reserved*sector+cluster*(4 if fat32 else 2)
            cluster = int.from_bytes(read_at(stream, offset, 4 if fat32 else 2), 'little')
            if fat32: cluster &= 0x0fffffff
        return result
    ranges = chain(struct.unpack_from('<I', boot, 44)[0]) if fat32 else [[root_offset, root_bytes]]
    for component in path.strip('/').split('/'):
        directory = b''.join(read_at(stream, *pair) for pair in ranges)
        selected = None
        for pos in range(0, len(directory), 32):
            entry = directory[pos:pos+32]
            if not entry[0]: break
            if entry[0] == 0xe5 or entry[11] == 0x0f: continue
            name = entry[:8].decode('ascii').rstrip()
            ext = entry[8:11].decode('ascii').rstrip()
            if ext: name += '.'+ext
            if name.casefold() == component.casefold(): selected = entry; break
        if selected is None: raise ValueError('missing FAT vendor file: '+path)
        cluster = struct.unpack_from('<H', selected, 26)[0]
        if fat32: cluster |= struct.unpack_from('<H', selected, 20)[0] << 16
        ranges = chain(cluster)
    remaining = struct.unpack_from('<I', selected, 28)[0]; result = []
    for offset, length in ranges:
        length = min(remaining, length)
        if length: result.append([offset, length]); remaining -= length
    if remaining: raise ValueError('short FAT chain')
    return result


def generate(zip_path, reference, pinned):
    """Compile offsets only, with byte-for-byte parity against ms-extract.sh."""
    if sha(zip_path) != pinned['sha256']: raise ValueError('recovery ZIP hash mismatch')
    reference = Path(reference)
    with zipfile.ZipFile(zip_path) as archive, tempfile.TemporaryFile() as disk:
        names = [n for n in archive.namelist() if n.endswith('.raw') and 'fast-hab' not in n]
        if len(names) != 1: raise ValueError('expected one Microsoft disk image')
        member = names[0]
        with archive.open(member) as src:
            # Same bounded prefix as ms-extract.sh, containing the stock root.
            remaining = (165888+4194304)*512
            while remaining:
                block = src.read(min(1024**2, remaining))
                if not block: raise ValueError('short Microsoft disk image')
                disk.write(block); remaining -= len(block)
        entries = read_at(disk, 1024, 3*128)
        parts = [struct.unpack_from('<QQ', entries, n*128+32) for n in range(3)]
        esp, secondary, root = [start*512 for start, end in parts]
        ranges = {
            'platform-prefix.bin': [[0, esp]],
            'secondary-esp.img': [[secondary, (parts[1][1]-parts[1][0]+1)*512]],
            'Image': ext4_file(disk, root, '/boot/vmlinuz'),
            'pe100.dtb': fat_file(disk, esp, '/pe100.dtb'),
            'bootaa64.efi': fat_file(disk, esp, '/EFI/BOOT/bootaa64.efi'),
            'grubaa64.efi': fat_file(disk, esp, '/EFI/BOOT/grubaa64.efi'),
        }
        outputs = {}
        for name in sorted(FILES):
            ref = reference/('efi/'+name if name.endswith('.efi') else name)
            if name in ranges:
                actual = b''.join(read_at(disk, *pair) for pair in ranges[name])
                record = {'member': member, 'ranges': ranges[name]}
            else:
                actual = archive.read(name)
                record = {'member': name, 'ranges': [[0, len(actual)]]}
            if hashlib.sha256(actual).hexdigest() != sha(ref):
                raise ValueError('portable/Linux extraction differs: '+name)
            outputs[name] = dict(record, bytes=len(actual), sha256=sha(ref))
    return {'schema': 1, 'zip_sha256': pinned['sha256'], 'files': outputs}


def extract(zip_path, recipe, destination, pinned):
    if recipe.get('schema') != 1 or recipe.get('zip_sha256') != pinned['sha256']:
        raise ValueError('unsupported recovery recipe')
    if sha(zip_path) != pinned['sha256']: raise ValueError('recovery ZIP hash mismatch')
    if set(recipe['files']) != FILES: raise ValueError('invalid vendor recipe files')
    destination = Path(destination); destination.mkdir(parents=True, exist_ok=False)
    # Read each compressed member once; distribute its extents as bytes stream past.
    members = {}
    for name, record in recipe['files'].items():
        ranges = record['ranges']
        if not ranges or sum(pair[1] for pair in ranges) != record['bytes']:
            raise ValueError('invalid vendor extent lengths')
        logical = 0
        for offset, length in ranges:
            if not isinstance(offset, int) or not isinstance(length, int) or offset < 0 or length <= 0:
                raise ValueError('invalid vendor extent')
            members.setdefault(record['member'], []).append((offset, length, name, logical))
            logical += length
        if logical > 512*1024**2: raise ValueError('oversized vendor artifact')
        with (destination/name).open('xb') as dst: dst.truncate(logical)
    with zipfile.ZipFile(zip_path) as archive:
        for member, extents in members.items():
            limit = max(offset+length for offset, length, _, _ in extents)
            if limit > archive.getinfo(member).file_size: raise ValueError('vendor extent outside member')
            position = 0
            with archive.open(member) as src:
                while position < limit:
                    chunk = src.read(min(1024**2, limit-position))
                    if not chunk: raise ValueError('short recovery member')
                    for offset, length, name, logical in extents:
                        start, end = max(position, offset), min(position+len(chunk), offset+length)
                        if end > start:
                            with (destination/name).open('r+b') as dst:
                                dst.seek(logical+start-offset); dst.write(chunk[start-position:end-position])
                    position += len(chunk)
    for name, record in recipe['files'].items():
        if sha(destination/name) != record['sha256']: raise ValueError('vendor extraction hash mismatch: '+name)
    return destination
