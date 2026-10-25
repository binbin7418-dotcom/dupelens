# DupeLens — Duplicate & Similar Photo Finder (Quarantine, Never Delete)

DupeLens scans a photo folder and finds **byte-identical duplicates** and
**near-duplicates** (the same photo resized or re-compressed by a phone,
a messaging app, or an export). It then moves the extra copies into a
quarantine folder — **it never deletes a photo** — re-scans your library,
and writes a report proving the duplicates are gone and every keeper is
untouched. 100% local — your photos never leave your computer.

## The safety promise
- Nothing is ever deleted. Extra copies are *moved* to `DupeLens-Quarantine`
  with a manifest (`dupelens_manifest.json`) recording every original path.
- One command (or the manifest) restores everything to its original folder.
  If a new file now sits at an original path, the restored file is renamed
  with a ` (2)` suffix instead of overwriting it.
- Scan-only mode moves nothing at all — it just writes the report.

## How grouping works
- Exact duplicates: identical SHA-256.
- Near-duplicates: perceptual hash (pHash) distance at or below a threshold
  you control (default 6 of 64 bits; lower = stricter). In our seeded test,
  a resized copy measured distance 0 and a re-compressed copy distance 2,
  while unrelated photos measured 38.
- Keeper rule (deterministic): highest resolution wins, then largest file,
  then earliest modification time. The report shows, per group, what was
  kept, what was quarantined, and the measured distance for each copy.

## Verified behaviour
Seeded acceptance test (7 photos with known ground truth: one photo in 4
copies — original, byte-identical, resized, re-compressed — one photo in 2
copies, one unique photo): **27/27 checks passed**. Both groups found, the
resized and re-compressed copies grouped with their original, **0 false
positives**, quarantine re-scan showed 0 groups remaining, all 7 originals
accounted for and byte-intact, and restore brought every file back.
A 300-photo generated library scanned in 0.4–0.7 s on the test machine.
Full log: TEST-RESULTS in the product package.

## Run from source
```
pip install -r requirements.txt
python dupe_lens.py scan  "D:\Photos" --out report_folder
python dupe_lens.py clean "D:\Photos" --out report_folder
python dupe_lens.py restore "D:\Photos\DupeLens-Quarantine\dupelens_manifest.json"
```
`clean` accepts `--threshold N` (0–32) and `--quarantine <folder>`.
The Windows app (`gui.py`, packaged with PyInstaller) wraps the same engine.

## Scope & honest limits
- Formats: JPG/JPEG, PNG, WebP, BMP, GIF, TIFF (what Pillow decodes).
  HEIC/RAW are not decoded in this version.
- Perceptual hashing catches resizes and re-compression. Heavy edits
  (strong crops, filters, watermarks) can push a copy beyond the threshold
  and be missed. Raising the threshold casts a wider net (catches more
  edited copies, with a higher false-match risk); lowering it is stricter.
  Review the report before emptying quarantine; that is what it is for.
