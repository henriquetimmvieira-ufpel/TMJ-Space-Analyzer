# Preparation for Zenodo archival and manuscript revision

Status: **not released**. This document distinguishes what is ready from what still requires confirmation. Do not present this repository as a validated v1.0.0 release until the checks below are complete.

## 1. Current repository structure

- Public source: https://github.com/henriquetimmvieira-ufpel/TMJ-Space-Analyzer
- Default `main`: original 2026 research implementation, preserved for provenance.
- Draft pull request for updated continuous, area-weighted statistics: https://github.com/henriquetimmvieira-ufpel/TMJ-Space-Analyzer/pull/1
- Licence: Apache License, Version 2.0 (`LICENSE`).
- Citation metadata: `CITATION.cff`; **software authorship must be confirmed with the study team before release**.
- No repository release, Zenodo archive or DOI has been issued as of this preparation document.

## 2. Enable GitHub archiving in Zenodo — safe to do before release

1. Sign in to https://zenodo.org/ and connect your GitHub account under Profile → Linked accounts if it is not already linked.
2. Open the Zenodo profile menu → **GitHub**.
3. Click **Sync now**.
4. Find **henriquetimmvieira-ufpel/TMJ-Space-Analyzer**, enable the repository using the toggle, and refresh the page.
5. Do **not** publish a GitHub release yet. Enabling this integration alone does not publish or archive the current development version.

Official guide: https://help.zenodo.org/docs/github/enable-repository/

Zenodo will use `CITATION.cff` metadata for GitHub releases. We intentionally do not add a `.zenodo.json` because it would override the citation metadata. Reference: https://help.zenodo.org/docs/github/describe-software/citation-file/

## 3. Scientific and technical release gate

- [x] Preserve original source implementation for provenance.
- [x] Open and document the revised, continuous/area-weighted code in an independent draft PR.
- [x] Validate numerical calculations with synthetic VTK meshes and verify representative report exports offline.
- [x] Keep the six-landmark region subdivision exactly as implemented in the original source.
- [ ] Test the modified module interactively inside 3D Slicer 5.8.1 (UI, landmarks, colour legends and Excel/PDF exports).
- [ ] Resolve any software defects found during interactive testing.
- [ ] Confirm software authors and citation order; add verified coauthors to `CITATION.cff`, if applicable. Do not invent ORCIDs.
- [ ] Obtain scientific confirmation that the claims in the revised manuscript about Supplementary Table S6 correspond to analyses performed by the statistical team. This is **not** generated from the synthetic software tests.
- [ ] Confirm the original manuscript's version and software statements match the verified release.
- [ ] Decide whether there are eligible, de-identified surface meshes or landmarks for a **separate** dataset. Do not say such files were deposited unless they exist and their sharing is authorised.
- [ ] Approve the final source in the draft PR and merge it into `main`.
- [ ] Confirm that `main` is exactly the state intended for archival publication.

## 4. Create the software release only after approval

1. Confirm that GitHub–Zenodo integration is enabled.
2. On GitHub, open the repository → **Releases** → **Draft a new release**.
3. Create the tag `v1.0.0` from the verified `main` commit, title **TMJ Space Analyzer v1.0.0**.
4. In the release notes, distinguish the original discretised version used for the study from the new continuous area-weighted reporting version. State clearly that reference-value comparison is experimental and not clinically validated.
5. Publish the release; Zenodo will archive it and assign its DOI. Verify the archived version, files and creator metadata.
6. Insert the real DOI and GitHub URL into the manuscript and reviewer response — no placeholders.

Official guide: https://help.zenodo.org/docs/github/archive-software/github-upload/

## 5. Proposed software deposit description

**Title:** TMJ Space Analyzer — Open-source 3D Slicer module for regional analysis of temporomandibular joint space on CBCT

**Resource type:** Software

**Description:** TMJ Space Analyzer is a research-oriented scripted 3D Slicer module that computes three-dimensional distances between the mandibular condyle and the articular fossa from prepared CBCT-derived surface meshes. It provides colour-mapped visualisation, a semi-automated subdivision into anterior, middle and posterior regions based on six operator-placed anatomical landmarks, regional descriptive statistics and report exports. The research implementation used discretised distances for both visualisation and statistics; the proposed updated implementation retains discretisation only for the colour display and calculates descriptive statistics from continuous distances weighted by surface area. Reference-value comparisons derived from linear methods are experimental and have not been validated for clinical diagnosis.

**Licence:** Apache-2.0

**Keywords:** temporomandibular joint; CBCT; cone-beam computed tomography; 3D Slicer; anatomical landmarks; open-source software; surface distance; regional analysis

**Creators:** Confirm with all authors before the release. Current `CITATION.cff` lists Henrique Timm Vieira, Federal University of Pelotas (UFPel), Brazil. This is not a determination of sole ownership or software authorship.

## 6. Data availability and ethics

A software archive is different from a research-data archive. The clinical study's exported spreadsheets, original segmentations, STLs and landmark files should not be assumed available merely because the source code is public. A separate Zenodo dataset, if created, must be genuinely available, appropriately anonymised, and consistent with ethics approval and institutional data-sharing requirements.

Do not claim that missing DICOM, STL, landmarks or patient-specific segmentation thresholds are available in Zenodo. If only aggregate analysis outputs are preserved, document their actual contents accurately. Statistical sensitivity results and Supplementary Tables S4/S6 remain the study authors' responsibility.

## 7. Before submission

- [ ] Verify Zenodo's **version-specific DOI**, not a guessed number.
- [ ] Verify the released `ATMJointSpaceAnalyzer.py` matches the manuscript's method description.
- [ ] Verify supplementary material availability and data availability statement with the authors.
- [ ] Update journal/manuscript links only after those checks.
