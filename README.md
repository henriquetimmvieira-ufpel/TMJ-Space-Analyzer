# TMJ Space Analyzer

An open-source, research-oriented **scripted module for 3D Slicer** to explore three-dimensional distances between the mandibular condyle and the articular fossa using segmented surface meshes from cone-beam computed tomography (CBCT).

> **Archived research implementation:** The original version used in the study is available as [v0.1.0](https://github.com/henriquetimmvieira-ufpel/TMJ-Space-Analyzer/releases/tag/v0.1.0) and archived on [Zenodo](https://doi.org/10.5281/zenodo.24286265). The current version, v0.2.0, is archived under DOI [10.5281/zenodo.24290837](https://doi.org/10.5281/zenodo.24290837).

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

1. Download `ATMJointSpaceAnalyzer.py` and `tmj_space_core.py` and keep both in the same folder.
2. In 3D Slicer, open **Edit → Application Settings → Modules** and add the folder containing the file to **Additional module paths**; restart Slicer if required.
3. Open **TMJ Space Analyzer** in the module selector.
4. If Excel or PDF export is unavailable, install the optional dependencies in Slicer's Python environment, for example from its Python console: `slicer.util.pip_install("openpyxl reportlab")`.

These steps describe manual loading of the scripted module; publishing through the official 3D Slicer Extensions Index has not been established.

## Current workflow

1. Load and select the **mandibular condyle** and **articular fossa** as model nodes. Choose the filtering cutoff and an export folder, then run **Step 1**.
2. Select **Create standard 6-point list** and place the landmarks in the exact order shown in the module: anterior limit, two anterior–middle boundary points, two middle–posterior boundary points, and posterior limit. Run **Step 2**.
3. Run **Step 3** to generate the regional summaries, experimental reference comparisons and reports.

For scientific replication, record acquisition parameters, segmentation protocol, mesh-preprocessing operations, landmark positions, software revision and filtering threshold.

## Research implementation notes

Version v0.1.0 preserves the original implementation: continuous distances are calculated and stored internally, while numerical summaries use vertex-based distances rounded to 0.25 mm (capped at 4.5 mm). Area-weighted statistics are not implemented in this version. The software-generated vertex-level confidence intervals should not be interpreted as patient-level inferential intervals.

The anterior, middle and posterior regions are defined using six manually placed anatomical landmarks, including user-defined anterior–middle and middle–posterior boundaries. Comparison with published linear reference values is exploratory and not clinically validated.

Version v0.2.0 computes all numerical summaries from the continuous point-to-surface
distances. The 0.25 mm discretisation and the 4.5 mm upper bound are applied only to the
colour display, so the reported maximum of the distance map is the true maximum.
Area-weighted descriptors are reported alongside the vertex-based ones, each vertex being
weighted by one third of the area of its incident triangles. The vertex-level confidence
intervals were removed, because neighbouring vertices are spatially autocorrelated and do
not constitute independent observations. The anterior, middle and posterior subdivisions
are referred to as regions rather than poles throughout the interface, reports and
spreadsheets. Values produced by v0.2.0 therefore differ from those produced by v0.1.0,
and the two versions should not be mixed within a single analysis.

## Batch re-analysis

`batch_step1.py` reproduces the stage-1 analysis for a folder of cases without the
graphical interface, requiring only the two STL meshes of each joint; landmark files are
not needed, because the regional subdivision belongs to stages 2 and 3. It writes one CSV
row per joint with the continuous, area-weighted and discretised statistics side by side.

    python batch_step1.py --root <folder> --list
    python batch_step1.py --root <folder> --out step1_continuous.csv

The computation is shared with the Slicer module through `tmj_space_core.py`, so batch and
interactive runs return identical values.

## Data and privacy

No identifiable CBCT scans or patient-derived meshes should be committed to this software repository. Any anonymised research meshes, landmarks and analysis datasets should be reviewed under the relevant ethics approval before deposit in a separate, versioned research-data archive.

## Citation and licence

See [CITATION.cff](CITATION.cff) for software citation metadata. The source is licensed under the [Apache License, Version 2.0](LICENSE). Cite the version actually used. The implementation used in the original study is v0.1.0,
archived under DOI [10.5281/zenodo.24286265](https://doi.org/10.5281/zenodo.24286265).
Version v0.2.0 is archived under DOI [10.5281/zenodo.24290837](https://doi.org/10.5281/zenodo.24290837),
and the concept DOI [10.5281/zenodo.24286264](https://doi.org/10.5281/zenodo.24286264) always resolves to the latest version.

## Project contact

Henrique Timm Vieira — Federal University of Pelotas (UFPel), Brazil.
