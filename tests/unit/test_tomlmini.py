# SPDX-License-Identifier: MIT
import unittest

import helpers  # noqa: F401
from percept import tomlmini

SAMPLE = r'''
# comment
schema = 1
name = "a \"q\" \u00e9"   # trailing
lit = 'C:\raw'
flag = true
n = 1_000
list = [
  "a", "b",   # inline comment
]
[sect]
x = 2
[sect.sub]
y = { a = 1, b = ["z"] }
[[arr]]
k = "one"
[[arr]]
k = "two"
[arr.child]
v = 3
'''


class TomlMini(unittest.TestCase):
    def test_parse(self):
        d = tomlmini.loads(SAMPLE, force_mini=True)
        self.assertEqual(d["name"], 'a "q" \u00e9')
        self.assertEqual(d["lit"], "C:" + chr(92) + "raw")
        self.assertEqual(d["n"], 1000)
        self.assertEqual(d["list"], ["a", "b"])
        self.assertEqual(d["sect"]["sub"]["y"], {"a": 1, "b": ["z"]})
        self.assertEqual([a["k"] for a in d["arr"]], ["one", "two"])
        self.assertEqual(d["arr"][1]["child"]["v"], 3)

    def test_matches_stdlib_when_available(self):
        try:
            import tomllib
        except ImportError:
            self.skipTest("tomllib needs Python 3.11+")
        self.assertEqual(tomlmini.loads(SAMPLE, force_mini=True), tomllib.loads(SAMPLE))

    def test_rejects_unsupported(self):
        for bad in ('x = 1.5', 'x = """a"""', 'x = 1979-05-27', 'a = 1\na = 2', 'x = ', '[t]\n[t]', 'x = "unterminated'):
            with self.assertRaises(tomlmini.TomlError, msg=bad):
                tomlmini.loads(bad, force_mini=True)

    def test_error_has_line_number(self):
        with self.assertRaises(tomlmini.TomlError) as cm:
            tomlmini.loads('a = 1\nb = oops\n', force_mini=True)
        self.assertIn("line 2", str(cm.exception))

    def test_roundtrip(self):
        data = {"schema": 1, "board": {"name": "x", "tz": 'a"b' + chr(92) + 'c'}, "user": [{"name": "u", "k": ["a", "b"]}, {"name": "v"}],
                "net": {"eth": {"dns": [], "on": True}}}
        self.assertEqual(tomlmini.loads(tomlmini.dumps(data), force_mini=True), data)


if __name__ == "__main__":
    unittest.main()
