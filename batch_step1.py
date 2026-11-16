#!/usr/bin/env python
"""
batch_step1.py — headless stage-1 re-analysis of the TMJ joint space from STL meshes.

Recomputes the global distance map and the filtered functional surface for every
case in a folder, using continuous distances and area-weighted statistics, and
writes one CSV row per joint. Landmark files are NOT required: the anterior /
middle / posterior subdivision belongs to stages 2 and 3 and is not reproduced here.

Requires only NumPy and VTK; the computation is shared with the 3D Slicer module
through tmj_space_core, so the numbers are identical to an interactive run.

    python batch_step1.py --root /path/to/cases --out step1_continuous.csv
    python batch_step1.py --root /path/to/cases --list      # check pairing first
"""

import argparse
import csv
import fnmatch
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tmj_space_core as core


def findCases(root, condylePattern, fossaPattern):
    """Yield (caseName, condylePath, fossaPath) for every folder holding both meshes."""
    cases = []
    for dirPath, _dirNames, fileNames in os.walk(root):
        stls = [f for f in fileNames if f.lower().endswith(".stl")]
        condyles = [f for f in stls if fnmatch.fnmatch(f.lower(), condylePattern.lower())]
        fossae = [f for f in stls if fnmatch.fnmatch(f.lower(), fossaPattern.lower())]
        if len(condyles) == 1 and len(fossae) == 1:
            cases.append((os.path.relpath(dirPath, root),
                          os.path.join(dirPath, condyles[0]),
                          os.path.join(dirPath, fossae[0])))
        elif condyles or fossae:
            sys.stderr.write(
                f"[skip] {dirPath}: {len(condyles)} condyle / {len(fossae)} fossa match\n")
    return sorted(cases)


def flatten(prefix, stats):
    return {f"{prefix}_{k}": v for k, v in stats.items()}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", required=True, help="folder containing one subfolder per joint")
    ap.add_argument("--condyle", default="*condyl*.stl", help="glob for the condyle mesh")
    ap.add_argument("--fossa", default="*foss*.stl", help="glob for the articular fossa mesh")
    ap.add_argument("--cutoff", type=float, default=5.0, help="functional-surface threshold (mm)")
    ap.add_argument("--out", default="step1_continuous.csv")
    ap.add_argument("--list", action="store_true", help="only list the detected pairs")
    args = ap.parse_args()

    cases = findCases(args.root, args.condyle, args.fossa)
    if not cases:
        sys.exit("No case folder contained exactly one condyle and one fossa mesh.")

    if args.list:
        for name, c, f in cases:
            print(f"{name}\n    condyle: {os.path.basename(c)}\n    fossa  : {os.path.basename(f)}")
        print(f"\n{len(cases)} case(s) ready.")
        return

    rows = []
    for i, (name, condylePath, fossaPath) in enumerate(cases, start=1):
        print(f"[{i}/{len(cases)}] {name}", flush=True)
        try:
            result = core.computeStep1(core.readSTL(condylePath), core.readSTL(fossaPath),
                                       cutoffMm=args.cutoff)
        except Exception as exc:                      # noqa: BLE001 - report and continue
            sys.stderr.write(f"[error] {name}: {exc}\n")
            continue
        row = {"Case": name, "CutoffMm": result["cutoff_mm"],
               "VerticesAboveDisplayMax": result["n_capped_vertices"],
               "PercentAboveDisplayMax": result["percent_capped"]}
        row.update(flatten("Global", result["global"]))
        row.update(flatten("Filtered", result["filtered"]))
        row.update(flatten("GlobalDiscretised", result["global_discretised"]))
        row.update(flatten("FilteredDiscretised", result["filtered_discretised"]))
        rows.append(row)

    if not rows:
        sys.exit("No case could be processed.")

    with open(args.out, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n{len(rows)} case(s) written to {args.out}")


if __name__ == "__main__":
    main()
