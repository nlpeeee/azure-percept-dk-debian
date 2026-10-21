#!/usr/bin/env python3
"""Build the temporary Percept RAM-only diagnostic initramfs on ARM64 Linux.

Does not install or boot anything. Includes a static BusyBox, the reviewed UDP
sender and its native runtime libraries. Archive device nodes need no privileges.
--binary/--file/--symlink add further dynamic programs (with their libraries),
plain files and links, e.g. for the ESP launcher.
"""
import argparse
import fnmatch
import gzip
import hashlib
import json
import lzma
from pathlib import Path
import re
import stat
import struct
import subprocess
import uuid


def arm64_elf(path, require_static=False):
    data = path.read_bytes()
    if data[:6] != b"\x7fELF\x02\x01" or struct.unpack_from("<H", data, 18)[0] != 183:
        raise ValueError("Expected ARM64 ELF: " + str(path))
    if require_static:
        offset = struct.unpack_from("<Q", data, 32)[0]
        size, count = struct.unpack_from("<HH", data, 54)
        if any(struct.unpack_from("<I", data, offset + n * size)[0] == 3 for n in range(count)):
            raise ValueError("BusyBox must be static")
    return data


def library_dependencies(path):
    """Absolute ldd paths (libraries and loader) of a dynamic ARM64 ELF."""
    output = subprocess.check_output(["ldd", str(path.resolve())], text=True)
    return sorted(set(re.findall(r"(?:=>\s+)?(/[^\s()]+)", output)))


def archive_path(text):
    """Validate an archive member name; leading slashes are dropped."""
    name = text.lstrip("/")
    parts = name.split("/")
    if not name or any(p in ("", ".", "..") for p in parts) or not re.fullmatch(r"[A-Za-z0-9_./+-]+", name):
        raise ValueError("Unsafe archive path: " + text)
    return name


def source_destination(text, default_to_source):
    """Split SRC[:DEST]; DEST defaults to SRC's own absolute path."""
    source, separator, destination = text.partition(":")
    if not separator:
        if not default_to_source:
            raise ValueError("Expected SRC:DEST: " + text)
        destination = str(Path(source).resolve())
    return Path(source), archive_path(destination)


def archive(entries):
    output = bytearray()
    for inode, (name, mode, data, major, minor) in enumerate(entries + [("TRAILER!!!", 0, b"", 0, 0)], 1):
        encoded = name.encode("ascii") + b"\0"
        fields = [inode, mode, 0, 0, 1, 0, len(data), 0, 0, major, minor, len(encoded), 0]
        output.extend(("070701" + "".join("%08x" % n for n in fields)).encode("ascii"))
        output.extend(encoded)
        output.extend(bytes((-len(output)) % 4))
        output.extend(data)
        output.extend(bytes((-len(output)) % 4))
    return bytes(output)


def module_plan(tree, release, requested):
    """Resolve depmod's hard/soft dependencies; return uncompressed ARM64 modules.

    Use insmod with this explicit order, so runtime loading does not depend on
    BusyBox's optional modprobe/compression/depmod-index implementations.
    """
    if not re.fullmatch(r"[A-Za-z0-9_.+-]{1,128}", release):
        raise ValueError("Invalid kernel release")
    tree = tree.resolve(strict=True)
    if tree.name != release:
        raise ValueError("Modules tree must be the exact release directory: " + release)
    if not requested:
        raise ValueError("Module mode requires at least one --load-module")

    def key(name):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
            raise ValueError("Invalid module name: " + name)
        return name.replace("-", "_")

    def canonical(path):
        parts = path.split("/")
        if not path or path.startswith("/") or any(p in ("", ".", "..") for p in parts) or "\\" in path:
            raise ValueError("Unsafe module metadata path: " + path)
        if not re.fullmatch(r"[A-Za-z0-9_./+-]+", path):
            raise ValueError("Invalid module metadata path: " + path)
        if path.endswith((".xz", ".gz")):
            path = path.rsplit(".", 1)[0]
        if not path.endswith(".ko"):
            raise ValueError("Unsupported module format (stage .ko, .ko.xz or .ko.gz): " + path)
        return path

    def read_metadata(name):
        return (tree / name).read_text(encoding="utf-8")

    dep_text = read_metadata("modules.dep")
    builtin_text = read_metadata("modules.builtin")
    softdep_text = read_metadata("modules.softdep")
    aliases = []
    alias_file = tree / "modules.alias"
    if alias_file.exists():
        for line in alias_file.read_text(encoding="utf-8").splitlines():
            text = line.split("#", 1)[0].strip()
            if not text:
                continue
            fields = text.split(None, 1)
            if len(fields) != 2 or fields[0] != "alias":
                raise ValueError("Malformed modules.alias line: " + line)
            # Some real module aliases contain spaces (e.g. ASoC card names).
            # depmod writes the complete pattern between the keyword and the
            # final module-name token, without quoting those spaces.
            pattern_target = fields[1].rsplit(None, 1)
            if len(pattern_target) != 2:
                raise ValueError("Malformed modules.alias line: " + line)
            aliases.append((pattern_target[0], key(pattern_target[1])))
    by_name, dependencies, original = {}, {}, {}
    for line in dep_text.splitlines():
        if not line.strip():
            continue
        source, separator, deps = line.partition(":")
        if not separator:
            raise ValueError("Malformed modules.dep line: " + line)
        path = canonical(source)
        name = key(Path(path).stem)
        if name in by_name or path in original:
            raise ValueError("Duplicate module in modules.dep: " + source)
        by_name[name] = path
        original[path] = source
        dependencies[path] = [canonical(p) for p in deps.split()]
    builtin = {}
    for line in builtin_text.splitlines():
        if line.strip():
            path = canonical(line.strip())
            builtin[key(Path(path).stem)] = path
    soft, soft_errors, metadata_warnings = {}, {}, []
    for line in softdep_text.splitlines():
        fields = line.split("#", 1)[0].split()
        if not fields:
            continue
        name = None
        try:
            if len(fields) >= 2:
                name = key(fields[1])
            if name is None or fields[0] != "softdep":
                raise ValueError("Malformed modules.softdep line: " + line)
            if name in soft or name in soft_errors:
                raise ValueError("Duplicate softdep rule: " + name)
            pre, post, target = [], [], None
            for item in fields[2:]:
                if item == "pre:":
                    target = pre
                elif item == "post:":
                    target = post
                elif target is None:
                    raise ValueError("Malformed modules.softdep line: " + line)
                else:
                    target.append(key(item))
            soft[name] = (pre, post)
        except ValueError as error:
            # Older depmod versions can reproduce unsupported softdep strings
            # from unrelated newer modules. Never discard a selected rule, but
            # do not let unrelated drivers prevent this explicit closure build.
            if name is not None:
                soft_errors[name] = str(error)
            metadata_warnings.append(str(error))

    visiting, visited, ordered, builtins_used = set(), set(), [], []
    alias_resolutions = {}

    def visit(name):
        name = key(name)
        if name in visited:
            return
        if name in visiting:
            raise ValueError("Module dependency cycle at: " + name)
        if name in soft_errors:
            raise ValueError("Selected module has unsupported softdep metadata: " + soft_errors[name])
        if name not in by_name and name not in builtin:
            matches = list(dict.fromkeys(target for pattern, target in aliases
                           if fnmatch.fnmatchcase(name, pattern) or fnmatch.fnmatchcase(name.replace("_", "-"), pattern)))
            if not matches:
                raise ValueError("Dependency absent from staged metadata/aliases: " + name)
            alias_resolutions[name] = matches
            for target in matches:
                if target not in by_name and target not in builtin:
                    raise ValueError("Alias target absent from staged metadata: " + target)
                visit(target)
            return
        visiting.add(name)
        pre, post = soft.get(name, ([], []))
        for dependency in pre:
            visit(dependency)
        if name in by_name:
            path = by_name[name]
            for dependency in dependencies[path]:
                dependency_name = key(Path(dependency).stem)
                if by_name.get(dependency_name) != dependency and builtin.get(dependency_name) != dependency:
                    raise ValueError("Dependency path absent from metadata: " + dependency)
                visit(dependency_name)
            ordered.append(path)
        else:
            builtins_used.append(name)
        visiting.remove(name)
        visited.add(name)
        for dependency in post:
            visit(dependency)

    for name in requested:
        visit(name)
    files = []
    for path in ordered:
        source = tree / original[path]
        if not source.resolve(strict=True).is_relative_to(tree):
            raise ValueError("Module escapes staged tree: " + str(source))
        data = source.read_bytes()
        if source.suffix == ".xz":
            data = lzma.decompress(data)
        elif source.suffix == ".gz":
            data = gzip.decompress(data)
        if len(data) < 64 or data[:6] != b"\x7fELF\x02\x01" or struct.unpack_from("<H", data, 18)[0] != 183:
            raise ValueError("Expected ARM64 ELF module: " + str(source))
        vermagic = re.search(rb"(?:^|\x00)vermagic=([^\x00]+)\x00", data)
        if not vermagic or vermagic.group(1).split(b" ", 1)[0] != release.encode("ascii"):
            raise ValueError("Module vermagic does not match " + release + ": " + str(source))
        files.append((path, data))
    metadata = {
        "modules.dep": "".join(path + ":" + (" " + " ".join(dependencies[path]) if dependencies[path] else "") + "\n" for path in ordered),
        "modules.builtin": builtin_text,
        "modules.alias": "".join("alias " + pattern + " " + target + "\n" for pattern, target in aliases if target in visited),
        "modules.softdep": "".join("softdep " + name + (" pre: " + " ".join(pre) if pre else "") + (" post: " + " ".join(post) if post else "") + "\n"
                                   for name, (pre, post) in soft.items() if name in visited),
    }
    return files, metadata, dict(requested_modules=requested, builtin_modules=builtins_used,
                                module_alias_resolutions=alias_resolutions,
                                module_metadata_warnings=[message[:256] for message in metadata_warnings[:20]],
                                module_metadata_warning_count=len(metadata_warnings),
                                module_load_order=ordered, module_loader="busybox-insmod",
                                module_compression="decompressed-in-archive")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--busybox", required=True, type=Path)
    parser.add_argument("--sender", required=True, type=Path)
    parser.add_argument("--init", required=True, type=Path)
    parser.add_argument("--source-boot", required=True)
    parser.add_argument("--experiment", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--kernel-release", help="Exact expected uname -r; mandatory with module staging")
    parser.add_argument("--modules-tree", type=Path, help="Staged lib/modules/RELEASE directory with depmod text metadata")
    parser.add_argument("--load-module", action="append", default=[], help="Root module name, in desired order; repeatable")
    parser.add_argument("--binary", action="append", default=[], metavar="SRC[:DEST]",
                        help="Dynamic ARM64 ELF plus its ldd library dependencies; DEST defaults to SRC; repeatable")
    parser.add_argument("--file", action="append", default=[], metavar="SRC:DEST[:MODE]",
                        help="Plain file copied as-is, octal MODE (default 0644); repeatable")
    parser.add_argument("--symlink", action="append", default=[], metavar="LINK:TARGET", help="Symbolic link; repeatable")
    parser.add_argument("--require-applet", action="append", default=[], help="Additional BusyBox applet the init needs; repeatable")
    args = parser.parse_args()
    if str(uuid.UUID(args.source_boot)) != args.source_boot:
        raise ValueError("Source boot ID must be canonical")
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", args.experiment):
        raise ValueError("Invalid experiment token")
    if args.output.exists() or args.output.with_suffix(args.output.suffix + ".json").exists():
        raise ValueError("Refusing to overwrite an artifact")
    if args.kernel_release and not re.fullmatch(r"[A-Za-z0-9_.+-]{1,128}", args.kernel_release):
        raise ValueError("Invalid kernel release")
    if bool(args.modules_tree) != bool(args.load_module) or (args.modules_tree and not args.kernel_release):
        raise ValueError("--modules-tree, --kernel-release and --load-module are required together")
    module_files, module_metadata, module_manifest = [], {}, {}
    if args.modules_tree:
        module_files, module_metadata, module_manifest = module_plan(args.modules_tree, args.kernel_release, args.load_module)
    busybox = arm64_elf(args.busybox, require_static=True)
    sender = arm64_elf(args.sender)
    applets = set(subprocess.check_output([str(args.busybox.resolve()), "--list"], text=True).split())
    required = {"sh", "init", "mount", "mkdir", "cat", "sleep", "ip", "timeout", "uname", "dmesg", "reboot", "kill"}
    if args.modules_tree:
        required.add("insmod")
    required.update(args.require_applet)
    if required - applets:
        raise ValueError("Missing BusyBox applets: " + repr(required - applets))
    subprocess.run([str(args.busybox.resolve()), "sh", "-n", str(args.init)], check=True)
    entries = []
    names = set()

    def add(name, mode, data=b"", major=0, minor=0):
        if name in names:
            return
        names.add(name)
        parent = Path(name).parent.as_posix()
        if parent != ".":
            add(parent, stat.S_IFDIR | 0o755)
        entries.append((name, mode, data, major, minor))

    for name in ("bin", "sbin", "dev", "etc/percept-test", "proc", "sys", "run", "www", "tmp"):
        add(name, stat.S_IFDIR | (0o1777 if name == "tmp" else 0o755))
    add("bin/busybox", stat.S_IFREG | 0o755, busybox)
    add("bin/udp_log_sender", stat.S_IFREG | 0o755, sender)
    add("bin/sh", stat.S_IFLNK | 0o777, b"busybox")
    add("init", stat.S_IFREG | 0o755, args.init.read_bytes().replace(b"\r\n", b"\n"))
    add("dev/console", stat.S_IFCHR | 0o600, major=5, minor=1)
    add("dev/null", stat.S_IFCHR | 0o666, major=1, minor=3)
    add("etc/percept-test/experiment-id", stat.S_IFREG | 0o444, (args.experiment + "\n").encode())
    add("etc/percept-test/source-boot-id", stat.S_IFREG | 0o444, (args.source_boot + "\n").encode())
    add("etc/percept-test/expected-kernel-release", stat.S_IFREG | 0o444, ((args.kernel_release or "") + "\n").encode())
    module_prefix = "lib/modules/" + (args.kernel_release or "")
    for path, module in module_files:
        add(module_prefix + "/" + path, stat.S_IFREG | 0o444, module)
    for name, contents in module_metadata.items():
        add(module_prefix + "/" + name, stat.S_IFREG | 0o444, contents.encode("utf-8"))
    add("etc/percept-test/module-load-order", stat.S_IFREG | 0o444,
        "".join("/" + module_prefix + "/" + path + "\n" for path, _ in module_files).encode("ascii"))
    add("etc/percept-test/module-roots", stat.S_IFREG | 0o444, (" ".join(args.load_module) + "\n").encode("ascii"))
    paths = library_dependencies(args.sender)
    if not paths:
        raise ValueError("No dynamic sender dependencies found")
    for name in paths:
        data = arm64_elf(Path(name))
        add(name.lstrip("/"), stat.S_IFREG | 0o755, data)

    def add_new(name, mode, data=b""):
        # Explicit extras must not silently collide with an existing member.
        if name in names:
            raise ValueError("Duplicate archive member: " + name)
        add(name, mode, data)

    binary_dependencies = {}
    for text in args.binary:
        source, name = source_destination(text, default_to_source=True)
        add_new(name, stat.S_IFREG | 0o755, arm64_elf(source))
        libraries = library_dependencies(source)
        if not libraries:
            raise ValueError("No dynamic dependencies found: " + str(source))
        for library in libraries:
            add(library.lstrip("/"), stat.S_IFREG | 0o755, arm64_elf(Path(library)))
        binary_dependencies[name] = libraries
    extra_files = {}
    for text in args.file:
        source_text, separator, mode_text = text.rpartition(":")
        if not separator or not re.fullmatch(r"[0-7]{3,4}", mode_text):
            source_text, mode_text = text, "0644"
        source, name = source_destination(source_text, default_to_source=False)
        data = source.read_bytes()
        add_new(name, stat.S_IFREG | int(mode_text, 8), data)
        extra_files[name] = hashlib.sha256(data).hexdigest()
    for text in args.symlink:
        link, separator, target = text.partition(":")
        if not separator or not re.fullmatch(r"[A-Za-z0-9_./+-]+", target):
            raise ValueError("Expected LINK:TARGET: " + text)
        add_new(archive_path(link), stat.S_IFLNK | 0o777, target.encode("ascii"))
    data = gzip.compress(archive(entries), mtime=0)
    args.output.write_bytes(data)
    manifest = dict(experiment=args.experiment, source_boot_id=args.source_boot,
                    sha256=hashlib.sha256(data).hexdigest(), size=len(data),
                    paths=[n for n, *_ in entries], optional_httpd="httpd" in applets,
                    sender_dependencies=paths, installed=False)
    manifest.update(expected_kernel_release=args.kernel_release, **module_manifest)
    if binary_dependencies or extra_files or args.symlink:
        manifest.update(binary_dependencies=binary_dependencies, extra_files=extra_files, symlinks=args.symlink)
    args.output.with_suffix(args.output.suffix + ".json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
