import os
import math
import numpy as np
import vtk

import qt
import ctk

from vtk.util.numpy_support import vtk_to_numpy, numpy_to_vtk

import sys as _sys
_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
if _MODULE_DIR not in _sys.path:
    _sys.path.insert(0, _MODULE_DIR)
from tmj_space_core import (
    vertexAreasFromPolyData as _vertexAreas,
    weightedQuantile as _weightedQuantile,
    summaryStats as _summaryStats,
    discretise as _discretise,
)

import slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin

# -----------------------------
# Optional dependencies
# -----------------------------
OPENPYXL_AVAILABLE = True
try:
    from openpyxl import Workbook, load_workbook
    from openpyxl.styles import Font
except ImportError:
    OPENPYXL_AVAILABLE = False

REPORTLAB_AVAILABLE = True
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
except ImportError:
    REPORTLAB_AVAILABLE = False


#
# ATMJointSpaceAnalyzer
#

class ATMJointSpaceAnalyzer(ScriptedLoadableModule):
    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        parent.title = "TMJ Space Analyzer"
        parent.categories = ["Examples"]
        parent.dependencies = []
        parent.contributors = ["Gabriela Schneid Rios", "Henrique Timm Vieira", "Noeli Boscato (UFPel)"]
        parent.helpText = """
TMJ Space Analyzer (v0.2.0)

Module for TMJ joint space analysis:
1. distance map + functional condylar surface filtering
2. manual segmentation into anterior / middle / posterior regions
3. filtered overall statistics + region-based statistics + reference comparison map
4. automatic export of standardized 3D screenshots in JPG
5. automatic export of Step 1 and Step 3 statistics to Excel
6. automatic export of final PDF report
"""
        parent.acknowledgementText = ""


#
# ATMJointSpaceAnalyzerWidget
#

class ATMJointSpaceAnalyzerWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
    def __init__(self, parent=None):
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)
        self.logic = None

        self.pointLabels = [
            "Anterior",
            "AM_mesial",
            "AM_distal",
            "MP_mesial",
            "MP_distal",
            "Posterior"
        ]

        self.pointDescriptions = [
            "Most anterior limit point of the anterior condylar region.",
            "Point at the anterior–middle boundary on the most mesial aspect of the mandibular condyle.",
            "Point at the anterior–middle boundary on the most distal/lateral aspect of the mandibular condyle.",
            "Point at the middle–posterior boundary on the most mesial aspect of the mandibular condyle.",
            "Point at the middle–posterior boundary on the most distal/lateral aspect of the mandibular condyle.",
            "Most posterior limit point of the posterior condylar region."
        ]

        self.markupObserverTag = None
        self.activeMarkupNode = None

    def setup(self):
        ScriptedLoadableModuleWidget.setup(self)
        self.logic = ATMJointSpaceAnalyzerLogic()

        parametersCollapsibleButton = ctk.ctkCollapsibleButton()
        parametersCollapsibleButton.text = "Parameters"
        self.layout.addWidget(parametersCollapsibleButton)

        parametersFormLayout = qt.QFormLayout(parametersCollapsibleButton)

        self.sourceSelector = slicer.qMRMLNodeComboBox()
        self.sourceSelector.nodeTypes = ["vtkMRMLModelNode"]
        self.sourceSelector.selectNodeUponCreation = True
        self.sourceSelector.addEnabled = False
        self.sourceSelector.removeEnabled = False
        self.sourceSelector.noneEnabled = False
        self.sourceSelector.setMRMLScene(slicer.mrmlScene)
        self.sourceSelector.setToolTip("Select the mandibular condyle model")
        parametersFormLayout.addRow("Mandibular condyle:", self.sourceSelector)

        self.targetSelector = slicer.qMRMLNodeComboBox()
        self.targetSelector.nodeTypes = ["vtkMRMLModelNode"]
        self.targetSelector.selectNodeUponCreation = True
        self.targetSelector.addEnabled = False
        self.targetSelector.removeEnabled = False
        self.targetSelector.noneEnabled = False
        self.targetSelector.setMRMLScene(slicer.mrmlScene)
        self.targetSelector.setToolTip("Select the articular cavity model")
        parametersFormLayout.addRow("Articular cavity:", self.targetSelector)

        self.markupSelector = slicer.qMRMLNodeComboBox()
        self.markupSelector.nodeTypes = ["vtkMRMLMarkupsFiducialNode"]
        self.markupSelector.selectNodeUponCreation = True
        self.markupSelector.addEnabled = True
        self.markupSelector.renameEnabled = True
        self.markupSelector.removeEnabled = False
        self.markupSelector.noneEnabled = True
        self.markupSelector.setMRMLScene(slicer.mrmlScene)
        self.markupSelector.setToolTip("Six-point landmark list")
        parametersFormLayout.addRow("Landmark list:", self.markupSelector)

        self.createPointsButton = qt.QPushButton("Create standard 6-point list")
        self.createPointsButton.toolTip = "Create an empty 6-point landmark list and activate point placement"
        self.createPointsButton.connect("clicked(bool)", self.onCreatePoints)
        parametersFormLayout.addRow(self.createPointsButton)

        self.cutoffSpinBox = qt.QDoubleSpinBox()
        self.cutoffSpinBox.minimum = 0.1
        self.cutoffSpinBox.maximum = 20.0
        self.cutoffSpinBox.singleStep = 0.1
        self.cutoffSpinBox.value = 5.0
        parametersFormLayout.addRow("Filtering cutoff (mm):", self.cutoffSpinBox)

        self.refAnteriorSpinBox = qt.QDoubleSpinBox()
        self.refAnteriorSpinBox.minimum = 0.0
        self.refAnteriorSpinBox.maximum = 20.0
        self.refAnteriorSpinBox.value = 1.3
        parametersFormLayout.addRow("Anterior reference (mm):", self.refAnteriorSpinBox)

        self.refMedioSpinBox = qt.QDoubleSpinBox()
        self.refMedioSpinBox.minimum = 0.0
        self.refMedioSpinBox.maximum = 20.0
        self.refMedioSpinBox.value = 2.5
        parametersFormLayout.addRow("Middle reference (mm):", self.refMedioSpinBox)

        self.refPosteriorSpinBox = qt.QDoubleSpinBox()
        self.refPosteriorSpinBox.minimum = 0.0
        self.refPosteriorSpinBox.maximum = 20.0
        self.refPosteriorSpinBox.value = 2.1
        parametersFormLayout.addRow("Posterior reference (mm):", self.refPosteriorSpinBox)

        self.exportFolderEdit = qt.QLineEdit()
        self.exportFolderEdit.setText(os.path.join(os.path.expanduser("~"), "Desktop", "ATMJointSpaceExports"))
        self.exportFolderEdit.setToolTip("Folder where JPG screenshots, Excel, and PDF will be exported")
        parametersFormLayout.addRow("Export folder:", self.exportFolderEdit)

        step1Button = ctk.ctkCollapsibleButton()
        step1Button.text = "Step 1 — Distance map and filtering"
        self.layout.addWidget(step1Button)
        step1Layout = qt.QVBoxLayout(step1Button)

        self.runStep1Button = qt.QPushButton("Run Step 1")
        self.runStep1Button.connect("clicked(bool)", self.onRunStep1)
        step1Layout.addWidget(self.runStep1Button)

        step2Button = ctk.ctkCollapsibleButton()
        step2Button.text = "Step 2 — Landmark placement and region segmentation"
        self.layout.addWidget(step2Button)
        step2Layout = qt.QVBoxLayout(step2Button)

        self.instructionsLabel = qt.QLabel(
            "Place 6 landmarks in this exact order:\n\n"
            "1. Anterior — Most anterior limit point of the anterior condylar region.\n"
            "2. AM_mesial — Point at the anterior–middle boundary on the most mesial aspect of the condyle.\n"
            "3. AM_distal — Point at the anterior–middle boundary on the most distal/lateral aspect of the condyle.\n"
            "4. MP_mesial — Point at the middle–posterior boundary on the most mesial aspect of the condyle.\n"
            "5. MP_distal — Point at the middle–posterior boundary on the most distal/lateral aspect of the condyle.\n"
            "6. Posterior — Most posterior limit point of the posterior condylar region."
        )
        self.instructionsLabel.setWordWrap(True)
        step2Layout.addWidget(self.instructionsLabel)

        self.currentPointLabel = qt.QLabel("Current point to place: none")
        self.currentPointLabel.setStyleSheet(
            "font-weight: bold; color: darkred; padding: 6px; background-color: #f5f5f5;"
        )
        self.currentPointLabel.setWordWrap(True)
        step2Layout.addWidget(self.currentPointLabel)

        self.runStep2Button = qt.QPushButton("Run Step 2")
        self.runStep2Button.connect("clicked(bool)", self.onRunStep2)
        step2Layout.addWidget(self.runStep2Button)

        step3Button = ctk.ctkCollapsibleButton()
        step3Button.text = "Step 3 — Final statistics and reference comparison"
        self.layout.addWidget(step3Button)
        step3Layout = qt.QVBoxLayout(step3Button)

        self.runStep3Button = qt.QPushButton("Run Step 3")
        self.runStep3Button.connect("clicked(bool)", self.onRunStep3)
        step3Layout.addWidget(self.runStep3Button)

        self.outputText = qt.QPlainTextEdit()
        self.outputText.readOnly = True
        step3Layout.addWidget(self.outputText)

        self.layout.addStretch(1)

    def cleanup(self):
        self.removeMarkupObserver()
        if hasattr(self, "currentPointLabel"):
            self.currentPointLabel.setText("Current point to place: none")

    def log(self, text):
        self.outputText.appendPlainText(text)
        print(text)

    def removeMarkupObserver(self):
        if self.activeMarkupNode is not None and self.markupObserverTag is not None:
            try:
                self.activeMarkupNode.RemoveObserver(self.markupObserverTag)
            except Exception:
                pass
        self.markupObserverTag = None
        self.activeMarkupNode = None

    def onPointPlaced(self, caller, event=None):
        if self.activeMarkupNode is None:
            return

        n = self.activeMarkupNode.GetNumberOfControlPoints()

        for i in range(min(n, len(self.pointLabels))):
            self.activeMarkupNode.SetNthControlPointLabel(i, self.pointLabels[i])

        if n < len(self.pointLabels):
            self.currentPointLabel.setText(
                f"Current point to place:\n{self.pointLabels[n]} — {self.pointDescriptions[n]}"
            )
        else:
            self.currentPointLabel.setText("All 6 points placed successfully.")
            interactionNode = slicer.app.applicationLogic().GetInteractionNode()
            interactionNode.SetPlaceModePersistence(0)
            interactionNode.SetCurrentInteractionMode(interactionNode.ViewTransform)
            self.removeMarkupObserver()
            slicer.util.infoDisplay("All 6 landmarks were placed successfully.")

    def onCreatePoints(self):
        self.removeMarkupObserver()

        node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode", "ATM_6pts")
        self.markupSelector.setCurrentNode(node)
        self.activeMarkupNode = node

        self.markupObserverTag = node.AddObserver(
            slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent,
            self.onPointPlaced
        )

        selectionNode = slicer.app.applicationLogic().GetSelectionNode()
        interactionNode = slicer.app.applicationLogic().GetInteractionNode()

        selectionNode.SetReferenceActivePlaceNodeClassName("vtkMRMLMarkupsFiducialNode")
        selectionNode.SetActivePlaceNodeID(node.GetID())

        interactionNode.SetPlaceModePersistence(1)
        interactionNode.SetCurrentInteractionMode(interactionNode.Place)

        self.currentPointLabel.setText(
            f"Current point to place:\n{self.pointLabels[0]} — {self.pointDescriptions[0]}"
        )

        slicer.util.infoDisplay(
            "ATM_6pts created.\n"
            "Click 6 times on the model following the displayed order."
        )

    def onRunStep1(self):
        sourceNode = self.sourceSelector.currentNode()
        targetNode = self.targetSelector.currentNode()
        if not sourceNode or not targetNode:
            slicer.util.errorDisplay("Please select both the mandibular condyle and the articular cavity.")
            return

        try:
            result = self.logic.runStep1(
                sourceNode=sourceNode,
                targetNode=targetNode,
                cutoffMm=self.cutoffSpinBox.value,
                exportFolder=self.exportFolderEdit.text
            )
            slicer.util.infoDisplay("Step 1 completed.")
            self.log("Step 1 completed.")
            self.log(str(result))
        except Exception as e:
            slicer.util.errorDisplay(f"Step 1 error:\n{e}")
            raise

    def onRunStep2(self):
        markupNode = self.markupSelector.currentNode()
        if not markupNode:
            slicer.util.errorDisplay("Please select the landmark list.")
            return

        try:
            result = self.logic.runStep2(
                filteredModelName="CondyleFiltered_lt5mm",
                fiducialNode=markupNode
            )
            slicer.util.infoDisplay("Step 2 completed.")
            self.log("Step 2 completed.")
            self.log(str(result))
        except Exception as e:
            slicer.util.errorDisplay(f"Step 2 error:\n{e}")
            raise

    def onRunStep3(self):
        refs = {
            1: self.refPosteriorSpinBox.value,
            2: self.refMedioSpinBox.value,
            3: self.refAnteriorSpinBox.value
        }
        try:
            result = self.logic.runStep3(
                segmentedModelName="Condyle_AP_Manual_6pts",
                referenceValues=refs,
                exportFolder=self.exportFolderEdit.text
            )
            self.outputText.clear()
            self.log("Step 3 completed.\n")
            self.log(result["text"])
        except Exception as e:
            slicer.util.errorDisplay(f"Step 3 error:\n{e}")
            raise


#
# ATMJointSpaceAnalyzerLogic
#

class ATMJointSpaceAnalyzerLogic(ScriptedLoadableModuleLogic):

    def __init__(self):
        ScriptedLoadableModuleLogic.__init__(self)
        self.lastStep1Data = {}
        self.lastStep2Data = {}
        self.lastStep3Data = {}

    def getNode(self, name):
        return slicer.util.getNode(name)

    def createOrGetModelNode(self, name):
        try:
            return slicer.util.getNode(name)
        except slicer.util.MRMLNodeNotFoundException:
            return slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", name)

    def removeNodeIfExists(self, name):
        try:
            node = slicer.util.getNode(name)
            slicer.mrmlScene.RemoveNode(node)
        except slicer.util.MRMLNodeNotFoundException:
            pass

    def ensureDir(self, folderPath):
        os.makedirs(folderPath, exist_ok=True)
        return folderPath

    def getExcelPath(self, exportFolder):
        self.ensureDir(exportFolder)
        return os.path.join(exportFolder, "ATM_JointSpace_Results.xlsx")

    def getPdfPath(self, exportFolder):
        self.ensureDir(exportFolder)
        return os.path.join(exportFolder, "ATM_JointSpace_Report.pdf")

    def getPdfSummaryPath(self, exportFolder):
        self.ensureDir(exportFolder)
        return os.path.join(exportFolder, "ATM_JointSpace_Report_Summary.pdf")

    def getOrCreateWorkbook(self, excelPath):
        if not OPENPYXL_AVAILABLE:
            return None
        if os.path.exists(excelPath):
            wb = load_workbook(excelPath)
        else:
            wb = Workbook()
            defaultSheet = wb.active
            wb.remove(defaultSheet)
        return wb

    def writeSheet(self, wb, sheetName, rows):
        if wb is None:
            return

        if sheetName in wb.sheetnames:
            ws = wb[sheetName]
            wb.remove(ws)

        ws = wb.create_sheet(sheetName)

        if not rows:
            ws["A1"] = "No data"
            return

        headers = list(rows[0].keys())
        for colIdx, header in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=colIdx, value=header)
            cell.font = Font(bold=True)

        for rowIdx, rowData in enumerate(rows, start=2):
            for colIdx, header in enumerate(headers, start=1):
                value = rowData.get(header, "")
                ws.cell(row=rowIdx, column=colIdx, value=value)

        for column_cells in ws.columns:
            length = max(len(str(cell.value)) if cell.value is not None else 0 for cell in column_cells)
            ws.column_dimensions[column_cells[0].column_letter].width = min(max(length + 2, 12), 35)

    def saveWorkbook(self, wb, excelPath):
        if wb is not None:
            wb.save(excelPath)

    def preprocessPolydata(self, polydata):
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

        output = vtk.vtkPolyData()
        output.DeepCopy(normals.GetOutput())
        return output

    def findColorNode(self, colorName):
        try:
            return slicer.util.getNode(colorName)
        except Exception:
            pass
        collection = slicer.mrmlScene.GetNodesByClass("vtkMRMLColorNode")
        collection.UnRegister(None)
        collection.InitTraversal()
        for _ in range(collection.GetNumberOfItems()):
            node = collection.GetNextItemAsObject()
            if node and colorName.lower() in node.GetName().lower():
                return node
        return None

    def createOrUpdateDiscreteDistanceColorNode(self, name="Distance_0.25mm_0to4.5"):
        existing = None
        try:
            existing = slicer.util.getNode(name)
        except Exception:
            existing = None

        step = 0.25
        maxVal = 4.5
        n = int(maxVal / step) + 1

        if existing and existing.IsA("vtkMRMLColorTableNode"):
            colorNode = existing
        else:
            if existing:
                slicer.mrmlScene.RemoveNode(existing)
            colorNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLColorTableNode", name)
            colorNode.SetTypeToUser()

        colorNode.SetNumberOfColors(n)
        colorNode.NamesInitialisedOn()

        for i in range(n):
            val = i * step
            t = val / maxVal if maxVal > 0 else 0.0

            r = min(max(2.0 * t - 0.5, 0.0), 1.0)
            g = min(max(1.8 * (1.0 - abs(t - 0.5) * 2.0), 0.0), 1.0)
            b = min(max(1.5 * (1.0 - t), 0.0), 1.0)

            colorNode.SetColor(i, r, g, b, 1.0)

        return colorNode

    def createOrUpdateDiscreteReferenceComparisonColorNode(self, name="ReferenceComparison_Discrete_0.25mm"):
        existing = None
        try:
            existing = slicer.util.getNode(name)
        except Exception:
            existing = None

        if existing and existing.IsA("vtkMRMLProceduralColorNode"):
            colorNode = existing
        else:
            if existing:
                slicer.mrmlScene.RemoveNode(existing)
            colorNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLProceduralColorNode", name)

        ctf = vtk.vtkColorTransferFunction()
        ctf.RemoveAllPoints()

        ctf.AddRGBPoint(-2.0, 1.0, 0.0, 0.0)
        ctf.AddRGBPoint(-0.25, 0.0, 1.0, 0.0)
        ctf.AddRGBPoint(0.0, 0.0, 1.0, 0.0)
        ctf.AddRGBPoint(0.25, 0.0, 1.0, 0.0)
        ctf.AddRGBPoint(2.0, 0.0, 0.0, 1.0)

        colorNode.SetAndObserveColorTransferFunction(ctf)
        colorNode.SetName(name)
        colorNode.HideFromEditorsOff()
        return colorNode

    def setModelDisplay(self, modelNode, scalarName, colorName, scalarMin, scalarMax):
        if not modelNode.GetDisplayNode():
            modelNode.CreateDefaultDisplayNodes()

        displayNode = modelNode.GetDisplayNode()
        displayNode.SetVisibility(True)
        displayNode.SetScalarVisibility(True)

        try:
            displayNode.SetActiveScalar(scalarName, vtk.vtkAssignAttribute.POINT_DATA)
        except Exception:
            displayNode.SetActiveScalarName(scalarName)

        try:
            displayNode.SetAutoScalarRange(False)
            displayNode.SetScalarRange(scalarMin, scalarMax)
        except Exception:
            pass

        colorNode = self.findColorNode(colorName)
        if colorNode:
            displayNode.SetAndObserveColorNodeID(colorNode.GetID())

        modelNode.Modified()
        displayNode.Modified()
        slicer.app.processEvents()

    def setModelDisplayWithColorNode(self, modelNode, scalarName, colorNode, scalarMin, scalarMax):
        if not modelNode.GetDisplayNode():
            modelNode.CreateDefaultDisplayNodes()

        displayNode = modelNode.GetDisplayNode()
        displayNode.SetVisibility(True)
        displayNode.SetScalarVisibility(True)

        try:
            displayNode.SetActiveScalar(scalarName, vtk.vtkAssignAttribute.POINT_DATA)
        except Exception:
            displayNode.SetActiveScalarName(scalarName)

        displayNode.SetAutoScalarRange(False)
        displayNode.SetScalarRange(scalarMin, scalarMax)
        displayNode.SetAndObserveColorNodeID(colorNode.GetID())

        modelNode.Modified()
        displayNode.Modified()
        slicer.app.processEvents()

    def addOrUpdateColorLegend(self, modelNode, titleText="Difference from region reference (mm)"):
        colorLegendDisplayNode = slicer.modules.colors.logic().AddDefaultColorLegendDisplayNode(modelNode)
        colorLegendDisplayNode.SetVisibility(True)
        colorLegendDisplayNode.SetTitleText(titleText)
        colorLegendDisplayNode.SetLabelFormat("%0.2f")
        colorLegendDisplayNode.SetSize(0.12, 0.5)
        colorLegendDisplayNode.SetPosition(0.85, 0.15)
        return colorLegendDisplayNode

    def showOnlyFinalComparison(self):
        nodeNamesToHide = [
            "JointSpaceDistanceMap",
            "CondyleFiltered_lt5mm",
            "Condyle_AP_Manual_6pts",
            "CutLine_AM",
            "CutLine_MP"
        ]

        for nodeName in nodeNamesToHide:
            try:
                node = slicer.util.getNode(nodeName)
                if node.GetDisplayNode():
                    node.GetDisplayNode().SetVisibility(False)
            except Exception:
                pass

        try:
            node = slicer.util.getNode("Condyle_ReferenceComparison")
            if node.GetDisplayNode():
                node.GetDisplayNode().SetVisibility(True)
        except Exception:
            pass

    def showOnlyNodes(self, visibleNodeNames):
        allModelNodes = slicer.util.getNodesByClass("vtkMRMLModelNode")
        for node in allModelNodes:
            if node.GetDisplayNode():
                node.GetDisplayNode().SetVisibility(False)

        allLineNodes = slicer.util.getNodesByClass("vtkMRMLMarkupsLineNode")
        for node in allLineNodes:
            if node.GetDisplayNode():
                node.GetDisplayNode().SetVisibility(False)

        allFidNodes = slicer.util.getNodesByClass("vtkMRMLMarkupsFiducialNode")
        for node in allFidNodes:
            if node.GetDisplayNode():
                node.GetDisplayNode().SetVisibility(False)

        for name in visibleNodeNames:
            try:
                node = slicer.util.getNode(name)
                if node.GetDisplayNode():
                    node.GetDisplayNode().SetVisibility(True)
            except Exception:
                pass

        slicer.app.processEvents()

    def thresholdPolydataByPointScalar(self, polydata, scalarName, upperValue):
        thresh = vtk.vtkThreshold()
        thresh.SetInputData(polydata)
        thresh.SetInputArrayToProcess(
            0, 0, 0,
            vtk.vtkDataObject.FIELD_ASSOCIATION_POINTS,
            scalarName
        )
        thresh.SetLowerThreshold(0.0)
        thresh.SetUpperThreshold(upperValue)
        thresh.SetThresholdFunction(vtk.vtkThreshold.THRESHOLD_BETWEEN)
        thresh.Update()

        geo = vtk.vtkGeometryFilter()
        geo.SetInputData(thresh.GetOutput())
        geo.Update()

        out = vtk.vtkPolyData()
        out.DeepCopy(geo.GetOutput())
        return out

    def thresholdPolydataByPointScalarRange(self, polydata, scalarName, lowerValue, upperValue):
        thresh = vtk.vtkThreshold()
        thresh.SetInputData(polydata)
        thresh.SetInputArrayToProcess(
            0, 0, 0,
            vtk.vtkDataObject.FIELD_ASSOCIATION_POINTS,
            scalarName
        )
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

    def extractLargestRegion(self, polydata):
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

    def removeExistingArray(self, polydata, arrayName):
        pd = polydata.GetPointData()
        if pd is None:
            return
        for i in range(pd.GetNumberOfArrays() - 1, -1, -1):
            arr = pd.GetArray(i)
            if arr and arr.GetName() == arrayName:
                pd.RemoveArray(arrayName)

    def normalize(self, v):
        n = np.linalg.norm(v)
        if n == 0:
            raise RuntimeError("Zero-length vector.")
        return v / n

    def getFiducialPoints(self, fidNode, nExpected=6):
        n = fidNode.GetNumberOfControlPoints()
        if n < nExpected:
            raise RuntimeError(f"The landmark list must contain at least {nExpected} points.")
        pts = []
        for i in range(nExpected):
            p = [0.0, 0.0, 0.0]
            fidNode.GetNthControlPointPositionWorld(i, p)
            pts.append(np.array(p, dtype=float))
        return pts

    def createLineMarkup(self, name, p1, p2, color=(1, 0, 0)):
        self.removeNodeIfExists(name)
        lineNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsLineNode", name)
        lineNode.AddControlPointWorld(vtk.vtkVector3d(*p1))
        lineNode.AddControlPointWorld(vtk.vtkVector3d(*p2))
        display = lineNode.GetDisplayNode()
        if display:
            display.SetSelectedColor(*color)
            display.SetColor(*color)
            display.SetLineThickness(0.6)
            display.SetGlyphScale(1.2)
            display.SetTextScale(0.0)
        return lineNode

    def vertexAreas(self, polydata):
        """Area weight of each vertex (shared implementation, see tmj_space_core)."""
        return _vertexAreas(polydata)

    def weightedQuantile(self, values, weights, q):
        return _weightedQuantile(values, weights, q)



    def forceRender(self):
        layoutManager = slicer.app.layoutManager()
        threeDWidget = layoutManager.threeDWidget(0)
        threeDView = threeDWidget.threeDView()
        threeDView.forceRender()
        slicer.app.processEvents()

    def computeRangeDistribution(self, values, bins, weights=None):
        values = np.asarray(values, dtype=float)
        results = []
        n = len(values)
        w = None
        if weights is not None:
            w = np.asarray(weights, dtype=float)
            if w.size != values.size:
                w = None
            else:
                w = np.where(np.isfinite(w) & (w > 0), w, 0.0)
        totalArea = float(w.sum()) if w is not None else 0.0
        if n == 0:
            for lo, hi in bins:
                results.append({"Range": f"{lo}-{hi} mm", "Count": 0, "Percent": 0.0, "PercentArea": 0.0})
            return results
        for lo, hi in bins:
            if hi == bins[-1][1]:
                mask = (values >= lo) & (values <= hi)
            else:
                mask = (values >= lo) & (values < hi)
            count = int(np.sum(mask))
            pct = float(100.0 * count / n)
            pctArea = float(100.0 * w[mask].sum() / totalArea) if (w is not None and totalArea > 0) else None
            results.append({"Range": f"{lo}-{hi} mm", "Count": count, "Percent": pct, "PercentArea": pctArea})
        return results

    def formatRangeDistributionLine(self, distRows):
        return " / ".join([f"{r['Range']}: {r['Percent']:.2f}%" for r in distRows])

    def computeRegionDeltaDistribution(self, deltaValues, tolerance=0.5):
        n = len(deltaValues)
        if n == 0:
            return {
                "BelowExpected_Count": 0, "BelowExpected_Percent": 0.0,
                "WithinExpected_Count": 0, "WithinExpected_Percent": 0.0,
                "AboveExpected_Count": 0, "AboveExpected_Percent": 0.0
            }
        below = int(np.sum(deltaValues < -tolerance))
        within = int(np.sum((deltaValues >= -tolerance) & (deltaValues <= tolerance)))
        above = int(np.sum(deltaValues > tolerance))
        return {
            "BelowExpected_Count": below, "BelowExpected_Percent": 100.0 * below / n,
            "WithinExpected_Count": within, "WithinExpected_Percent": 100.0 * within / n,
            "AboveExpected_Count": above, "AboveExpected_Percent": 100.0 * above / n
        }

    def setCameraToStandardView(self, modelNode, viewName):
        layoutManager = slicer.app.layoutManager()
        threeDWidget = layoutManager.threeDWidget(0)
        threeDView = threeDWidget.threeDView()
        renderer = threeDView.renderWindow().GetRenderers().GetFirstRenderer()
        camera = renderer.GetActiveCamera()

        bounds = [0.0] * 6
        modelNode.GetBounds(bounds)

        xMin, xMax, yMin, yMax, zMin, zMax = bounds
        center = np.array([
            (xMin + xMax) / 2.0,
            (yMin + yMax) / 2.0,
            (zMin + zMax) / 2.0
        ])

        dx = xMax - xMin
        dy = yMax - yMin
        dz = zMax - zMin
        maxDim = max(dx, dy, dz)
        distance = maxDim * 3.0 if maxDim > 0 else 100.0

        views = {
            "anterior": (np.array([0.0, 1.0, 0.0]), np.array([0.0, 0.0, 1.0])),
            "posterior": (np.array([0.0, -1.0, 0.0]), np.array([0.0, 0.0, 1.0])),
            "right": (np.array([1.0, 0.0, 0.0]), np.array([0.0, 0.0, 1.0])),
            "left": (np.array([-1.0, 0.0, 0.0]), np.array([0.0, 0.0, 1.0])),
            "superior": (np.array([0.0, 0.0, 1.0]), np.array([0.0, 1.0, 0.0])),
            "inferior": (np.array([0.0, 0.0, -1.0]), np.array([0.0, 1.0, 0.0])),
        }

        if viewName not in views:
            raise ValueError(f"Unknown view: {viewName}")

        direction, viewUp = views[viewName]
        position = center + direction * distance

        camera.SetFocalPoint(center[0], center[1], center[2])
        camera.SetPosition(position[0], position[1], position[2])
        camera.SetViewUp(viewUp[0], viewUp[1], viewUp[2])

        renderer.ResetCameraClippingRange()
        threeDView.forceRender()
        slicer.app.processEvents()

    def save3DViewScreenshot(self, filePath):
        layoutManager = slicer.app.layoutManager()
        threeDWidget = layoutManager.threeDWidget(0)
        pixmap = threeDWidget.grab()
        pixmap.save(filePath, "JPG")

    def captureStandardViews(self, modelNode, outputFolder, prefix):
        self.ensureDir(outputFolder)

        viewNames = ["anterior", "posterior", "right", "left", "superior", "inferior"]
        savedFiles = []

        for viewName in viewNames:
            self.setCameraToStandardView(modelNode, viewName)
            filePath = os.path.join(outputFolder, f"{prefix}_{viewName}.jpg")
            self.save3DViewScreenshot(filePath)
            savedFiles.append(filePath)

        return savedFiles

    def buildStatsRow(self, groupName, vals, weights=None):
        """Descriptors of a distance distribution (shared implementation, see tmj_space_core)."""
        row = {"Group": groupName}
        row.update(_summaryStats(vals, weights))
        return row

    def buildPdfReport(self, pdfPath, step1Images, step3Images, step1StatsRows, step1DistRows,
                       step2Rows, overallRows, regionRows, regionDistRows):
        if not REPORTLAB_AVAILABLE:
            return False, "reportlab is not installed. PDF export was skipped."

        c = canvas.Canvas(pdfPath, pagesize=A4)
        pageW, pageH = A4

        def new_page(title):
            c.setFont("Helvetica-Bold", 16)
            c.drawString(20 * mm, pageH - 20 * mm, title)

        def draw_lines(lines, x_mm=20, start_y_mm=35, line_h_mm=6, font_size=10):
            c.setFont("Helvetica", font_size)
            y = pageH - start_y_mm * mm
            for line in lines:
                c.drawString(x_mm * mm, y, str(line))
                y -= line_h_mm * mm
                if y < 20 * mm:
                    c.showPage()
                    c.setFont("Helvetica", font_size)
                    y = pageH - 20 * mm
            return y

        def draw_image_grid(imagePaths, title):
            c.showPage()
            new_page(title)
            x_positions = [15 * mm, 110 * mm]
            y_positions = [pageH - 40 * mm, pageH - 115 * mm, pageH - 190 * mm]
            w = 80 * mm
            h = 60 * mm
            idx = 0
            for y in y_positions:
                for x in x_positions:
                    if idx >= len(imagePaths):
                        return
                    imgPath = imagePaths[idx]
                    if os.path.exists(imgPath):
                        c.drawImage(imgPath, x, y - h, width=w, height=h, preserveAspectRatio=True, anchor='sw')
                        c.setFont("Helvetica", 9)
                        c.drawString(x, y - h - 5 * mm, os.path.basename(imgPath))
                    idx += 1

        new_page("ATM Joint Space Analysis Report")
        draw_lines([
            f"Step 1 images exported: {len(step1Images)}",
            f"Step 3 images exported: {len(step3Images)}",
            f"Excel export available: {'Yes' if OPENPYXL_AVAILABLE else 'No'}",
            "",
            "Included sections:",
            "- Step 1 statistics",
            "- Step 1 distribution by ranges",
            "- Step 2 segmentation summary",
            "- Step 3 overall filtered statistics",
            "- Step 3 region-based statistics",
            "- Step 3 region delta distributions",
            "- Step 1 screenshots",
            "- Step 3 screenshots",
        ])

        c.showPage(); new_page("Step 1 Statistics")
        lines = []
        for row in step1StatsRows:
            lines.append(f"Group: {row.get('Group', '')}")
            for k, v in row.items():
                if k != "Group": lines.append(f"  {k}: {v}")
            lines.append("")
        if step1DistRows:
            lines.append("Step 1 filtered distribution by ranges:")
            for row in step1DistRows:
                lines.append(f"  {row.get('Range', '')}: {row.get('Percent', 0):.2f}% ({row.get('Count', 0)} points)")
        draw_lines(lines)

        c.showPage(); new_page("Step 2 Segmentation Summary")
        lines = []
        for row in step2Rows:
            for k, v in row.items():
                lines.append(f"{k}: {v}")
        draw_lines(lines)

        c.showPage(); new_page("Step 3 Overall Filtered Statistics")
        lines = []
        for row in overallRows:
            lines.append(f"Group: {row.get('Group', '')}")
            for k, v in row.items():
                if k != "Group": lines.append(f"  {k}: {v}")
            lines.append("")
        draw_lines(lines)

        c.showPage(); new_page("Step 3 Region-Based Statistics")
        lines = []
        for row in regionRows:
            lines.append(f"Region: {row.get('Region', '')}")
            for k, v in row.items():
                if k != "Region": lines.append(f"  {k}: {v}")
            lines.append("")
        draw_lines(lines)

        c.showPage(); new_page("Step 3 Region Delta Distributions")
        lines = []
        for row in regionDistRows:
            lines.append(f"Region: {row.get('Region', '')}")
            lines.append(f"  Within ±0.5 mm: {row.get('WithinExpected_Percent', 0):.2f}% ({row.get('WithinExpected_Count', 0)})")
            lines.append(f"  Below expected (< -0.5 mm): {row.get('BelowExpected_Percent', 0):.2f}% ({row.get('BelowExpected_Count', 0)})")
            lines.append(f"  Above expected (> +0.5 mm): {row.get('AboveExpected_Percent', 0):.2f}% ({row.get('AboveExpected_Count', 0)})")
            lines.append("")
        draw_lines(lines)

        draw_image_grid(step1Images, "Step 1 Standardized Views")
        draw_image_grid(step3Images, "Step 3 Standardized Views")

        c.save()
        return True, None

    def buildSummaryPdfReport(self, pdfPath, step1Images, step3Images, step1StatsRows, step1DistRows, overallRows, regionRows, regionDistRows):
        if not REPORTLAB_AVAILABLE:
            return False, "reportlab is not installed. PDF summary export was skipped."

        c = canvas.Canvas(pdfPath, pagesize=A4)
        pageW, pageH = A4

        def title(txt):
            c.setFont("Helvetica-Bold", 18)
            c.drawString(18 * mm, pageH - 18 * mm, txt)

        def section(txt, y):
            c.setFont("Helvetica-Bold", 13)
            c.drawString(18 * mm, y, txt)

        def body(txt, x, y, size=10):
            c.setFont("Helvetica", size)
            c.drawString(x, y, str(txt))

        def draw_big_images(imagePaths, y_top, titleText):
            section(titleText, y_top)
            y = y_top - 8 * mm
            x_positions = [18 * mm, 110 * mm]
            w = 80 * mm
            h = 60 * mm
            for idx in range(min(2, len(imagePaths))):
                img = imagePaths[idx]
                if os.path.exists(img):
                    x = x_positions[idx]
                    c.drawImage(img, x, y - h, width=w, height=h, preserveAspectRatio=True, anchor='sw')
            return y - h - 8 * mm

        title("ATM Joint Space Analysis Summary")
        y = pageH - 30 * mm
        y = draw_big_images(step1Images, y, "Step 1 views")
        section("Step 1 summary", y)
        y -= 8 * mm
        for row in step1StatsRows[:2]:
            body(f"{row.get('Group','')}: mean {row.get('Mean_mm', None)} mm | SD {row.get('SD_mm', None)} | min {row.get('Min_mm', None)} | max {row.get('Max_mm', None)}", 20 * mm, y)
            y -= 6 * mm
        if step1DistRows:
            body("Filtered distribution:", 20 * mm, y)
            y -= 6 * mm
            body(" / ".join([f"{r['Range']}: {r['Percent']:.2f}%" for r in step1DistRows]), 24 * mm, y)

        c.showPage()
        title("Step 3 Summary")
        y = pageH - 30 * mm
        y = draw_big_images(step3Images, y, "Step 3 views")
        section("Overall filtered", y)
        y -= 8 * mm
        if overallRows:
            row = overallRows[0]
            body(f"Mean {row.get('Mean_mm', None)} mm | SD {row.get('SD_mm', None)} | min {row.get('Min_mm', None)} | max {row.get('Max_mm', None)}", 20 * mm, y)
            y -= 10 * mm
        section("Region summary", y)
        y -= 8 * mm
        regionDistMap = {r['Region']: r for r in regionDistRows}
        for row in regionRows:
            region = row.get('Region','')
            dist = regionDistMap.get(region, {})
            body(f"{region}: mean {row.get('Mean_mm', None)} mm | ref {row.get('Reference_mm', None)} | diff {row.get('AbsoluteDifference_mm', None)}", 20 * mm, y)
            y -= 5 * mm
            body(f"within ±0.5 mm {dist.get('WithinExpected_Percent',0):.2f}% | below {dist.get('BelowExpected_Percent',0):.2f}% | above {dist.get('AboveExpected_Percent',0):.2f}%", 24 * mm, y)
            y -= 8 * mm

        c.save()
        return True, None


    # ------------------------
    # STEP 1
    # ------------------------
    def runStep1(self, sourceNode, targetNode, cutoffMm=5.0, exportFolder=""):
        sourcePoly = sourceNode.GetPolyData()
        targetPoly = targetNode.GetPolyData()

        if sourcePoly is None or sourcePoly.GetNumberOfPoints() == 0:
            raise RuntimeError("Mandibular condyle model is empty.")
        if targetPoly is None or targetPoly.GetNumberOfPoints() == 0:
            raise RuntimeError("Articular cavity model is empty.")

        sourcePoly = self.preprocessPolydata(sourcePoly)
        targetPoly = self.preprocessPolydata(targetPoly)

        distanceFilter = vtk.vtkDistancePolyDataFilter()
        distanceFilter.SetInputData(0, sourcePoly)
        distanceFilter.SetInputData(1, targetPoly)
        distanceFilter.SignedDistanceOff()
        distanceFilter.ComputeSecondDistanceOff()
        distanceFilter.Update()

        outputPoly = vtk.vtkPolyData()
        outputPoly.DeepCopy(distanceFilter.GetOutput())

        distanceScalars = outputPoly.GetPointData().GetScalars()
        if distanceScalars is None:
            raise RuntimeError("Distance scalar generation failed.")

        fullScalarsRaw = vtk_to_numpy(distanceScalars)
        fullScalarsRaw = np.abs(fullScalarsRaw)

        step = 0.25
        maxDisplayVal = 4.5
        discreteScalars = _discretise(fullScalarsRaw, step, maxDisplayVal)  # display only

        self.removeExistingArray(outputPoly, "RawAbsoluteDistance")
        rawArray = numpy_to_vtk(fullScalarsRaw, deep=True)
        rawArray.SetName("RawAbsoluteDistance")
        outputPoly.GetPointData().AddArray(rawArray)

        self.removeExistingArray(outputPoly, "AbsoluteDistance")
        distanceArray = numpy_to_vtk(discreteScalars, deep=True)
        distanceArray.SetName("AbsoluteDistance")
        outputPoly.GetPointData().AddArray(distanceArray)
        outputPoly.GetPointData().SetActiveScalars("AbsoluteDistance")

        distanceNode = self.createOrGetModelNode("JointSpaceDistanceMap")
        distanceNode.SetAndObservePolyData(outputPoly)

        discreteColorNode = self.createOrUpdateDiscreteDistanceColorNode()
        self.setModelDisplayWithColorNode(distanceNode, "AbsoluteDistance", discreteColorNode, 0.0, 4.5)
        legendNode = self.addOrUpdateColorLegend(distanceNode, titleText="Distance to articular cavity (mm)")
        legendNode.SetVisibility(True)
        self.forceRender()

        filteredPoly = self.thresholdPolydataByPointScalar(outputPoly, "RawAbsoluteDistance", cutoffMm)
        filteredPoly = self.extractLargestRegion(filteredPoly)

        filteredPd = filteredPoly.GetPointData()
        if filteredPd.GetArray("AbsoluteDistance") is None:
            raise RuntimeError("The filtered condylar surface lost the AbsoluteDistance array.")

        filteredNode = self.createOrGetModelNode("CondyleFiltered_lt5mm")
        filteredNode.SetAndObservePolyData(filteredPoly)
        self.setModelDisplayWithColorNode(filteredNode, "AbsoluteDistance", discreteColorNode, 0.0, 4.5)

        filteredRawArr = filteredPd.GetArray("RawAbsoluteDistance")
        if filteredRawArr is None:
            raise RuntimeError("The filtered condylar surface lost the RawAbsoluteDistance array.")

        globalValues = fullScalarsRaw
        globalAreas = self.vertexAreas(outputPoly)
        filtered = vtk_to_numpy(filteredRawArr)
        filteredAreas = self.vertexAreas(filteredPoly)
        values = globalValues[np.isfinite(globalValues)]

        step1Rows = [
            self.buildStatsRow("Global distance map", globalValues, globalAreas),
            self.buildStatsRow(f"Filtered condylar surface <= {cutoffMm:.2f} mm", filtered, filteredAreas)
        ]
        bins = [(0, 1), (1, 2), (2, 4), (4, 5)]
        step1DistRows = self.computeRangeDistribution(filtered, bins, filteredAreas)

        exportedFiles = []
        excelPath = None
        excelWarning = None

        if exportFolder:
            self.ensureDir(exportFolder)
            excelPath = self.getExcelPath(exportFolder)

            step1Folder = self.ensureDir(os.path.join(exportFolder, "Step1"))
            self.showOnlyNodes(["JointSpaceDistanceMap"])
            legendNode = self.addOrUpdateColorLegend(distanceNode, titleText="Distance to articular cavity (mm)")
            legendNode.SetVisibility(True)
            self.forceRender()
            exportedFiles = self.captureStandardViews(distanceNode, step1Folder, "Step1_DistanceMap")

            if OPENPYXL_AVAILABLE:
                wb = self.getOrCreateWorkbook(excelPath)
                self.writeSheet(wb, "Step1_Statistics", step1Rows)
                self.writeSheet(wb, "Step1_Distribution", step1DistRows)

                imageRows = [{"Step": "Step1", "ImagePath": path} for path in exportedFiles]
                if "ExportedImages" in wb.sheetnames:
                    ws = wb["ExportedImages"]
                    existing = list(ws.values)
                    wb.remove(ws)
                    merged = []
                    if existing:
                        headers = existing[0]
                        for row in existing[1:]:
                            merged.append(dict(zip(headers, row)))
                    merged.extend(imageRows)
                    self.writeSheet(wb, "ExportedImages", merged)
                else:
                    self.writeSheet(wb, "ExportedImages", imageRows)

                self.saveWorkbook(wb, excelPath)
            else:
                excelWarning = "openpyxl is not installed. Excel export was skipped."

        self.lastStep1Data = {"stats_rows": step1Rows, "distribution_rows": step1DistRows, "images": exportedFiles, "excel_path": excelPath}

        return {
            "global_n": int(len(values)),
            "global_mean": float(np.mean(values)),
            "global_max": float(np.max(values)) if len(values) > 0 else None,
            "filtered_n": int(len(filtered)),
            "filtered_mean": float(np.mean(filtered)) if len(filtered) > 0 else None,
            "distribution_text": self.formatRangeDistributionLine(step1DistRows),
            "exported_step1_images": exportedFiles,
            "step1_rows": step1Rows,
            "step1_distribution_rows": step1DistRows,
            "excel_file": excelPath if OPENPYXL_AVAILABLE else None,
            "excel_warning": excelWarning
        }


    # ------------------------
    # STEP 2
    # ------------------------
    def runStep2(self, filteredModelName, fiducialNode):
        modelNode = self.getNode(filteredModelName)
        poly = modelNode.GetPolyData()
        if poly is None or poly.GetNumberOfPoints() == 0:
            raise RuntimeError("Filtered condylar surface is empty.")

        points = vtk_to_numpy(poly.GetPoints().GetData())

        p_ant, p_am_m, p_am_d, p_mp_m, p_mp_d, p_pos = self.getFiducialPoints(fiducialNode, 6)

        apAxis = self.normalize(p_ant - p_pos)
        origin = p_pos.copy()

        proj = np.dot(points - origin, apAxis)

        proj_am_m = np.dot(p_am_m - origin, apAxis)
        proj_am_d = np.dot(p_am_d - origin, apAxis)
        proj_mp_m = np.dot(p_mp_m - origin, apAxis)
        proj_mp_d = np.dot(p_mp_d - origin, apAxis)

        cut_am = (proj_am_m + proj_am_d) / 2.0
        cut_mp = (proj_mp_m + proj_mp_d) / 2.0

        if not (cut_mp < cut_am):
            raise RuntimeError("The cuts are inconsistent: the middle–posterior boundary must precede the anterior–middle boundary.")

        z_coords = points[:, 2]
        am_z_level = (p_am_m[2] + p_am_d[2]) / 2.0
        mp_z_level = (p_mp_m[2] + p_mp_d[2]) / 2.0
        middle_min_z = max(am_z_level, mp_z_level)

        anterior_min_z = p_ant[2]
        posterior_min_z = p_pos[2]

        regions = np.zeros(len(points), dtype=np.int16)

        for i, val in enumerate(proj):
            z = z_coords[i]
            if val <= cut_mp:
                regions[i] = 1 if z >= posterior_min_z else 0
            elif val <= cut_am:
                regions[i] = 2 if z >= middle_min_z else 0
            else:
                regions[i] = 3 if z >= anterior_min_z else 0

        polyOut = vtk.vtkPolyData(); polyOut.DeepCopy(poly)
        self.removeExistingArray(polyOut, "AP_Manual_6pts")
        arr = numpy_to_vtk(regions, deep=True, array_type=vtk.VTK_SHORT)
        arr.SetName("AP_Manual_6pts")
        polyOut.GetPointData().AddArray(arr)
        polyOut.GetPointData().SetActiveScalars("AP_Manual_6pts")

        regionsOnlyPoly = self.thresholdPolydataByPointScalarRange(polyOut, "AP_Manual_6pts", 1, 3)
        segmentedNode = self.createOrGetModelNode("Condyle_AP_Manual_6pts")
        segmentedNode.SetAndObservePolyData(regionsOnlyPoly)
        self.setModelDisplay(segmentedNode, "AP_Manual_6pts", "Random", 1, 3)

        self.createLineMarkup("CutLine_AM", p_am_m, p_am_d, color=(1, 0, 0))
        self.createLineMarkup("CutLine_MP", p_mp_m, p_mp_d, color=(0, 1, 0))

        step2Rows = [{"cut_mp": float(cut_mp), "cut_am": float(cut_am), "am_z_level": float(am_z_level), "mp_z_level": float(mp_z_level), "middle_min_z": float(middle_min_z), "anterior_min_z": float(anterior_min_z), "posterior_min_z": float(posterior_min_z), "n_posterior": int(np.sum(regions == 1)), "n_middle": int(np.sum(regions == 2)), "n_anterior": int(np.sum(regions == 3)), "n_excluded": int(np.sum(regions == 0))}]
        self.lastStep2Data = {"rows": step2Rows}
        return step2Rows[0]


    # ------------------------
    # STEP 3
    # ------------------------
    def runStep3(self, segmentedModelName, referenceValues, exportFolder=""):
        overallNode = self.getNode("CondyleFiltered_lt5mm")
        overallPoly = overallNode.GetPolyData()
        if overallPoly is None or overallPoly.GetNumberOfPoints() == 0:
            raise RuntimeError("Filtered condylar surface is empty.")

        overallDistanceArr = overallPoly.GetPointData().GetArray("RawAbsoluteDistance")
        if overallDistanceArr is None:
            raise RuntimeError("RawAbsoluteDistance array not found in CondyleFiltered_lt5mm.")
        overallDistancesAll = vtk_to_numpy(overallDistanceArr)
        overallAreasAll = self.vertexAreas(overallPoly)
        overallFinite = np.isfinite(overallDistancesAll)
        overallDistances = overallDistancesAll[overallFinite]
        overallAreas = overallAreasAll[overallFinite]

        modelNode = self.getNode(segmentedModelName)
        poly = modelNode.GetPolyData()
        if poly is None or poly.GetNumberOfPoints() == 0:
            raise RuntimeError("Segmented region model is empty.")

        pointData = poly.GetPointData()
        segmentArr = pointData.GetArray("AP_Manual_6pts")
        distanceArr = pointData.GetArray("RawAbsoluteDistance")
        if segmentArr is None:
            raise RuntimeError("AP_Manual_6pts array not found.")
        if distanceArr is None:
            raise RuntimeError("RawAbsoluteDistance array not found.")

        segments = vtk_to_numpy(segmentArr)
        distances = vtk_to_numpy(distanceArr)
        areasAll = self.vertexAreas(poly)

        validMask = np.isfinite(distances)
        segments = segments[validMask]
        distances = distances[validMask]
        areas = areasAll[validMask]

        labels = {1: "Posterior", 2: "Middle", 3: "Anterior"}

        lines = []
        lines.append("FINAL FILTERED ANALYSIS\n")
        lines.append("--- Overall filtered condylar surface ---")
        lines.append(f"N points: {len(overallDistances)}")

        overallRows = [self.buildStatsRow("Overall filtered condylar surface", overallDistances, overallAreas)]
        if len(overallDistances) > 0:
            meanVal = float(np.mean(overallDistances)); sdVal = float(np.std(overallDistances, ddof=0)); medVal = float(np.median(overallDistances))
            minVal = float(np.min(overallDistances)); maxVal = float(np.max(overallDistances))
            lines.append(f"Mean: {meanVal:.4f} mm")
            lines.append(f"SD: {sdVal:.4f} mm")
            lines.append(f"Median: {medVal:.4f} mm")
            lines.append(f"Min: {minVal:.4f} mm")
            lines.append(f"Max: {maxVal:.4f} mm")
            lines.append(f"Area-weighted mean: {overallRows[0].get('MeanAreaWeighted_mm')} mm")
            lines.append(f"Area-weighted median: {overallRows[0].get('MedianAreaWeighted_mm')} mm\n")
        else:
            lines.append("No points available.\n")

        lines.append("REGION-BASED ANALYSIS\n")

        rows = []
        ref_values_per_point = np.zeros(len(segments), dtype=float)
        regionStatsRows = []
        regionDistRows = []

        for segId in [1, 2, 3]:
            mask = segments == segId
            vals = distances[mask]
            wts = areas[mask]
            ref = referenceValues[segId]
            label = labels[segId]
            lines.append(f"--- {label} region ---")
            lines.append(f"Reference value: {ref:.4f} mm")
            lines.append(f"N vertices: {len(vals)}")

            if len(vals) == 0:
                lines.append("No points in this region.\n")
                regionStatsRows.append({"Region": label, "Reference_mm": ref, "N_vertices": 0, "Mean_mm": None, "SD_mm": None,
                                        "Median_mm": None, "Min_mm": None, "Max_mm": None, "Area_mm2": None,
                                        "MeanAreaWeighted_mm": None, "SDAreaWeighted_mm": None, "MedianAreaWeighted_mm": None,
                                        "AbsoluteDifference_mm": None, "PercentDifference": None})
                regionDistRows.append({"Region": label, "BelowExpected_Count": 0, "BelowExpected_Percent": 0.0,
                                       "WithinExpected_Count": 0, "WithinExpected_Percent": 0.0,
                                       "AboveExpected_Count": 0, "AboveExpected_Percent": 0.0})
                continue

            statsRow = self.buildStatsRow(label, vals, wts)
            meanVal = statsRow["Mean_mm"]; sdVal = statsRow["SD_mm"]; medVal = statsRow["Median_mm"]
            minVal = statsRow["Min_mm"]; maxVal = statsRow["Max_mm"]
            diffAbs = meanVal - ref; diffPct = ((meanVal - ref) / ref * 100.0) if ref != 0 else np.nan

            lines.append(f"Mean: {meanVal:.4f} mm")
            lines.append(f"SD: {sdVal:.4f} mm")
            lines.append(f"Median: {medVal:.4f} mm")
            lines.append(f"Min: {minVal:.4f} mm")
            lines.append(f"Max: {maxVal:.4f} mm")
            lines.append(f"Area-weighted mean: {statsRow.get('MeanAreaWeighted_mm')} mm")
            lines.append(f"Area-weighted median: {statsRow.get('MedianAreaWeighted_mm')} mm")
            lines.append(f"Absolute difference vs reference: {diffAbs:+.4f} mm")
            lines.append(f"Percent difference vs reference: {diffPct:+.2f}%")

            regionDeltaRaw = vals - ref
            regionDist = self.computeRegionDeltaDistribution(regionDeltaRaw, tolerance=0.5)
            lines.append(f"Within expected (\u00b10.5 mm): {regionDist['WithinExpected_Percent']:.2f}%")
            lines.append(f"Below expected (< -0.5 mm): {regionDist['BelowExpected_Percent']:.2f}%")
            lines.append(f"Above expected (> +0.5 mm): {regionDist['AboveExpected_Percent']:.2f}%\n")

            rows.append({"region": label, "reference_mm": ref, "n": int(len(vals)), "mean_mm": meanVal, "sd_mm": sdVal,
                         "median_mm": medVal, "min_mm": minVal, "max_mm": maxVal,
                         "mean_area_weighted_mm": statsRow.get("MeanAreaWeighted_mm"),
                         "median_area_weighted_mm": statsRow.get("MedianAreaWeighted_mm"),
                         "absolute_difference_mm": diffAbs, "percent_difference": diffPct})
            regionRow = {"Region": label, "Reference_mm": ref}
            regionRow.update({k: v for k, v in statsRow.items() if k != "Group"})
            regionRow.update({"AbsoluteDifference_mm": diffAbs, "PercentDifference": diffPct})
            regionStatsRows.append(regionRow)
            regionDistRows.append({"Region": label, **regionDist})
            ref_values_per_point[segments == segId] = ref

        referenceDeltaRaw = distances - ref_values_per_point
        step = 0.25
        maxDeltaDisplay = 2.0
        referenceDelta = np.clip(np.round(referenceDeltaRaw / step) * step, -maxDeltaDisplay, maxDeltaDisplay)

        polyOut = vtk.vtkPolyData(); polyOut.DeepCopy(poly)
        self.removeExistingArray(polyOut, "ReferenceValue"); self.removeExistingArray(polyOut, "ReferenceDelta")
        refArray = numpy_to_vtk(ref_values_per_point, deep=True); refArray.SetName("ReferenceValue"); polyOut.GetPointData().AddArray(refArray)
        deltaArray = numpy_to_vtk(referenceDelta, deep=True); deltaArray.SetName("ReferenceDelta"); polyOut.GetPointData().AddArray(deltaArray); polyOut.GetPointData().SetActiveScalars("ReferenceDelta")

        compNode = self.createOrGetModelNode("Condyle_ReferenceComparison")
        compNode.SetAndObservePolyData(polyOut)
        colorNode = self.createOrUpdateDiscreteReferenceComparisonColorNode()
        self.setModelDisplayWithColorNode(compNode, "ReferenceDelta", colorNode, -2.0, 2.0)

        legendNode = self.addOrUpdateColorLegend(compNode, titleText="Difference from region reference (mm)")
        legendNode.SetVisibility(True)
        self.showOnlyFinalComparison()
        self.forceRender()

        exportedFiles=[]; excelPath=None; pdfPath=None; summaryPdfPath=None; excelWarning=None; pdfWarning=None; summaryPdfWarning=None
        if exportFolder:
            self.ensureDir(exportFolder)
            excelPath=self.getExcelPath(exportFolder); pdfPath=self.getPdfPath(exportFolder); summaryPdfPath=self.getPdfSummaryPath(exportFolder)
            step3Folder=self.ensureDir(os.path.join(exportFolder, "Step3"))
            legendNode=self.addOrUpdateColorLegend(compNode, titleText="Difference from region reference (mm)")
            legendNode.SetVisibility(True)
            self.forceRender()
            exportedFiles=self.captureStandardViews(compNode, step3Folder, "Step3_ReferenceComparison")

            if OPENPYXL_AVAILABLE:
                wb=self.getOrCreateWorkbook(excelPath)
                self.writeSheet(wb, "Step3_OverallFiltered", overallRows)
                self.writeSheet(wb, "Step3_Regions", regionStatsRows)
                self.writeSheet(wb, "Step3_RegionDistribution", regionDistRows)
                if self.lastStep2Data.get("rows"):
                    self.writeSheet(wb, "Step2_Summary", self.lastStep2Data["rows"])

                imageRows=[{"Step":"Step3","ImagePath":path} for path in exportedFiles]
                if "ExportedImages" in wb.sheetnames:
                    ws=wb["ExportedImages"]; existing=list(ws.values); wb.remove(ws); merged=[]
                    if existing:
                        headers=existing[0]
                        for row in existing[1:]:
                            merged.append(dict(zip(headers,row)))
                    merged.extend(imageRows)
                    self.writeSheet(wb, "ExportedImages", merged)
                else:
                    self.writeSheet(wb, "ExportedImages", imageRows)
                self.saveWorkbook(wb, excelPath)
            else:
                excelWarning="openpyxl is not installed. Excel export was skipped."

            step1Folder=os.path.join(exportFolder, "Step1")
            step1Images=[]
            if os.path.isdir(step1Folder):
                for f in sorted(os.listdir(step1Folder)):
                    if f.lower().endswith(".jpg"):
                        step1Images.append(os.path.join(step1Folder, f))

            step1StatsRows=self.lastStep1Data.get("stats_rows", [])
            step1DistRows=self.lastStep1Data.get("distribution_rows", [])
            step2Rows=self.lastStep2Data.get("rows", [])

            ok,msg=self.buildPdfReport(pdfPath, step1Images, exportedFiles, step1StatsRows, step1DistRows, step2Rows, overallRows, regionStatsRows, regionDistRows)
            if not ok:
                pdfWarning=msg

            ok2,msg2=self.buildSummaryPdfReport(summaryPdfPath, step1Images, exportedFiles, step1StatsRows, step1DistRows, overallRows, regionStatsRows, regionDistRows)
            if not ok2:
                summaryPdfWarning=msg2

        self.lastStep3Data = {"overall_rows": overallRows, "region_rows": regionStatsRows, "region_distribution_rows": regionDistRows, "images": exportedFiles}

        lines.append("REFERENCE COMPARISON MAP")
        lines.append("Color interpretation:")
        lines.append("Red = distance below reference")
        lines.append("Strong green = within ±0.25 mm from reference")
        lines.append("Blue = distance above reference")
        lines.append("Display range is clipped from -2.00 to +2.00 mm")

        if exportedFiles:
            lines.append("")
            lines.append("JPG views exported:")
            for f in exportedFiles:
                lines.append(f)

        if excelPath and OPENPYXL_AVAILABLE:
            lines.append("")
            lines.append(f"Excel file saved to: {excelPath}")
        elif excelWarning:
            lines.append("")
            lines.append(excelWarning)

        if pdfPath and REPORTLAB_AVAILABLE and pdfWarning is None:
            lines.append(f"PDF report saved to: {pdfPath}")
        elif pdfWarning:
            lines.append(pdfWarning)

        if summaryPdfPath and REPORTLAB_AVAILABLE and summaryPdfWarning is None:
            lines.append(f"Summary PDF report saved to: {summaryPdfPath}")
        elif summaryPdfWarning:
            lines.append(summaryPdfWarning)

        return {
            "text": "\n".join(lines),
            "rows": rows,
            "exported_step3_images": exportedFiles,
            "excel_file": excelPath if OPENPYXL_AVAILABLE else None,
            "pdf_file": pdfPath if REPORTLAB_AVAILABLE and pdfWarning is None else None,
            "summary_pdf_file": summaryPdfPath if REPORTLAB_AVAILABLE and summaryPdfWarning is None else None,
            "excel_warning": excelWarning,
            "pdf_warning": pdfWarning,
            "summary_pdf_warning": summaryPdfWarning
        }
        return {
            "text": "\n".join(lines),
            "rows": rows,
            "exported_step3_images": exportedFiles,
            "excel_file": excelPath if OPENPYXL_AVAILABLE else None,
            "pdf_file": pdfPath if REPORTLAB_AVAILABLE and pdfWarning is None else None,
            "excel_warning": excelWarning,
            "pdf_warning": pdfWarning
        }
