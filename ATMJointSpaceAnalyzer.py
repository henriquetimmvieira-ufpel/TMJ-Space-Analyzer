import os
import math
import numpy as np
import vtk

import qt
import ctk

from vtk.util.numpy_support import vtk_to_numpy, numpy_to_vtk

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
        parent.title = "ATM Joint Space Analyzer"
        parent.categories = ["Examples"]
        parent.dependencies = []
        parent.contributors = ["Henrique + ChatGPT"]
        parent.helpText = """
Module for TMJ joint space analysis:
1. distance map + functional condylar surface filtering
2. manual segmentation into anterior / middle / posterior poles
3. filtered overall statistics + pole-based statistics + reference comparison map
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
            "Most anterior limit point of the anterior condylar pole.",
            "Point at the anterior–middle boundary on the most mesial aspect of the mandibular condyle.",
            "Point at the anterior–middle boundary on the most distal/lateral aspect of the mandibular condyle.",
            "Point at the middle–posterior boundary on the most mesial aspect of the mandibular condyle.",
            "Point at the middle–posterior boundary on the most distal/lateral aspect of the mandibular condyle.",
            "Most posterior limit point of the posterior condylar pole."
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
        step2Button.text = "Step 2 — Landmark placement and pole segmentation"
        self.layout.addWidget(step2Button)
        step2Layout = qt.QVBoxLayout(step2Button)

        self.instructionsLabel = qt.QLabel(
            "Place 6 landmarks in this exact order:\n\n"
            "1. Anterior — Most anterior limit point of the anterior condylar pole.\n"
            "2. AM_mesial — Point at the anterior–middle boundary on the most mesial aspect of the condyle.\n"
            "3. AM_distal — Point at the anterior–middle boundary on the most distal/lateral aspect of the condyle.\n"
            "4. MP_mesial — Point at the middle–posterior boundary on the most mesial aspect of the condyle.\n"
            "5. MP_distal — Point at the middle–posterior boundary on the most distal/lateral aspect of the condyle.\n"
            "6. Posterior — Most posterior limit point of the posterior condylar pole."
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

    def addOrUpdateColorLegend(self, modelNode, titleText="Difference from pole reference (mm)"):
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

    def vertexAreaWeights(self, polydata):
        """One third of each incident triangle area per vertex (mm2).

        The polydata must be a surface mesh. Degenerate triangles are ignored.
        Weight arrays retain the input vertex ordering so they can be paired with
        point-data arrays such as RawAbsoluteDistance and AP_Manual_6pts.
        """
        triangulator = vtk.vtkTriangleFilter()
        triangulator.SetInputData(polydata)
        triangulator.Update()
        trianglesPoly = triangulator.GetOutput()
        if trianglesPoly.GetNumberOfPoints() != polydata.GetNumberOfPoints():
            raise RuntimeError("Triangulation changed mesh vertex count; cannot align area weights with distances.")

        points = vtk_to_numpy(trianglesPoly.GetPoints().GetData()).astype(np.float64, copy=False)
        polygonArray = trianglesPoly.GetPolys()
        offsets = vtk_to_numpy(polygonArray.GetOffsetsArray())
        connectivity = vtk_to_numpy(polygonArray.GetConnectivityArray())
        if len(offsets) < 2 or len(connectivity) == 0:
            raise RuntimeError("The surface has no triangles for area-weighted analysis.")
        if not np.all(np.diff(offsets) == 3):
            raise RuntimeError("The triangulated surface contains non-triangular faces.")
        triangles = connectivity.reshape((-1, 3))
        a, b, c = points[triangles[:, 0]], points[triangles[:, 1]], points[triangles[:, 2]]
        faceAreas = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
        vertexWeights = np.zeros(len(points), dtype=float)
        np.add.at(vertexWeights, triangles.ravel(), np.repeat(faceAreas / 3.0, 3))
        if np.sum(vertexWeights) <= 0:
            raise RuntimeError("The surface contains no non-degenerate triangles.")
        return vertexWeights

    def weightedStats(self, values, areaWeights):
        """Descriptive surface statistics; no pseudo-independent per-vertex CIs."""
        values = np.asarray(values, dtype=float)
        areaWeights = np.asarray(areaWeights, dtype=float)
        if values.shape != areaWeights.shape:
            raise RuntimeError("Distance and vertex area arrays have different shapes.")
        valid = np.isfinite(values) & np.isfinite(areaWeights) & (areaWeights > 0)
        values, areaWeights = values[valid], areaWeights[valid]
        if not len(values):
            return {"N": 0, "Area_mm2": 0.0, "Mean_mm": None, "SD_mm": None,
                    "Median_mm": None, "Min_mm": None, "Max_mm": None}
        totalArea = float(areaWeights.sum())
        avg = float(np.dot(values, areaWeights) / totalArea)
        sd = float(np.sqrt(np.dot(areaWeights, (values - avg) ** 2) / totalArea))
        order = np.argsort(values, kind="stable")
        orderedValues = values[order]
        orderedWeights = areaWeights[order]
        # Interpolate between weighted observation midpoints; equals numpy's
        # ordinary median when all weights are equal (including even N).
        midpoints = np.cumsum(orderedWeights) - 0.5 * orderedWeights
        med = float(np.interp(0.5 * totalArea, midpoints, orderedValues))
        return {"N": int(len(values)), "Area_mm2": totalArea,
                "Mean_mm": avg, "SD_mm": sd, "Median_mm": med,
                "Min_mm": float(np.min(values)), "Max_mm": float(np.max(values))}


    def forceRender(self):
        layoutManager = slicer.app.layoutManager()
        threeDWidget = layoutManager.threeDWidget(0)
        threeDView = threeDWidget.threeDView()
        threeDView.forceRender()
        slicer.app.processEvents()

    def computeRangeDistribution(self, values, bins, areaWeights):
        results = []
        values = np.asarray(values, dtype=float)
        areaWeights = np.asarray(areaWeights, dtype=float)
        valid = np.isfinite(values) & np.isfinite(areaWeights) & (areaWeights > 0)
        values, areaWeights = values[valid], areaWeights[valid]
        totalArea = float(areaWeights.sum())
        for lo, hi in bins:
            mask = (values >= lo) & ((values <= hi) if hi == bins[-1][1] else (values < hi))
            selectedArea = float(areaWeights[mask].sum())
            results.append({"Range": f"{lo}-{hi} mm", "Count": int(np.sum(mask)),
                            "Area_mm2": selectedArea,
                            "Percent": 100.0 * selectedArea / totalArea if totalArea > 0 else 0.0})
        return results

    def formatRangeDistributionLine(self, distRows):
        return " / ".join([f"{r['Range']}: {r['Percent']:.2f}%" for r in distRows])

    def computePoleDeltaDistribution(self, deltaValues, areaWeights, tolerance=0.5):
        deltaValues = np.asarray(deltaValues, dtype=float)
        areaWeights = np.asarray(areaWeights, dtype=float)
        valid = np.isfinite(deltaValues) & np.isfinite(areaWeights) & (areaWeights > 0)
        deltaValues, areaWeights = deltaValues[valid], areaWeights[valid]
        totalArea = float(areaWeights.sum())
        below = deltaValues < -tolerance
        within = (deltaValues >= -tolerance) & (deltaValues <= tolerance)
        above = deltaValues > tolerance
        def percentage(mask):
            return 100.0 * float(areaWeights[mask].sum()) / totalArea if totalArea else 0.0
        return {
            "BelowExpected_Count": int(np.sum(below)), "BelowExpected_Percent": percentage(below),
            "WithinExpected_Count": int(np.sum(within)), "WithinExpected_Percent": percentage(within),
            "AboveExpected_Count": int(np.sum(above)), "AboveExpected_Percent": percentage(above)
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

    def buildStatsRow(self, groupName, vals, areaWeights):
        return {"Group": groupName, **self.weightedStats(vals, areaWeights)}

    def buildPdfReport(self, pdfPath, step1Images, step3Images, step1StatsRows, step1DistRows,
                       step2Rows, overallRows, poleRows, poleDistRows):
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
            "- Step 3 pole-based statistics",
            "- Step 3 pole delta distributions",
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
                lines.append(f"  {row.get('Range', '')}: {row.get('Percent', 0):.2f}% of area ({row.get('Area_mm2', 0):.2f} mm2)")
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

        c.showPage(); new_page("Step 3 Pole-Based Statistics")
        lines = []
        for row in poleRows:
            lines.append(f"Pole: {row.get('Pole', '')}")
            for k, v in row.items():
                if k != "Pole": lines.append(f"  {k}: {v}")
            lines.append("")
        draw_lines(lines)

        c.showPage(); new_page("Step 3 Pole Delta Distributions")
        lines = []
        for row in poleDistRows:
            lines.append(f"Pole: {row.get('Pole', '')}")
            lines.append(f"  Within ±0.5 mm: {row.get('WithinExpected_Percent', 0):.2f}% ({row.get('WithinExpected_Count', 0)})")
            lines.append(f"  Below expected (< -0.5 mm): {row.get('BelowExpected_Percent', 0):.2f}% ({row.get('BelowExpected_Count', 0)})")
            lines.append(f"  Above expected (> +0.5 mm): {row.get('AboveExpected_Percent', 0):.2f}% ({row.get('AboveExpected_Count', 0)})")
            lines.append("")
        draw_lines(lines)

        draw_image_grid(step1Images, "Step 1 Standardized Views")
        draw_image_grid(step3Images, "Step 3 Standardized Views")

        c.save()
        return True, None

    def buildSummaryPdfReport(self, pdfPath, step1Images, step3Images, step1StatsRows, step1DistRows, overallRows, poleRows, poleDistRows):
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
        section("Pole summary", y)
        y -= 8 * mm
        poleDistMap = {r['Pole']: r for r in poleDistRows}
        for row in poleRows:
            pole = row.get('Pole','')
            dist = poleDistMap.get(pole, {})
            body(f"{pole}: mean {row.get('Mean_mm', None)} mm | ref {row.get('Reference_mm', None)} | diff {row.get('AbsoluteDifference_mm', None)}", 20 * mm, y)
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
        discreteScalars = np.clip(np.round(fullScalarsRaw / step) * step, 0.0, maxDisplayVal)

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

        # All descriptive statistics are continuous and surface-area weighted.
        # Quantised distances are retained exclusively for colour-map display.
        values = fullScalarsRaw
        valueWeights = self.vertexAreaWeights(outputPoly)
        filteredRawArray = filteredPd.GetArray("RawAbsoluteDistance")
        if filteredRawArray is None:
            raise RuntimeError("The filtered surface lost the RawAbsoluteDistance array.")
        filtered = vtk_to_numpy(filteredRawArray)
        filteredWeights = self.vertexAreaWeights(filteredPoly)

        step1Rows = [
            self.buildStatsRow("Global distance map", values, valueWeights),
            self.buildStatsRow(f"Filtered condylar surface <= {cutoffMm:.2f} mm", filtered, filteredWeights)
        ]
        bins = [(0, 1), (1, 2), (2, 4), (4, 5)]
        step1DistRows = self.computeRangeDistribution(filtered, bins, filteredWeights)

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
            "global_mean": step1Rows[0]["Mean_mm"],
            "filtered_n": step1Rows[1]["N"],
            "filtered_mean": step1Rows[1]["Mean_mm"],
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

        polesOnlyPoly = self.thresholdPolydataByPointScalarRange(polyOut, "AP_Manual_6pts", 1, 3)
        segmentedNode = self.createOrGetModelNode("Condyle_AP_Manual_6pts")
        segmentedNode.SetAndObservePolyData(polesOnlyPoly)
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

        overallDistanceArr = overallPoly.GetPointData().GetArray("AbsoluteDistance")
        if overallDistanceArr is None:
            raise RuntimeError("AbsoluteDistance array not found in CondyleFiltered_lt5mm.")
        overallDistances = vtk_to_numpy(overallDistanceArr)
        overallDistances = overallDistances[np.isfinite(overallDistances)]

        modelNode = self.getNode(segmentedModelName)
        poly = modelNode.GetPolyData()
        if poly is None or poly.GetNumberOfPoints() == 0:
            raise RuntimeError("Segmented pole model is empty.")

        pointData = poly.GetPointData()
        segmentArr = pointData.GetArray("AP_Manual_6pts")
        distanceArr = pointData.GetArray("AbsoluteDistance")
        if segmentArr is None:
            raise RuntimeError("AP_Manual_6pts array not found.")
        if distanceArr is None:
            raise RuntimeError("AbsoluteDistance array not found.")

        segments = vtk_to_numpy(segmentArr)
        distances = vtk_to_numpy(distanceArr)

        validMask = np.isfinite(distances)
        segments = segments[validMask]
        distances = distances[validMask]

        labels = {1: "Posterior", 2: "Middle", 3: "Anterior"}

        lines = []
        lines.append("FINAL FILTERED ANALYSIS\n")
        lines.append("--- Overall filtered condylar surface ---")
        lines.append(f"N points: {len(overallDistances)}")

        overallRows = [self.buildStatsRow("Overall filtered condylar surface", overallDistances)]
        if len(overallDistances) > 0:
            meanVal = float(np.mean(overallDistances)); sdVal = float(np.std(overallDistances, ddof=0)); medVal = float(np.median(overallDistances))
            minVal = float(np.min(overallDistances)); maxVal = float(np.max(overallDistances)); ciLow, ciHigh = self.meanCI95(overallDistances)
            lines.append(f"Mean: {meanVal:.4f} mm")
            lines.append(f"SD: {sdVal:.4f} mm")
            lines.append(f"Median: {medVal:.4f} mm")
            lines.append(f"Min: {minVal:.4f} mm")
            lines.append(f"Max: {maxVal:.4f} mm")
            lines.append(f"95% CI: {ciLow:.4f} to {ciHigh:.4f} mm\n")
        else:
            lines.append("No points available.\n")

        lines.append("POLE-BASED ANALYSIS\n")

        rows = []
        ref_values_per_point = np.zeros(len(segments), dtype=float)
        poleStatsRows = []
        poleDistRows = []

        for segId in [1, 2, 3]:
            vals = distances[segments == segId]
            ref = referenceValues[segId]
            label = labels[segId]
            lines.append(f"--- {label} pole ---")
            lines.append(f"Reference value: {ref:.4f} mm")
            lines.append(f"N points: {len(vals)}")

            if len(vals) == 0:
                lines.append("No points in this pole.\n")
                poleStatsRows.append({"Pole":label,"Reference_mm":ref,"N":0,"Mean_mm":None,"SD_mm":None,"Median_mm":None,"Min_mm":None,"Max_mm":None,"CI95_low_mm":None,"CI95_high_mm":None,"AbsoluteDifference_mm":None,"PercentDifference":None})
                poleDistRows.append({"Pole":label,"BelowExpected_Count":0,"BelowExpected_Percent":0.0,"WithinExpected_Count":0,"WithinExpected_Percent":0.0,"AboveExpected_Count":0,"AboveExpected_Percent":0.0})
                continue

            meanVal = float(np.mean(vals)); sdVal = float(np.std(vals, ddof=0)); medVal = float(np.median(vals))
            minVal = float(np.min(vals)); maxVal = float(np.max(vals)); ciLow, ciHigh = self.meanCI95(vals)
            diffAbs = meanVal - ref; diffPct = ((meanVal - ref) / ref * 100.0) if ref != 0 else np.nan

            lines.append(f"Mean: {meanVal:.4f} mm")
            lines.append(f"SD: {sdVal:.4f} mm")
            lines.append(f"Median: {medVal:.4f} mm")
            lines.append(f"Min: {minVal:.4f} mm")
            lines.append(f"Max: {maxVal:.4f} mm")
            lines.append(f"95% CI: {ciLow:.4f} to {ciHigh:.4f} mm")
            lines.append(f"Absolute difference vs reference: {diffAbs:+.4f} mm")
            lines.append(f"Percent difference vs reference: {diffPct:+.2f}%")

            poleDeltaRaw = vals - ref
            poleDist = self.computePoleDeltaDistribution(poleDeltaRaw, tolerance=0.5)
            lines.append(f"Within expected (±0.5 mm): {poleDist['WithinExpected_Percent']:.2f}%")
            lines.append(f"Below expected (< -0.5 mm): {poleDist['BelowExpected_Percent']:.2f}%")
            lines.append(f"Above expected (> +0.5 mm): {poleDist['AboveExpected_Percent']:.2f}%\n")

            rows.append({"pole":label,"reference_mm":ref,"n":int(len(vals)),"mean_mm":meanVal,"sd_mm":sdVal,"median_mm":medVal,"min_mm":minVal,"max_mm":maxVal,"ci95_low_mm":ciLow,"ci95_high_mm":ciHigh,"diff_abs_mm":diffAbs,"diff_pct":diffPct})
            poleStatsRows.append({"Pole":label,"Reference_mm":ref,"N":int(len(vals)),"Mean_mm":meanVal,"SD_mm":sdVal,"Median_mm":medVal,"Min_mm":minVal,"Max_mm":maxVal,"CI95_low_mm":ciLow,"CI95_high_mm":ciHigh,"AbsoluteDifference_mm":diffAbs,"PercentDifference":diffPct})
            poleDistRows.append({"Pole":label, **poleDist})
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

        legendNode = self.addOrUpdateColorLegend(compNode, titleText="Difference from pole reference (mm)")
        legendNode.SetVisibility(True)
        self.showOnlyFinalComparison()
        self.forceRender()

        exportedFiles=[]; excelPath=None; pdfPath=None; summaryPdfPath=None; excelWarning=None; pdfWarning=None; summaryPdfWarning=None
        if exportFolder:
            self.ensureDir(exportFolder)
            excelPath=self.getExcelPath(exportFolder); pdfPath=self.getPdfPath(exportFolder); summaryPdfPath=self.getPdfSummaryPath(exportFolder)
            step3Folder=self.ensureDir(os.path.join(exportFolder, "Step3"))
            legendNode=self.addOrUpdateColorLegend(compNode, titleText="Difference from pole reference (mm)")
            legendNode.SetVisibility(True)
            self.forceRender()
            exportedFiles=self.captureStandardViews(compNode, step3Folder, "Step3_ReferenceComparison")

            if OPENPYXL_AVAILABLE:
                wb=self.getOrCreateWorkbook(excelPath)
                self.writeSheet(wb, "Step3_OverallFiltered", overallRows)
                self.writeSheet(wb, "Step3_Poles", poleStatsRows)
                self.writeSheet(wb, "Step3_PoleDistribution", poleDistRows)
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

            ok,msg=self.buildPdfReport(pdfPath, step1Images, exportedFiles, step1StatsRows, step1DistRows, step2Rows, overallRows, poleStatsRows, poleDistRows)
            if not ok:
                pdfWarning=msg

            ok2,msg2=self.buildSummaryPdfReport(summaryPdfPath, step1Images, exportedFiles, step1StatsRows, step1DistRows, overallRows, poleStatsRows, poleDistRows)
            if not ok2:
                summaryPdfWarning=msg2

        self.lastStep3Data = {"overall_rows": overallRows, "pole_rows": poleStatsRows, "pole_distribution_rows": poleDistRows, "images": exportedFiles}

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
