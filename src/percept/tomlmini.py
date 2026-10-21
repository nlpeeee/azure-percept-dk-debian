# SPDX-License-Identifier: MIT
"""A small TOML reader/writer for Python 3.9 (no tomllib before 3.11).

Reads the subset this project uses: comments, ``[table]`` / ``[[array]]`` headers
(dotted), ``key = value`` with basic and literal strings, integers, booleans,
arrays (multi-line, trailing comma) and inline tables. Anything else (floats,
dates, multi-line strings) raises ``TomlError`` rather than being misread.
``loads`` prefers the stdlib ``tomllib`` when it exists.
"""
import re

try:  # Python 3.11+
    import tomllib as _tomllib
except ImportError:  # pragma: no cover - exercised on 3.9/3.10
    _tomllib = None


class TomlError(ValueError):
    pass


_BARE = re.compile(r"[A-Za-z0-9_-]+")
_INT = re.compile(r"[+-]?(0|[1-9][0-9_]*)")
_ESC = {'"': '"', "\\": "\\", "n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f"}


def loads(text, force_mini=False):
    if _tomllib is not None and not force_mini:
        try:
            return _tomllib.loads(text)
        except _tomllib.TOMLDecodeError as exc:
            raise TomlError(str(exc)) from None
    return _Parser(text).parse()


def load_file(path):
    with open(path, "rb") as f:
        raw = f.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise TomlError("%s: not valid UTF-8 (%s)" % (path, exc)) from None
    if text.startswith("﻿"):  # Notepad on Windows
        text = text[1:]
    try:
        return loads(text)
    except TomlError as exc:
        raise TomlError("%s: %s" % (path, exc)) from None


class _Parser:
    def __init__(self, text):
        self.s = text.replace("\r\n", "\n")
        self.i = 0
        self.root = {}
        self.cur = self.root
        self.defined = set()

    def err(self, msg):
        line = self.s.count("\n", 0, self.i) + 1
        raise TomlError("line %d: %s" % (line, msg))

    def peek(self):
        return self.s[self.i] if self.i < len(self.s) else ""

    def skip_ws(self):
        while self.peek() in (" ", "\t"):
            self.i += 1

    def skip_ws_nl(self):
        while True:
            self.skip_ws()
            if self.peek() == "#":
                while self.peek() not in ("\n", ""):
                    self.i += 1
            if self.peek() == "\n":
                self.i += 1
            else:
                return

    def end_of_line(self):
        self.skip_ws()
        if self.peek() == "#":
            while self.peek() not in ("\n", ""):
                self.i += 1
        if self.peek() not in ("\n", ""):
            self.err("unexpected text after value")
        if self.peek() == "\n":
            self.i += 1

    def parse(self):
        while True:
            self.skip_ws_nl()
            c = self.peek()
            if c == "":
                return self.root
            if c == "[":
                self.header()
            else:
                self.keyval(self.cur)
                self.end_of_line()

    def key_path(self, stop):
        parts = []
        while True:
            self.skip_ws()
            c = self.peek()
            if c == '"':
                parts.append(self.basic_string())
            elif c == "'":
                parts.append(self.literal_string())
            else:
                m = _BARE.match(self.s, self.i)
                if not m:
                    self.err("invalid key")
                parts.append(m.group(0))
                self.i = m.end()
            self.skip_ws()
            if self.peek() == ".":
                self.i += 1
                continue
            if self.peek() == stop:
                return parts
            self.err("expected %r" % stop)

    def header(self):
        array = self.s.startswith("[[", self.i)
        self.i += 2 if array else 1
        parts = self.key_path("]")
        self.i += 1
        if array:
            if self.peek() != "]":
                self.err("expected ']]'")
            self.i += 1
        self.end_of_line()
        node = self.root
        for p in parts[:-1]:
            nxt = node.setdefault(p, {})
            if isinstance(nxt, list):
                nxt = nxt[-1]
            if not isinstance(nxt, dict):
                self.err("key %r is not a table" % p)
            node = nxt
        last = parts[-1]
        if array:
            lst = node.setdefault(last, [])
            if not isinstance(lst, list):
                self.err("%r is not an array of tables" % last)
            tbl = {}
            lst.append(tbl)
            self.cur = tbl
        else:
            ident = tuple(parts)
            if ident in self.defined:
                self.err("table %s defined twice" % ".".join(parts))
            self.defined.add(ident)
            tbl = node.setdefault(last, {})
            if not isinstance(tbl, dict):
                self.err("%r is not a table" % last)
            self.cur = tbl

    def keyval(self, table):
        parts = self.key_path("=")
        self.i += 1
        self.skip_ws()
        value = self.value()
        node = table
        for p in parts[:-1]:
            node = node.setdefault(p, {})
            if not isinstance(node, dict):
                self.err("key %r is not a table" % p)
        if parts[-1] in node:
            self.err("duplicate key %r" % parts[-1])
        node[parts[-1]] = value

    def value(self):
        c = self.peek()
        if c == '"':
            if self.s.startswith('"""', self.i):
                self.err("multi-line strings are not supported; use a single line or *_file")
            return self.basic_string()
        if c == "'":
            if self.s.startswith("'''", self.i):
                self.err("multi-line strings are not supported; use a single line or *_file")
            return self.literal_string()
        if c == "[":
            return self.array()
        if c == "{":
            return self.inline_table()
        if self.s.startswith("true", self.i):
            self.i += 4
            return True
        if self.s.startswith("false", self.i):
            self.i += 5
            return False
        m = _INT.match(self.s, self.i)
        if m:
            nxt = self.s[m.end():m.end() + 1]
            if nxt in (".", "e", "E", "-", ":"):
                self.err("floats and dates are not supported")
            self.i = m.end()
            return int(m.group(0).replace("_", ""))
        self.err("invalid value")

    def basic_string(self):
        self.i += 1
        out = []
        while True:
            c = self.peek()
            if c in ("", "\n"):
                self.err("unterminated string")
            self.i += 1
            if c == '"':
                return "".join(out)
            if c == "\\":
                e = self.peek()
                self.i += 1
                if e in _ESC:
                    out.append(_ESC[e])
                elif e in ("u", "U"):
                    n = 4 if e == "u" else 8
                    hexs = self.s[self.i:self.i + n]
                    if len(hexs) != n or not re.fullmatch(r"[0-9A-Fa-f]+", hexs):
                        self.err("bad unicode escape")
                    out.append(chr(int(hexs, 16)))
                    self.i += n
                else:
                    self.err("bad escape \\%s" % e)
            else:
                out.append(c)

    def literal_string(self):
        self.i += 1
        end = self.s.find("'", self.i)
        nl = self.s.find("\n", self.i)
        if end < 0 or (0 <= nl < end):
            self.err("unterminated string")
        val = self.s[self.i:end]
        self.i = end + 1
        return val

    def array(self):
        self.i += 1
        items = []
        while True:
            self.skip_ws_nl()
            if self.peek() == "]":
                self.i += 1
                return items
            items.append(self.value())
            self.skip_ws_nl()
            if self.peek() == ",":
                self.i += 1
            elif self.peek() != "]":
                self.err("expected ',' or ']'")

    def inline_table(self):
        self.i += 1
        tbl = {}
        while True:
            self.skip_ws()
            if self.peek() == "}":
                self.i += 1
                return tbl
            self.keyval(tbl)
            self.skip_ws()
            if self.peek() == ",":
                self.i += 1
            elif self.peek() != "}":
                self.err("expected ',' or '}'")


# --------------------------------------------------------------------- writer

def _scalar(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, str):
        out = ['"']
        for ch in v:
            if ch == '"':
                out.append('\\"')
            elif ch == "\\":
                out.append("\\\\")
            elif ch == "\n":
                out.append("\\n")
            elif ch == "\t":
                out.append("\\t")
            elif ch == "\r":
                out.append("\\r")
            elif ord(ch) < 0x20 or ord(ch) == 0x7F:
                out.append("\\u%04x" % ord(ch))
            else:
                out.append(ch)
        out.append('"')
        return "".join(out)
    if isinstance(v, list):
        return "[" + ", ".join(_scalar(x) for x in v) + "]"
    raise TomlError("cannot write %r" % type(v).__name__)


def _key(k):
    return k if _BARE.fullmatch(k) else _scalar(k)


def dumps(data):
    """Write nested dicts / lists of dicts / scalars / lists of scalars."""
    lines = []

    def is_tables(v):
        return isinstance(v, list) and v and all(isinstance(x, dict) for x in v)

    def emit(table, path):
        scalars = [(k, v) for k, v in table.items() if not isinstance(v, dict) and not is_tables(v)]
        for k, v in scalars:
            lines.append("%s = %s" % (_key(k), _scalar(v)))
        for k, v in table.items():
            if isinstance(v, dict):
                lines.append("")
                lines.append("[%s]" % ".".join(_key(p) for p in path + [k]))
                emit(v, path + [k])
            elif is_tables(v):
                for item in v:
                    lines.append("")
                    lines.append("[[%s]]" % ".".join(_key(p) for p in path + [k]))
                    emit(item, path + [k])

    emit(data, [])
    return "\n".join(lines).lstrip("\n") + "\n"
