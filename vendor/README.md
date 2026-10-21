# Vendor inputs

`vendor-manifest.toml` is the single list of everything this project downloads
from someone else, with source URL and SHA-256. Microsoft/ASUS/Intel/NXP
material is **never** committed or attached to releases: `percept fetch` pulls
it from the original host onto your machine (`cache/vendor/`) and verifies the
hash, so the legal relationship is between you and the vendor.

Entries marked `# pin before first release` have no hash yet and are refused
by `fetch` until one is recorded.
