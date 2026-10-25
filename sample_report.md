# DupeLens — quarantine & re-check report

Folders: /home/hatch/workspace/dupelens-product/dev/seed_library  ·  Similarity threshold: 6/64 bits  ·  Quarantine: /home/hatch/workspace/dupelens-product/dev/seed_quarantine

## Before
- Photos scanned: 7
- Duplicate groups: 2 (1 exact, 1 with near-duplicates)
- Redundant copies: 4 (57.3 KB)

## Groups found
### Group 1 — exact + similar (4 files)
- KEEP: /home/hatch/workspace/dupelens-product/dev/seed_library/A/IMG_A_original.jpg (26.7 KB, 800x600)
- DUPLICATE (byte-identical): /home/hatch/workspace/dupelens-product/dev/seed_library/A/IMG_A_copy.jpg (26.7 KB)
- DUPLICATE (near-duplicate, perceptual distance 2/64): /home/hatch/workspace/dupelens-product/dev/seed_library/A/IMG_A_recompressed.jpg (14.4 KB)
- DUPLICATE (near-duplicate, perceptual distance 0/64): /home/hatch/workspace/dupelens-product/dev/seed_library/A/IMG_A_resized.jpg (11.4 KB)

### Group 2 — exact (2 files)
- KEEP: /home/hatch/workspace/dupelens-product/dev/seed_library/B/IMG_B_original.png (4.9 KB, 800x600)
- DUPLICATE (byte-identical): /home/hatch/workspace/dupelens-product/dev/seed_library/B/IMG_B_copy.png (4.9 KB)

## Moved to quarantine (nothing was deleted)
- /home/hatch/workspace/dupelens-product/dev/seed_library/A/IMG_A_copy.jpg  ->  /home/hatch/workspace/dupelens-product/dev/seed_quarantine/seed_library/A/IMG_A_copy.jpg (26.7 KB)
- /home/hatch/workspace/dupelens-product/dev/seed_library/A/IMG_A_recompressed.jpg  ->  /home/hatch/workspace/dupelens-product/dev/seed_quarantine/seed_library/A/IMG_A_recompressed.jpg (14.4 KB)
- /home/hatch/workspace/dupelens-product/dev/seed_library/A/IMG_A_resized.jpg  ->  /home/hatch/workspace/dupelens-product/dev/seed_quarantine/seed_library/A/IMG_A_resized.jpg (11.4 KB)
- /home/hatch/workspace/dupelens-product/dev/seed_library/B/IMG_B_copy.png  ->  /home/hatch/workspace/dupelens-product/dev/seed_quarantine/seed_library/B/IMG_B_copy.png (4.9 KB)

## Re-check after quarantine
- Photos remaining in library: 3
- Duplicate groups remaining: 0
- Keepers still in place: 2/2 groups verified
- Space freed in the library: 57.3 KB (the files themselves are safe in quarantine, not deleted)
- Verdict: CLEAN — every processed group is resolved

## How to undo
Manifest: /home/hatch/workspace/dupelens-product/dev/seed_quarantine/dupelens_manifest.json
Run:  python dupe_lens.py restore "/home/hatch/workspace/dupelens-product/dev/seed_quarantine/dupelens_manifest.json"
Every quarantined file moves back to its original folder; if a new file now sits at an original path, the restored file is renamed with a ' (2)' suffix instead of overwriting.
