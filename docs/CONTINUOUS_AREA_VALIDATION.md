# Continuous, area-weighted statistics — development validation notes

**Status: experimental branch, not a scientific release.** The original study implementation remains on `main`. No clinical data were re-analysed by these code changes.

## What changed

- Retains continuous `RawAbsoluteDistance` arrays for all descriptive statistics; `AbsoluteDistance` remains rounded to 0.25 mm and capped at 4.5 mm **for colour mapping only**.
- Estimates each vertex's representational surface area as one third of its incident triangle areas. Computes area-weighted mean, population SD, and weighted median; min and max use the original unrounded values.
- Percentage distributions describe surface **area**, not percentage of vertices. Vertex counts remain separate descriptive fields.
- Uses the actual extracted and connected filtered mesh, rather than the pre-extraction logical mask, for Step 1's filtered statistics.
- Removes unqualified per-vertex 95% confidence intervals from exports and reports.
- Preserves the entire six-landmark anatomical classification algorithm in Step 2, including projection boundaries and vertical limits.

## Verification completed without patient data

- Python syntax compilation.
- Six numerical tests using synthetic meshes of known area and distances: area assignment, weighted mean/median/SD, histogram percentages, reference-band percentages, uniform weights, and missing data.
- A VTK smoke test using two concentric artificial spheres to execute Steps 1, 2 and 3 without the 3D Slicer interface.

Tests may be run with NumPy and VTK installed:

```bash
python -m unittest discover -s tests -v
```

## Required before a tagged release or Zenodo DOI

1. Load this scripted module into **3D Slicer 5.8.1** and run the three steps on synthetic meshes.
2. Visually verify the original six-landmark regional boundaries and confirm they are unchanged relative to the original implementation.
3. Inspect colour legends and exports (Excel, full PDF, summary PDF), including areas and continuous values.
4. Confirm behavior for empty regions, irregular/degenerate meshes and mesh repairs.
5. Independently review/confirm area weighting and weighted median conventions.
6. Ask the study's statistical analysts to verify whether the **Supplementary Table S6** results exist and how they were derived. This branch does not establish or reproduce those results.
7. Check author names, citation metadata and the data-sharing/ethics statement before creating an official GitHub release or Zenodo record.

**Do not claim that this branch has been clinically validated or that patient-level sensitivity analyses have been recomputed.**
