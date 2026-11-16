# Changelog

## v0.2.0

Statistical output of the module revised. The stage-1 and stage-3 descriptors are
now computed from the continuous point-to-surface distances; the 0.25 mm
discretisation and the 4.5 mm upper bound are applied only to the colour display.

### Changed
- **Continuous statistics.** All descriptors are computed from `RawAbsoluteDistance`.
  In v0.1.0 they were computed from `AbsoluteDistance`, which holds the values
  rounded to the nearest 0.25 mm and clipped at 4.5 mm.
- **No upper bound in the statistics.** The reported maximum of the global distance
  map is the true maximum. In v0.1.0 any distance above 4.5 mm was reported as 4.5 mm.
- **Area-weighted descriptors added.** Each vertex is weighted by one third of the
  area of its incident triangles, so the statistics no longer over-represent densely
  meshed areas. Both vertex-based and area-weighted values are reported, together
  with the surface area of each region.
- **Per-vertex 95% confidence intervals removed** from the reports and spreadsheets.
  Neighbouring vertices are spatially autocorrelated and are not independent
  observations, so the interval had no inferential meaning.
- **"Pole" renamed to "region"** throughout the interface, reports and spreadsheets.
  Worksheets `Step3_Poles` and `Step3_PoleDistribution` are now `Step3_Regions` and
  `Step3_RegionDistribution`; the column `Pole` is now `Region`; the column `N` is
  now `N_vertices`.
- **Distribution by ranges** additionally reports the area-weighted percentage.
- **Stage-1 filtered statistics use the filtered surface itself.** In v0.1.0 they were
  computed from every vertex at or below the cutoff, including small regions disconnected
  from the condylar surface; they now come from the largest connected region, the same
  surface that is displayed and carried into stages 2 and 3.

### Added
- `tmj_space_core.py` — geometry and statistics shared by the Slicer module and the
  batch script, so both produce identical numbers. Depends only on NumPy and VTK.
- `batch_step1.py` — headless stage-1 re-analysis from STL meshes, one CSV row per
  joint, reporting continuous, area-weighted and discretised statistics side by side.
  Landmark files are not required.

### Compatibility
v0.1.0 is the implementation used in the original study and remains archived. Because
v0.2.0 removes the rounding and the upper bound and adds area weighting, its values
differ from v0.1.0; the two versions should not be mixed within one analysis.

### Installation
`ATMJointSpaceAnalyzer.py` and `tmj_space_core.py` must sit in the same folder.
