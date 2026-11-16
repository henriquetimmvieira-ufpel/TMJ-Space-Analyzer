# Checklist before the archival v1.0.0 release

This checklist captures differences identified between the **uploaded Python source of 16 November 2026** and the methods promised in the revised TMJ Space Analyzer manuscript. Items are **not** claims that work has already been completed.

- [ ] Implement and validate continuous-distance statistics (no 0.25-mm rounding or 4.5-mm upper cap for calculation).
- [ ] Implement and validate area-weighted regional statistics; specify the precise treatment of triangle areas and region boundaries.
- [ ] Remove or clearly restrict the per-vertex confidence intervals so that spatially correlated vertices are not treated as independent subjects.
- [x] Reconcile the six-landmark subdivision description with the original code: user-defined anterior–middle and middle–posterior boundaries and landmark-derived vertical cutoffs. The revised manuscript now describes these correctly. Preserve the Stage 2 algorithm in future updates.
- [ ] Ensure experimental comparisons with linear reference values are explicitly labelled **experimental / not clinically validated** in the UI and reports.
- [ ] Test the implementation on anonymised study meshes and compare reproducibility, mean/median/minimum values, and sensitivity analyses against the paper's final results.
- [ ] Record the 3D Slicer version, dependencies, installation requirements and automated or manual validation procedure.
- [ ] Review the copyright holder, software authors and contributors; expand CITATION.cff as appropriate before release.
- [ ] Confirm the research-data deposit is anonymous, authorised by ethics approval and separately citable.
- [ ] Verify README and exported reports against the released code.
- [ ] Activate GitHub–Zenodo integration, then create a **v1.0.0** GitHub release; confirm the archived artifact and version-specific DOI.
- [ ] Insert the verified GitHub URL and Zenodo DOI into the manuscript and response to reviewers.

**Do not create the DOI-bearing scientific release until these checks are complete.**
