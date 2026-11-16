# TMJ Space Analyzer

An open-source, research-oriented **scripted module for 3D Slicer** to explore three-dimensional distances between the mandibular condyle and the articular fossa using segmented surface meshes from cone-beam computed tomography (CBCT).

> **Development snapshot:** This repository currently contains the original `ATMJointSpaceAnalyzer.py` supplied on 16 November 2026. It is **not yet the validated version 1.0.0** described in the revised manuscript. Please read the [release checklist](docs/RELEASE_CHECKLIST.md) before treating the software as a reproducible scientific release.

## Current features

- Imports condylar and articular-fossa models already loaded in the 3D Slicer scene.
- Computes unsigned point-to-surface distances with VTK (`vtkDistancePolyDataFilter`).
- Filters the condylar surface by a configurable distance cutoff (default: 5 mm).
- Divides the filtered surface into anterior, middle and posterior regions using **six manually placed landmarks**.
- Exports distance summaries, regional comparisons, screenshots, Excel workbooks and PDF reports.
- Displays exploratory comparisons against adjustable values derived from **linear** joint-space measurements.

**Important:** This is a methodological research tool. The reference-value comparisons are experimental and **are not validated diagnostic thresholds**. It is not intended to guide clinical treatment decisions.

## Requirements

- [3D Slicer](https://www.slicer.org/) with its embedded Python, NumPy and VTK.
- Optional Python packages: `openpyxl` (Excel export) and `reportlab` (PDF export).
- Two surface model nodes: mandibular condyle and articular fossa, segmented and prepared before analysis.

## Installation

1. Download `ATMJointSpaceAnalyzer.py`.
2. In 3D Slicer, open **Edit → Application Settings → Modules** and add the folder containing the file to **Additional module paths**; restart Slicer if required.
3. Open **ATM Joint Space Analyzer** in the module selector.
4. If Excel or PDF export is unavailable, install the optional dependencies in Slicer's Python environment, for example from its Python console: `slicer.util.pip_install("openpyxl reportlab")`.

These steps describe manual loading of the development snapshot; publishing through the official 3D Slicer Extensions Index has not been established.

## Current workflow

1. Load and select the **mandibular condyle** and **articular fossa** as model nodes. Choose the filtering cutoff and an export folder, then run **Step 1**.
2. Select **Create standard 6-point list** and place the landmarks in the exact order shown in the module: anterior limit, two anterior–middle boundary points, two middle–posterior boundary points, and posterior limit. Run **Step 2**.
3. Run **Step 3** to generate the regional summaries, experimental reference comparisons and reports.

For scientific replication, record acquisition parameters, segmentation protocol, mesh-preprocessing operations, landmark positions, software revision and filtering threshold.

## Status and methodological caveats

**The uploaded source and the revised manuscript are not yet fully aligned.** In this snapshot:

- Continuous raw distances are stored, but the reported summary statistics use vertex-level distances rounded to 0.25 mm and capped at 4.5 mm for the colour scale.
- Regional statistics are not currently weighted by mesh area.
- Per-vertex 95% confidence intervals are generated, although neighbouring mesh vertices are not independent observations. These are **not valid patient-level inferential confidence intervals**.
- The six-landmark regional subdivision uses manually selected anterior–middle and middle–posterior boundary points, not the equal-thirds geometric definition currently proposed in the revised manuscript.
- The experimental comparisons against prior linear reference values are still exposed in the interface.

Until the revised implementation is validated on the study data, **do not cite this repository state as the final, continuous, area-weighted research release**. See [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md).

## Data and privacy

No identifiable CBCT scans or patient-derived meshes should be committed to this software repository. Any anonymised research meshes, landmarks and analysis datasets should be reviewed under the relevant ethics approval before deposit in a separate, versioned research-data archive.

## Citation and licence

See [CITATION.cff](CITATION.cff) for software citation metadata. The source is licensed under the [Apache License, Version 2.0](LICENSE). A DOI will be added only after a verified versioned release has been archived.

## Project contact

Henrique Timm Vieira — Federal University of Pelotas (UFPel), Brazil.
