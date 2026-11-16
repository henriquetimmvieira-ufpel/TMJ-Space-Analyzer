"""
tmj_space_core — geometry and statistics shared by the TMJ Space Analyzer
3D Slicer module and the headless batch script.

Depends only on NumPy and VTK, so it can be imported outside 3D Slicer.
Keeping these routines in one place guarantees that the interactive module
and the batch re-analysis produce identical numbers.
"""

import numpy as np
import vtk
from vtk.util.numpy_support import numpy_to_vtk, vtk_to_numpy

DISCRETISATION_STEP_MM = 0.25      # display granularity only
DISPLAY_MAX_MM = 4.5               # upper bound of the colour scale only


def preprocessPolyData(polydata):
    """Clean, triangulate and orient normals."""
    cleaner = vtk.vtkCleanPolyData()
    cleaner.SetInputData(polydata)
    cleaner.Update()

    triangulator = vtk.vtkTriangleFilter()
    triangulator.SetInputData(cleaner.GetOutput())
    triangulator.Update()

    normals = vtk.vtkPolyDataNormals()
    normals.SetInputData(triangulator.GetOutput())
    normals.AutoOrientNormalsOn()
    normals.ConsistencyOn()
    normals.SplittingOff()
    normals.Update()

    out = vtk.vtkPolyData()
    out.DeepCopy(normals.GetOutput())
    return out


def triangleIndices(polydata):
    """(n, 3) array of triangle vertex indices, or None."""
    polys = polydata.GetPolys() if polydata is not None else None
    if polys is None or polys.GetNumberOfCells() == 0:
        return None
    if hasattr(polys, "GetConnectivityArray") and hasattr(polys, "GetOffsetsArray"):
        conn = vtk_to_numpy(polys.GetConnectivityArray())
        offs = vtk_to_numpy(polys.GetOffsetsArray())
        starts = offs[:-1][np.diff(offs) == 3]
        if starts.size:
            return np.stack([conn[starts], conn[starts + 1], conn[starts + 2]], axis=1)
        return None
    ids = vtk.vtkIdList()
    collected = []
    for cellId in range(polys.GetNumberOfCells()):
        polydata.GetCellPoints(cellId, ids)
        if ids.GetNumberOfIds() == 3:
            collected.append([ids.GetId(0), ids.GetId(1), ids.GetId(2)])
    return np.asarray(collected, dtype=np.int64) if collected else None


def vertexAreasFromPolyData(polydata):
    """Area weight of each vertex: one third of the area of its incident triangles."""
    nPts = polydata.GetNumberOfPoints() if polydata is not None else 0
    areas = np.zeros(nPts, dtype=float)
    if nPts == 0:
        return areas
    tris = triangleIndices(polydata)
    if tris is None:
        return areas
    pts = vtk_to_numpy(polydata.GetPoints().GetData()).astype(float)
    a, b, c = pts[tris[:, 0]], pts[tris[:, 1]], pts[tris[:, 2]]
    third = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1) / 3.0
    np.add.at(areas, tris[:, 0], third)
    np.add.at(areas, tris[:, 1], third)
    np.add.at(areas, tris[:, 2], third)
    return areas


def weightedQuantile(values, weights, q):
    """Weighted quantile with linear interpolation of the weighted CDF."""
    v = np.asarray(values, dtype=float)
    w = np.asarray(weights, dtype=float)
    ok = np.isfinite(v) & np.isfinite(w) & (w > 0)
    v, w = v[ok], w[ok]
    if v.size == 0:
        return float("nan")
    order = np.argsort(v, kind="mergesort")
    v, w = v[order], w[order]
    cw = np.cumsum(w)
    total = cw[-1]
    if total <= 0:
        return float(np.median(v))
    return float(np.interp(q, (cw - 0.5 * w) / total, v))


def summaryStats(values, weights=None):
    """Vertex-based and, when weights are given, area-weighted descriptors (mm)."""
    v = np.asarray(values, dtype=float)
    finite = np.isfinite(v)
    v = v[finite]
    keys = ["Mean_mm", "SD_mm", "Median_mm", "Min_mm", "Max_mm",
            "Area_mm2", "MeanAreaWeighted_mm", "SDAreaWeighted_mm", "MedianAreaWeighted_mm"]
    out = {"N_vertices": int(v.size)}
    if v.size == 0:
        out.update({k: None for k in keys})
        return out
    out.update({
        "Mean_mm": float(np.mean(v)),
        "SD_mm": float(np.std(v, ddof=0)),
        "Median_mm": float(np.median(v)),
        "Min_mm": float(np.min(v)),
        "Max_mm": float(np.max(v)),
    })
    if weights is None:
        out.update({k: None for k in keys[5:]})
        return out
    w = np.asarray(weights, dtype=float)
    if w.size == finite.size:
        w = w[finite]
    w = np.where(np.isfinite(w) & (w > 0), w, 0.0)
    if w.size != v.size or float(w.sum()) <= 0:
        out.update({k: None for k in keys[5:]})
        return out
    total = float(w.sum())
    wMean = float(np.sum(w * v) / total)
    out.update({
        "Area_mm2": total,
        "MeanAreaWeighted_mm": wMean,
        "SDAreaWeighted_mm": float(np.sqrt(np.sum(w * (v - wMean) ** 2) / total)),
        "MedianAreaWeighted_mm": weightedQuantile(v, w, 0.5),
    })
    return out


def discretise(values, step=DISCRETISATION_STEP_MM, displayMax=DISPLAY_MAX_MM):
    """Display-only transform: nearest multiple of `step`, clipped to the colour scale."""
    return np.clip(np.round(np.asarray(values, dtype=float) / step) * step, 0.0, displayMax)


def readSTL(path):
    reader = vtk.vtkSTLReader()
    reader.SetFileName(path)
    reader.Update()
    out = vtk.vtkPolyData()
    out.DeepCopy(reader.GetOutput())
    return out


def thresholdByPointScalar(polydata, scalarName, upperValue, lowerValue=0.0):
    thresh = vtk.vtkThreshold()
    thresh.SetInputData(polydata)
    thresh.SetInputArrayToProcess(0, 0, 0, vtk.vtkDataObject.FIELD_ASSOCIATION_POINTS, scalarName)
    thresh.SetLowerThreshold(lowerValue)
    thresh.SetUpperThreshold(upperValue)
    thresh.SetThresholdFunction(vtk.vtkThreshold.THRESHOLD_BETWEEN)
    thresh.Update()
    geo = vtk.vtkGeometryFilter()
    geo.SetInputData(thresh.GetOutput())
    geo.Update()
    out = vtk.vtkPolyData()
    out.DeepCopy(geo.GetOutput())
    return out


def extractLargestRegion(polydata):
    conn = vtk.vtkConnectivityFilter()
    conn.SetInputData(polydata)
    conn.SetExtractionModeToLargestRegion()
    conn.Update()
    geo = vtk.vtkGeometryFilter()
    geo.SetInputData(conn.GetOutput())
    geo.Update()
    out = vtk.vtkPolyData()
    out.DeepCopy(geo.GetOutput())
    return out


def unsignedDistanceToSurface(sourcePoly, targetPoly):
    """Unsigned point-to-surface distance (mm) from every vertex of source to target."""
    f = vtk.vtkDistancePolyDataFilter()
    f.SetInputData(0, sourcePoly)
    f.SetInputData(1, targetPoly)
    f.SignedDistanceOff()
    f.ComputeSecondDistanceOff()
    f.Update()
    out = vtk.vtkPolyData()
    out.DeepCopy(f.GetOutput())
    scalars = out.GetPointData().GetScalars()
    if scalars is None:
        raise RuntimeError("Distance scalar generation failed.")
    return out, np.abs(vtk_to_numpy(scalars))


def computeStep1(condylePoly, fossaPoly, cutoffMm=5.0):
    """Stage-1 analysis: global distance map and filtered functional surface.

    Statistics are computed on the continuous distances; the discretised
    values are produced only for the colour display.
    """
    condylePoly = preprocessPolyData(condylePoly)
    fossaPoly = preprocessPolyData(fossaPoly)

    mapPoly, raw = unsignedDistanceToSurface(condylePoly, fossaPoly)

    # Same array type as the Slicer module (double), so thresholding is identical.
    rawArray = numpy_to_vtk(np.ascontiguousarray(raw, dtype=np.float64), deep=True)
    rawArray.SetName("RawAbsoluteDistance")
    mapPoly.GetPointData().AddArray(rawArray)

    globalAreas = vertexAreasFromPolyData(mapPoly)

    filteredPoly = extractLargestRegion(
        thresholdByPointScalar(mapPoly, "RawAbsoluteDistance", cutoffMm))
    filteredArr = filteredPoly.GetPointData().GetArray("RawAbsoluteDistance")
    if filteredArr is None:
        raise RuntimeError("The filtered condylar surface lost the RawAbsoluteDistance array.")
    filtered = vtk_to_numpy(filteredArr)
    filteredAreas = vertexAreasFromPolyData(filteredPoly)

    return {
        "global": summaryStats(raw, globalAreas),
        "filtered": summaryStats(filtered, filteredAreas),
        "global_discretised": summaryStats(discretise(raw)),
        "filtered_discretised": summaryStats(discretise(filtered)),
        "cutoff_mm": float(cutoffMm),
        "n_capped_vertices": int(np.sum(filtered > DISPLAY_MAX_MM)),
        "percent_capped": float(100.0 * np.sum(filtered > DISPLAY_MAX_MM) / len(filtered)) if len(filtered) else 0.0,
    }
