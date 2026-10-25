#!/usr/bin/env python3
"""DupeLens desktop shell (tkinter). Pick a photo folder -> find duplicate
and near-duplicate photos -> optionally quarantine the extras (never
deleted) -> re-check report."""
import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dupe_lens import run_quarantine, run_scan, fmt_bytes, DEFAULT_THRESHOLD


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("DupeLens — Duplicate Photo Finder (Quarantine, Never Delete)")
        self.geometry("720x560")
        self.folder = tk.StringVar()
        self.threshold = tk.StringVar(value=str(DEFAULT_THRESHOLD))
        tk.Label(self, text="Photo folder to scan (subfolders included):").pack(
            anchor="w", padx=12, pady=(12, 2))
        row = tk.Frame(self)
        row.pack(fill="x", padx=12)
        tk.Entry(row, textvariable=self.folder).pack(side="left", fill="x", expand=True)
        tk.Button(row, text="Browse…", command=self.pick).pack(side="left", padx=6)
        row2 = tk.Frame(self)
        row2.pack(fill="x", padx=12, pady=(8, 0))
        tk.Label(row2, text="Similarity sensitivity (perceptual distance 0–32, "
                            "lower = stricter, 6 = recommended):").pack(side="left")
        tk.Entry(row2, textvariable=self.threshold, width=4).pack(side="left", padx=6)
        btns = tk.Frame(self)
        btns.pack(pady=12)
        self.btn_scan = tk.Button(btns, text="Scan Only — Report, Move Nothing",
                                  command=lambda: self.run(False), height=2)
        self.btn_scan.pack(side="left", padx=6)
        self.btn_clean = tk.Button(btns, text="Scan && Quarantine Duplicates",
                                   command=lambda: self.run(True), height=2)
        self.btn_clean.pack(side="left", padx=6)
        self.log = scrolledtext.ScrolledText(self, wrap="word")
        self.log.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.write("DupeLens finds byte-identical and near-duplicate photos "
                   "(resized / re-compressed copies included).\n"
                   "SAFETY PROMISE: DupeLens never deletes a photo. In clean mode, "
                   "extra copies are moved into a 'DupeLens-Quarantine' folder with "
                   "a restore manifest, and the library is re-scanned to prove the "
                   "duplicates are gone and every keeper is untouched.\n"
                   "Everything runs locally — your photos never leave this computer.\n")

    def write(self, s):
        self.log.insert("end", s)
        self.log.see("end")

    def pick(self):
        p = filedialog.askdirectory()
        if p:
            self.folder.set(p)

    def run(self, clean):
        folder = self.folder.get().strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showerror("DupeLens", "Choose a photo folder first.")
            return
        try:
            threshold = int(self.threshold.get())
            assert 0 <= threshold <= 32
        except Exception:
            messagebox.showerror("DupeLens", "Similarity must be a whole number between 0 and 32.")
            return
        self.btn_scan.config(state="disabled")
        self.btn_clean.config(state="disabled")
        threading.Thread(target=self._work, args=(folder, threshold, clean),
                         daemon=True).start()

    def _work(self, folder, threshold, clean):
        try:
            outdir = os.path.join(folder, "dupelens_output")
            if clean:
                qdir = os.path.join(folder, "DupeLens-Quarantine")
                s = run_quarantine([folder], qdir, threshold, outdir)
                self.write(f"\nDone. Photos scanned: {s['files_scanned']} · "
                           f"groups found: {s['groups_before']} · "
                           f"copies quarantined: {len(s['moves'])} · "
                           f"space freed: {fmt_bytes(s['freed_bytes'])}\n"
                           f"Re-check: duplicate groups remaining: {s['groups_after']} · "
                           f"keepers verified in place: {s['keepers_intact']}/{s['groups_before']}\n"
                           f"Quarantine folder: {qdir}\nReport: {s['report_path']}\n"
                           "Nothing was deleted — restore any file from the quarantine "
                           "folder using the manifest inside it.\n")
            else:
                s = run_scan([folder], threshold, outdir)
                self.write(f"\nScan done. Photos scanned: {s['files_scanned']} · "
                           f"duplicate groups: {s['groups']} · "
                           f"redundant copies: {s['redundant_copies']} · "
                           f"space they hold: {fmt_bytes(s['reclaimable_bytes'])}\n"
                           f"Report: {s['report_path']}\n"
                           "Scan only — nothing was moved.\n")
        except Exception as e:  # surface, never crash silently
            self.write(f"\nError: {e}\n")
        finally:
            self.btn_scan.config(state="normal")
            self.btn_clean.config(state="normal")


if __name__ == "__main__":
    App().mainloop()
