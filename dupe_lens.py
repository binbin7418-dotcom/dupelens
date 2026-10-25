#!/usr/bin/env python3
"""
DupeLens — duplicate & near-duplicate photo finder with a quarantine
workflow and a re-check report.

Pipeline:
  1. Scan folders recursively. Every image file gets a SHA-256 (exact
     identity) and, when Pillow can decode it, a perceptual hash
     (ImageHash pHash) that survives resizing and re-compression.
  2. Group: byte-identical files group by SHA-256; near-duplicates group
     when their perceptual hashes are within a configurable Hamming
     distance (default 6 bits out of 64).
  3. In each group a keeper is chosen deterministically (highest
     resolution, then largest file, then earliest modification time).
  4. Clean mode moves every non-keeper into a quarantine folder —
     DupeLens NEVER deletes a photo. A manifest records where each
     file came from so the whole operation can be undone.
  5. The library is then re-scanned: the report proves the processed
     groups are gone, every keeper is still in place, and states how
     much space was freed by the quarantine.

Local only. No network access. Your photos never leave this computer.
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
import time

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
DEFAULT_THRESHOLD = 6
HASH_BITS = 64


def fmt_bytes(n):
    f = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if f < 1024 or unit == "TB":
            return f"{f:.0f} {unit}" if unit == "B" else f"{f:.1f} {unit}"
        f /= 1024.0


def sha256_of(path, chunk=1024 * 1024):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            data = fh.read(chunk)
            if not data:
                break
            h.update(data)
    return h.hexdigest()


def phash_of(path):
    """Return (phash_int, width, height) or (None, 0, 0) if undecodable."""
    try:
        import imagehash
        from PIL import Image
        with Image.open(path) as im:
            im.load()
            w, h = im.size
            ph = imagehash.phash(im.convert("RGB"))
        return int(str(ph), 16), w, h
    except Exception:
        return None, 0, 0


def scan_library(roots, exclude=()):
    """Walk roots for image files. Returns (records, skipped).
    Each record: path, size, mtime, sha256, phash (int|None), width, height."""
    exclude_resolved = [os.path.realpath(e) for e in exclude]
    records, skipped = [], []
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root):
            rp = os.path.realpath(dirpath)
            dirnames[:] = [d for d in dirnames
                           if not any(os.path.join(rp, d) == e or
                                      os.path.join(rp, d).startswith(e + os.sep)
                                      for e in exclude_resolved)]
            for name in sorted(filenames):
                if os.path.splitext(name)[1].lower() not in IMAGE_EXTS:
                    continue
                path = os.path.join(dirpath, name)
                if os.path.islink(path):
                    skipped.append({"path": path, "reason": "symlink — skipped for safety"})
                    continue
                try:
                    st = os.stat(path)
                    rec = {"path": path, "size": st.st_size, "mtime": st.st_mtime,
                           "sha256": sha256_of(path)}
                except OSError as e:
                    skipped.append({"path": path, "reason": f"unreadable ({e})"})
                    continue
                rec["phash"], rec["width"], rec["height"] = phash_of(path)
                rec["pixels"] = rec["width"] * rec["height"]
                records.append(rec)
    return records, skipped


class UnionFind:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def candidate_pairs(records, threshold):
    """Yield index pairs whose pHash distance could be <= threshold.
    Pigeonhole banding: split the 64-bit hash into threshold+1 bands —
    two hashes within `threshold` bits must agree on at least one whole
    band, so only same-band pairs need an exact distance check."""
    bands = threshold + 1
    band_bits = HASH_BITS // bands
    buckets = {}
    for i, rec in enumerate(records):
        if rec["phash"] is None:
            continue
        for b in range(bands):
            shift = b * band_bits
            width = band_bits if b < bands - 1 else HASH_BITS - shift
            key = (b, (rec["phash"] >> shift) & ((1 << width) - 1))
            buckets.setdefault(key, []).append(i)
    seen = set()
    for idxs in buckets.values():
        for x in range(len(idxs)):
            for y in range(x + 1, len(idxs)):
                pair = (idxs[x], idxs[y])
                if pair not in seen:
                    seen.add(pair)
                    yield pair


def build_groups(records, threshold=DEFAULT_THRESHOLD):
    """Group records into duplicate groups. Returns a list of group dicts:
    {id, kind, members (keeper first), keeper}. Singletons are omitted."""
    uf = UnionFind(len(records))
    by_sha = {}
    for i, rec in enumerate(records):
        by_sha.setdefault(rec["sha256"], []).append(i)
    for idxs in by_sha.values():
        for j in idxs[1:]:
            uf.union(idxs[0], j)
    for i, j in candidate_pairs(records, threshold):
        if bin(records[i]["phash"] ^ records[j]["phash"]).count("1") <= threshold:
            uf.union(i, j)
    clusters = {}
    for i in range(len(records)):
        clusters.setdefault(uf.find(i), []).append(i)
    groups = []
    for gid, idxs in enumerate(sorted((v for v in clusters.values() if len(v) > 1),
                                      key=lambda v: records[v[0]]["path"]), start=1):
        members = sorted((records[i] for i in idxs),
                         key=lambda r: (-r["pixels"], -r["size"], r["mtime"], r["path"]))
        shas = {r["sha256"] for r in members}
        if len(shas) == 1:
            kind = "exact"
        elif len(shas) == len(members):
            kind = "similar"
        else:
            kind = "exact + similar"
        groups.append({"id": gid, "kind": kind, "members": members, "keeper": members[0]})
    return groups


def summarize(records, groups, skipped):
    redundant = sum(len(g["members"]) - 1 for g in groups)
    reclaimable = sum(r["size"] for g in groups for r in g["members"][1:])
    return {
        "files_scanned": len(records),
        "files_skipped": len(skipped),
        "undecodable": sum(1 for r in records if r["phash"] is None),
        "groups": len(groups),
        "exact_groups": sum(1 for g in groups if g["kind"] == "exact"),
        "similar_groups": sum(1 for g in groups if g["kind"] != "exact"),
        "redundant_copies": redundant,
        "reclaimable_bytes": reclaimable,
    }


def group_lines(groups):
    lines = []
    for g in groups:
        k = g["keeper"]
        lines.append(f"### Group {g['id']} — {g['kind']} ({len(g['members'])} files)")
        lines.append(f"- KEEP: {k['path']} ({fmt_bytes(k['size'])}, "
                     f"{k['width']}x{k['height']})")
        for r in g["members"][1:]:
            dist = ""
            if r["phash"] is not None and k["phash"] is not None and r["sha256"] != k["sha256"]:
                d = bin(r["phash"] ^ k["phash"]).count("1")
                dist = f", perceptual distance {d}/{HASH_BITS}"
            same = "byte-identical" if r["sha256"] == k["sha256"] else "near-duplicate"
            lines.append(f"- DUPLICATE ({same}{dist}): {r['path']} ({fmt_bytes(r['size'])})")
        lines.append("")
    return lines


def run_scan(roots, threshold=DEFAULT_THRESHOLD, outdir=None):
    """Scan only — no file is touched. Optionally write dupelens_report.md."""
    records, skipped = scan_library(roots)
    groups = build_groups(records, threshold)
    s = summarize(records, groups, skipped)
    result = dict(s, group_list=groups, records=records, skipped=skipped,
                  threshold=threshold, roots=list(roots))
    if outdir:
        os.makedirs(outdir, exist_ok=True)
        lines = ["# DupeLens — duplicate scan report", "",
                 f"Folders: {', '.join(roots)}  ·  Similarity threshold: "
                 f"{threshold}/{HASH_BITS} bits", "",
                 "## Summary",
                 f"- Photos scanned: {s['files_scanned']}",
                 f"- Skipped (symlinks / unreadable): {s['files_skipped']}",
                 f"- Duplicate groups: {s['groups']} "
                 f"({s['exact_groups']} exact, {s['similar_groups']} with near-duplicates)",
                 f"- Redundant copies: {s['redundant_copies']}",
                 f"- Space held by redundant copies: {fmt_bytes(s['reclaimable_bytes'])}", "",
                 "## Groups (nothing has been moved — scan only)"]
        lines += group_lines(groups) or ["- no duplicates found", ""]
        if skipped:
            lines += ["## Skipped files"] + \
                     [f"- {x['path']} — {x['reason']}" for x in skipped] + [""]
        lines += ["Nothing was moved or deleted. Run DupeLens in clean mode to move "
                  "the duplicates into a quarantine folder (never deleted) with a "
                  "full restore manifest."]
        report_path = os.path.join(outdir, "dupelens_report.md")
        with open(report_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        result["report_path"] = report_path
    return result


def unique_dest(dest):
    if not os.path.exists(dest):
        return dest
    base, ext = os.path.splitext(dest)
    n = 2
    while os.path.exists(f"{base} ({n}){ext}"):
        n += 1
    return f"{base} ({n}){ext}"


def run_quarantine(roots, quarantine_dir, threshold=DEFAULT_THRESHOLD, outdir=None):
    """Scan, move non-keepers into quarantine_dir (NEVER delete), re-scan
    and produce the re-check report. Returns a summary dict."""
    roots = [os.path.abspath(r) for r in roots]
    quarantine_dir = os.path.abspath(quarantine_dir)
    os.makedirs(quarantine_dir, exist_ok=True)

    records, skipped = scan_library(roots, exclude=[quarantine_dir])
    groups = build_groups(records, threshold)
    before = summarize(records, groups, skipped)

    moves = []
    for g in groups:
        for rec in g["members"][1:]:
            src = rec["path"]
            rel = None
            for root in roots:
                if src == root or src.startswith(root + os.sep):
                    rel = os.path.relpath(src, root)
                    prefix = os.path.basename(root.rstrip(os.sep)) or "root"
                    break
            dest = os.path.join(quarantine_dir, prefix, rel) if rel else \
                os.path.join(quarantine_dir, os.path.basename(src))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            dest = unique_dest(dest)
            shutil.move(src, dest)
            moves.append({"group": g["id"], "kind": g["kind"],
                          "from": src, "to": dest, "size": rec["size"],
                          "sha256": rec["sha256"]})

    manifest_path = os.path.join(quarantine_dir, "dupelens_manifest.json")
    manifest = []
    if os.path.exists(manifest_path):
        try:
            manifest = json.load(open(manifest_path, encoding="utf-8"))
        except Exception:
            manifest = []
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    for m in moves:
        m["when"] = stamp
    manifest.extend(moves)
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)

    # Re-check: rescan the library with the same threshold.
    records2, skipped2 = scan_library(roots, exclude=[quarantine_dir])
    groups2 = build_groups(records2, threshold)
    keepers_ok = sum(1 for g in groups
                     if os.path.exists(g["keeper"]["path"]))
    freed = sum(m["size"] for m in moves)

    result = dict(before, moves=moves, freed_bytes=freed,
                  groups_after=len(groups2), groups_detail_after=groups2,
                  files_after=len(records2), keepers_intact=keepers_ok,
                  groups_before=len(groups), manifest_path=manifest_path,
                  quarantine_dir=quarantine_dir, threshold=threshold)

    if outdir:
        os.makedirs(outdir, exist_ok=True)
        lines = ["# DupeLens — quarantine & re-check report", "",
                 f"Folders: {', '.join(roots)}  ·  Similarity threshold: "
                 f"{threshold}/{HASH_BITS} bits  ·  Quarantine: {quarantine_dir}", "",
                 "## Before",
                 f"- Photos scanned: {before['files_scanned']}",
                 f"- Duplicate groups: {before['groups']} "
                 f"({before['exact_groups']} exact, {before['similar_groups']} with near-duplicates)",
                 f"- Redundant copies: {before['redundant_copies']} "
                 f"({fmt_bytes(before['reclaimable_bytes'])})", "",
                 "## Groups found"]
        lines += group_lines(groups) or ["- no duplicates found", ""]
        lines += ["## Moved to quarantine (nothing was deleted)"]
        lines += [f"- {m['from']}  ->  {m['to']} ({fmt_bytes(m['size'])})"
                  for m in moves] or ["- nothing moved"]
        lines += ["", "## Re-check after quarantine",
                  f"- Photos remaining in library: {len(records2)}",
                  f"- Duplicate groups remaining: {len(groups2)}",
                  f"- Keepers still in place: {keepers_ok}/{len(groups)} groups verified",
                  f"- Space freed in the library: {fmt_bytes(freed)} "
                  f"(the files themselves are safe in quarantine, not deleted)",
                  f"- Verdict: {'CLEAN — every processed group is resolved' if not groups2 else 'Groups remain — they were not part of this run or were re-added'}",
                  "", "## How to undo",
                  f"Manifest: {manifest_path}",
                  "Run:  python dupe_lens.py restore \"" + manifest_path + "\"",
                  "Every quarantined file moves back to its original folder; "
                  "if a new file now sits at an original path, the restored "
                  "file is renamed with a ' (2)' suffix instead of overwriting."]
        report_path = os.path.join(outdir, "dupelens_report.md")
        with open(report_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        result["report_path"] = report_path
    return result


def restore_quarantine(manifest_path):
    """Move every file listed in the manifest back to its original path."""
    entries = json.load(open(manifest_path, encoding="utf-8"))
    restored, missing = 0, []
    for e in entries:
        src, dest = e["to"], e["from"]
        if not os.path.exists(src):
            missing.append(src)
            continue
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.move(src, unique_dest(dest))
        restored += 1
    return {"restored": restored, "missing": missing}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="dupe_lens.py",
                                 description="DupeLens — duplicate photo finder (never deletes)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("scan", "clean"):
        p = sub.add_parser(name)
        p.add_argument("folders", nargs="+")
        p.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD,
                       help="perceptual-hash distance 0-32 (default 6; lower = stricter)")
        p.add_argument("--out", default=".", help="folder for dupelens_report.md")
        if name == "clean":
            p.add_argument("--quarantine", default=None,
                           help="quarantine folder (default: <first folder>/DupeLens-Quarantine)")
    p = sub.add_parser("restore")
    p.add_argument("manifest")
    args = ap.parse_args(argv)

    if args.cmd == "restore":
        r = restore_quarantine(args.manifest)
        print(f"restored={r['restored']} missing={len(r['missing'])}")
        return 0
    if not (0 <= args.threshold <= 32):
        print("threshold must be between 0 and 32")
        return 2
    if args.cmd == "scan":
        s = run_scan(args.folders, args.threshold, args.out)
        print(f"scanned={s['files_scanned']} groups={s['groups']} "
              f"redundant={s['redundant_copies']} reclaimable={fmt_bytes(s['reclaimable_bytes'])} "
              f"report={s.get('report_path')}")
        return 0
    qdir = args.quarantine or os.path.join(os.path.abspath(args.folders[0]),
                                            "DupeLens-Quarantine")
    s = run_quarantine(args.folders, qdir, args.threshold, args.out)
    print(f"scanned={s['files_scanned']} groups={s['groups_before']} "
          f"moved={len(s['moves'])} freed={fmt_bytes(s['freed_bytes'])} "
          f"groups_after={s['groups_after']} report={s.get('report_path')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
