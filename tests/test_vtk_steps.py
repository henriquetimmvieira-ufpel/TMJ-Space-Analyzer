"""Offline synthetic-mesh smoke test for Steps 1-3 using real VTK.

This is not a substitute for testing the module inside 3D Slicer with actual
clinical surfaces. Run with: python -m unittest discover -s tests -v
"""
import ast
from pathlib import Path
import unittest
import numpy as np
import vtk
from vtk.util.numpy_support import vtk_to_numpy, numpy_to_vtk

SOURCE = Path(__file__).resolve().parents[1] / "ATMJointSpaceAnalyzer.py"
tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
logicClass = next(x for x in tree.body if isinstance(x, ast.ClassDef) and x.name == "ATMJointSpaceAnalyzerLogic")
logicClass.bases = [ast.Name(id="object", ctx=ast.Load())]
namespace = {"np": np, "vtk": vtk, "vtk_to_numpy": vtk_to_numpy,
             "numpy_to_vtk": numpy_to_vtk, "ScriptedLoadableModuleLogic": object,
             "OPENPYXL_AVAILABLE": False, "REPORTLAB_AVAILABLE": False}
exec(compile(ast.fix_missing_locations(ast.Module(body=[logicClass], type_ignores=[])), str(SOURCE), "exec"), namespace)
Logic = namespace["ATMJointSpaceAnalyzerLogic"]


class Node:
    def __init__(self, poly=None): self.poly = poly
    def GetPolyData(self): return self.poly
    def SetAndObservePolyData(self, poly): self.poly = poly


class Legend:
    def SetVisibility(self, visible): pass


def sphere(radius):
    source = vtk.vtkSphereSource()
    source.SetRadius(radius)
    source.SetThetaResolution(48)
    source.SetPhiResolution(24)
    source.Update()
    return source.GetOutput()


class ModuleSmokeTests(unittest.TestCase):
    def test_three_stages(self):
        logic = Logic()
        nodes = {}

        def create(name):
            if name not in nodes: nodes[name] = Node()
            return nodes[name]

        logic.createOrGetModelNode = create
        logic.getNode = lambda name: nodes[name]
        logic.createOrUpdateDiscreteDistanceColorNode = lambda: object()
        logic.createOrUpdateDiscreteReferenceComparisonColorNode = lambda: object()
        logic.setModelDisplayWithColorNode = lambda *a, **kw: None
        logic.setModelDisplay = lambda *a, **kw: None
        logic.addOrUpdateColorLegend = lambda *a, **kw: Legend()
        logic.forceRender = lambda: None
        logic.showOnlyFinalComparison = lambda: None
        logic.createLineMarkup = lambda *a, **kw: None
        logic.getFiducialPoints = lambda *a, **kw: [
            np.array([0, 10, 0.]), np.array([-4, 4, 0.]), np.array([4, 4, 0.]),
            np.array([-4, -4, 0.]), np.array([4, -4, 0.]), np.array([0, -10, 0.])
        ]

        step1 = logic.runStep1(Node(sphere(10)), Node(sphere(12)), cutoffMm=5)
        self.assertGreater(step1["filtered_n"], 100)
        self.assertAlmostEqual(step1["filtered_mean"], 2, delta=0.5)
        self.assertNotIn("CI95", str(step1["step1_rows"]))

        step2 = logic.runStep2("CondyleFiltered_lt5mm", object())
        self.assertGreater(step2["n_anterior"], 0)
        self.assertGreater(step2["n_middle"], 0)
        self.assertGreater(step2["n_posterior"], 0)

        step3 = logic.runStep3("Condyle_AP_Manual_6pts", {1: 2.1, 2: 2.5, 3: 1.3})
        self.assertEqual(len(step3["rows"]), 3)
        self.assertTrue(all(row["area_mm2"] > 0 for row in step3["rows"]))
        self.assertTrue(all(0 < row["mean_mm"] < 5 for row in step3["rows"]))
        self.assertNotIn("95% CI", step3["text"])


if __name__ == "__main__":
    unittest.main()
