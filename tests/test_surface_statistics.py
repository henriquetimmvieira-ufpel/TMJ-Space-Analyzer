"""Tests for continuous area-weighted TMJ surface statistics.

Run in Python with numpy and VTK installed:
    python -m unittest discover -s tests -v
"""
import ast
from pathlib import Path
import unittest

import numpy as np
import vtk
from vtk.util.numpy_support import vtk_to_numpy

SOURCE = Path(__file__).resolve().parents[1] / "ATMJointSpaceAnalyzer.py"
tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
sourceClass = next(x for x in tree.body if isinstance(x, ast.ClassDef) and x.name == "ATMJointSpaceAnalyzerLogic")
methods = [x for x in sourceClass.body if isinstance(x, ast.FunctionDef) and x.name in {
    "vertexAreaWeights", "weightedStats", "computeRangeDistribution", "computePoleDeltaDistribution"
}]
subset = ast.ClassDef(name="Stats", bases=[], keywords=[], body=methods, decorator_list=[])
module = ast.fix_missing_locations(ast.Module(body=[subset], type_ignores=[]))
environment = {"np": np, "vtk": vtk, "vtk_to_numpy": vtk_to_numpy}
exec(compile(module, str(SOURCE), "exec"), environment)
logic = environment["Stats"]()


def mesh():
    # First triangle area=2 mm2; second triangle area=0.5 mm2.
    vertices = [(0, 0, 0), (2, 0, 0), (0, 2, 0),
                (4, 0, 0), (5, 0, 0), (4, 1, 0)]
    poly = vtk.vtkPolyData()
    points = vtk.vtkPoints()
    for p in vertices:
        points.InsertNextPoint(*p)
    poly.SetPoints(points)
    cells = vtk.vtkCellArray()
    for triangle in [(0, 1, 2), (3, 4, 5)]:
        c = vtk.vtkTriangle()
        for i, v in enumerate(triangle):
            c.GetPointIds().SetId(i, v)
        cells.InsertNextCell(c)
    poly.SetPolys(cells)
    return poly


class SurfaceStatisticsTests(unittest.TestCase):
    def setUp(self):
        self.weights = logic.vertexAreaWeights(mesh())
        self.distances = np.array([1.0] * 3 + [3.0] * 3)

    def test_triangle_areas(self):
        np.testing.assert_allclose(self.weights, [2/3]*3 + [0.5/3]*3)
        self.assertAlmostEqual(self.weights.sum(), 2.5)

    def test_area_weighted_mean_median_and_sd(self):
        values = logic.weightedStats(self.distances, self.weights)
        self.assertEqual(values["N"], 6)
        self.assertAlmostEqual(values["Mean_mm"], 1.4)
        self.assertAlmostEqual(values["Median_mm"], 1.0)
        self.assertAlmostEqual(values["SD_mm"], 0.8)
        self.assertNotIn("CI95_low_mm", values)

    def test_histogram_uses_area_not_point_counts(self):
        bins = logic.computeRangeDistribution(self.distances, [(0, 2), (2, 4)], self.weights)
        self.assertEqual([item["Count"] for item in bins], [3, 3])
        np.testing.assert_allclose([item["Percent"] for item in bins], [80, 20])

    def test_reference_category_percentages_use_area(self):
        result = logic.computePoleDeltaDistribution(self.distances - 2, self.weights)
        self.assertAlmostEqual(result["BelowExpected_Percent"], 80)
        self.assertAlmostEqual(result["AboveExpected_Percent"], 20)

    def test_uniform_weight_median(self):
        result = logic.weightedStats([1, 2, 3, 4], [1, 1, 1, 1])
        self.assertAlmostEqual(result["Median_mm"], 2.5)

    def test_missing_and_empty_values(self):
        result = logic.weightedStats([2, np.nan], [1, 1])
        self.assertEqual(result["N"], 1)
        self.assertEqual(result["Mean_mm"], 2)
        self.assertEqual(logic.weightedStats([], [])["N"], 0)


if __name__ == "__main__":
    unittest.main()
