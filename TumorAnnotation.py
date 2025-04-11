import os
import json
import numpy as np
import vtk
import qt
import ctk
import slicer
from slicer.ScriptedLoadableModule import *


class TumorAnnotation(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class."""

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "Tumor Annotation"
        self.parent.categories = ["Segmentation"]
        self.parent.dependencies = []
        self.parent.contributors = ["Your Name"]
        self.parent.helpText = """
        Annotate tumors by placing extreme points and generating bounding boxes.
        """
        self.parent.acknowledgementText = """
        Developed for tumor annotation workflow.
        """


class TumorAnnotationWidget(ScriptedLoadableModuleWidget):
    """Uses ScriptedLoadableModuleWidget base class."""

    def __init__(self, parent=None):
        ScriptedLoadableModuleWidget.__init__(self, parent)
        self.currentFileIndex = 0
        self.pointCoordinates = []
        self.boundingBoxNode = None
        self.boundingBoxModel = None
        self.fiducialNode = None
        self.placementActive = False

    def setup(self):
        ScriptedLoadableModuleWidget.setup(self)

        # Load UI from file
        uiFile = os.path.join(os.path.dirname(__file__), 
                             'Resources', 'UI', 'TumorAnnotation.ui')
        self.widget = slicer.util.loadUI(uiFile)
        self.layout.addWidget(self.widget)

        # Connect UI elements
        self.ui = slicer.util.childWidgetVariables(self.widget)
        self.ui.directoryButton.directoryChanged.connect(self.onDirectoryChanged)
        self.ui.loadButton.clicked.connect(self.onLoadButtonClicked)
        self.ui.placePointsButton.clicked.connect(self.enterPlacementMode)
        self.ui.createBBoxButton.clicked.connect(self.onCreateBBoxButtonClicked)
        self.ui.relaxSlider.valueChanged.connect(self.onRelaxSliderChanged)
        self.ui.submitButton.clicked.connect(self.onSubmitButtonClicked)
        self.ui.nextButton.clicked.connect(self.onNextButtonClicked)

        # Initialize UI
        self.updateUI()

        # Start in placement mode
        self.enterPlacementMode()

    def enterPlacementMode(self):
        """Enter persistent point placement mode"""
        if not self.fiducialNode:
            self.fiducialNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLMarkupsFiducialNode', 'ExtremePoints')
            self.fiducialNode.CreateDefaultDisplayNodes()
            self.fiducialNode.GetDisplayNode().SetSelectedColor(1, 0, 0)
            self.fiducialNode.GetDisplayNode().SetGlyphScale(2.0)
            self.fiducialNode.AddObserver(slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent, self.onPointPlaced)

        selectionNode = slicer.app.applicationLogic().GetSelectionNode()
        selectionNode.SetReferenceActivePlaceNodeID(self.fiducialNode.GetID())

        interactionNode = slicer.app.applicationLogic().GetInteractionNode()
        interactionNode.SetPlaceModePersistence(1)  # stay in place mode
        interactionNode.SetCurrentInteractionMode(interactionNode.Place)

        self.placementActive = True
        self.ui.placePointsButton.setChecked(True)

    def updateUI(self):
        """Update UI elements based on current state"""
        hasFiles = hasattr(self, 'niftiFiles') and len(self.niftiFiles) > 0
        hasLoaded = hasFiles and self.currentFileIndex < len(self.niftiFiles)
        
        self.ui.placePointsButton.enabled = hasLoaded
        self.ui.createBBoxButton.enabled = hasLoaded and (hasattr(self, 'fiducialNode') and self.fiducialNode.GetNumberOfControlPoints() >= 6)
        self.ui.relaxSlider.enabled = hasLoaded and self.boundingBoxNode is not None
        self.ui.submitButton.enabled = hasLoaded and self.boundingBoxNode is not None
        self.ui.nextButton.enabled = hasFiles and self.currentFileIndex < len(self.niftiFiles) - 1

        if hasFiles:
            progress = int((self.currentFileIndex / len(self.niftiFiles)) * 100)
            self.ui.progressBar.value = progress

    def onDirectoryChanged(self):
        """Called when directory is changed"""
        if hasattr(self, 'niftiFiles'):
            del self.niftiFiles
        self.currentFileIndex = 0
        self.clearAnnotation()
        self.updateUI()

    def onLoadButtonClicked(self):
        """Load NIfTI files from selected directory"""
        directory = self.ui.directoryButton.directory
        if not directory:
            slicer.util.errorDisplay("Please select a directory first")
            return

        self.niftiFiles = [f for f in os.listdir(directory) 
                         if f.lower().endswith('.nii') or f.lower().endswith('.nii.gz')]
        self.niftiFiles.sort()
        self.currentFileIndex = 0
        
        if not self.niftiFiles:
            slicer.util.errorDisplay("No NIfTI files found in selected directory")
            return
            
        self.loadCurrentFile()
        self.updateUI()

    def loadCurrentFile(self):
        """Load the current NIfTI file"""
        if not hasattr(self, 'niftiFiles') or self.currentFileIndex >= len(self.niftiFiles):
            return
            
        self.clearAnnotation()

        # Load new volume
        filePath = os.path.join(self.ui.directoryButton.directory, 
                              self.niftiFiles[self.currentFileIndex])
        slicer.util.loadVolume(filePath)
        
        # Start in placement mode automatically
        self.enterPlacementMode()

    def clearAnnotation(self):
        """Clear current annotation"""
        self.pointCoordinates = []
        if hasattr(self, 'fiducialNode') and self.fiducialNode:
            slicer.mrmlScene.RemoveNode(self.fiducialNode)
            self.fiducialNode = None
        if self.boundingBoxNode:
            slicer.mrmlScene.RemoveNode(self.boundingBoxNode)
            self.boundingBoxNode = None
        if self.boundingBoxModel:
            slicer.mrmlScene.RemoveNode(self.boundingBoxModel)
            self.boundingBoxModel = None

    def onPointPlaced(self, caller, event):
        """Handle new point placement"""
        if self.fiducialNode.GetNumberOfControlPoints() <= 6:
            pointPos = [0, 0, 0]
            self.fiducialNode.GetNthControlPointPosition(
                self.fiducialNode.GetNumberOfControlPoints()-1, pointPos)
            self.pointCoordinates.append(pointPos.copy())
        
        self.updateUI()

    def onCreateBBoxButtonClicked(self):
        """Create bounding box from placed points, aligned with the volume's axes"""
        if not hasattr(self, 'fiducialNode') or self.fiducialNode.GetNumberOfControlPoints() < 6:  # Fixed typo here
            slicer.util.errorDisplay("Please place all 6 points first")
            return

        # Get current volume node
        volumeNode = slicer.app.layoutManager().sliceWidget("Red").sliceLogic().GetBackgroundLayer().GetVolumeNode()
        if not volumeNode:
            slicer.util.errorDisplay("No volume loaded")
            return

        # Get volume's IJK to RAS matrix
        ijkToRas = vtk.vtkMatrix4x4()
        volumeNode.GetIJKToRASMatrix(ijkToRas)

        # Convert points to numpy array
        points = np.array(self.pointCoordinates)

        # Compute axis-aligned bounding box in RAS coordinates
        minCoords = np.min(points, axis=0)
        maxCoords = np.max(points, axis=0)

        # Optional: relax the box
        relaxation = self.ui.relaxSlider.value
        minCoords -= relaxation
        maxCoords += relaxation

        center = (minCoords + maxCoords) / 2
        size = maxCoords - minCoords

        # Create ROI node
        self.boundingBoxNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLMarkupsROINode', 'BoundingBox')
        self.boundingBoxNode.CreateDefaultDisplayNodes()
        self.boundingBoxNode.GetDisplayNode().SetColor(0, 1, 0)  # Green
        
        # First set the center and size in RAS coordinates
        self.boundingBoxNode.SetCenter(center)
        self.boundingBoxNode.SetSize(size)

        # Now align with volume axes
        # Get the volume's orientation vectors (columns of the rotation matrix)
        x_vector = np.array([ijkToRas.GetElement(0,0), ijkToRas.GetElement(1,0), ijkToRas.GetElement(2,0)])
        y_vector = np.array([ijkToRas.GetElement(0,1), ijkToRas.GetElement(1,1), ijkToRas.GetElement(2,1)])
        z_vector = np.array([ijkToRas.GetElement(0,2), ijkToRas.GetElement(1,2), ijkToRas.GetElement(2,2)])

        # Normalize the vectors
        x_vector = x_vector / np.linalg.norm(x_vector)
        y_vector = y_vector / np.linalg.norm(y_vector)
        z_vector = z_vector / np.linalg.norm(z_vector)

        # Create rotation matrix that aligns with volume axes
        rotationMatrix = vtk.vtkMatrix4x4()
        for i in range(3):
            rotationMatrix.SetElement(i, 0, x_vector[i])
            rotationMatrix.SetElement(i, 1, y_vector[i])
            rotationMatrix.SetElement(i, 2, z_vector[i])
            rotationMatrix.SetElement(i, 3, center[i])  # Set translation component
        
        # The rotation matrix should include the translation to keep the box centered
        rotationMatrix.SetElement(3, 3, 1)  # Homogeneous coordinate

        # Apply the transformation to the bounding box
        self.boundingBoxNode.GetObjectToNodeMatrix().DeepCopy(rotationMatrix)
        self.boundingBoxNode.Modified()

        self.updateUI()

        # Go back placement mode
        self.enterPlacementMode()

    def onRelaxSliderChanged(self, value):
        """Adjust bounding box size while maintaining orientation"""
        if not self.boundingBoxNode or len(self.pointCoordinates) < 6:
            return

        points = np.array(self.pointCoordinates)
        minCoords = np.min(points, axis=0)
        maxCoords = np.max(points, axis=0)

        minCoords -= value
        maxCoords += value

        center = (minCoords + maxCoords) / 2
        size = maxCoords - minCoords

        # Get current transform
        transformNode = self.boundingBoxNode.GetParentTransformNode()
        if transformNode:
            transformMatrix = vtk.vtkMatrix4x4()
            transformNode.GetMatrixTransformToParent(transformMatrix)
            
            # Update position in transform
            transformMatrix.SetElement(0, 3, center[0])
            transformMatrix.SetElement(1, 3, center[1])
            transformMatrix.SetElement(2, 3, center[2])
            transformNode.SetMatrixTransformToParent(transformMatrix)

        self.boundingBoxNode.SetSize(size)

        # Go back placement mode
        self.enterPlacementMode()

    def onSubmitButtonClicked(self):
        """Save the annotation data to JSON"""
        if not self.boundingBoxNode or len(self.pointCoordinates) < 6:
            slicer.util.errorDisplay("Please create a bounding box first")
            return
            
        data = {
            "filename": self.niftiFiles[self.currentFileIndex],
            "points": self.pointCoordinates,
            "bounding_box": {
                "center": [0, 0, 0],
                "size": [0, 0, 0]
            },
            "relaxation": self.ui.relaxSlider.value
        }
        
        self.boundingBoxNode.GetXYZ(data["bounding_box"]["center"])
        radius = [0, 0, 0]
        self.boundingBoxNode.GetRadiusXYZ(radius)
        data["bounding_box"]["size"] = [r*2 for r in radius]
        
        outputDir = os.path.join(self.ui.directoryButton.directory, "annotations")
        os.makedirs(outputDir, exist_ok=True)
            
        outputPath = os.path.join(
            outputDir, 
            os.path.splitext(self.niftiFiles[self.currentFileIndex])[0] + ".json")
        
        with open(outputPath, 'w') as f:
            json.dump(data, f, indent=2)
            
        slicer.util.infoDisplay(f"Annotation saved to {outputPath}")

    def onNextButtonClicked(self):
        """Move to next sample"""
        if self.currentFileIndex < len(self.niftiFiles) - 1:
            self.currentFileIndex += 1
            self.loadCurrentFile()
            self.updateUI()


class TumorAnnotationLogic(ScriptedLoadableModuleLogic):
    """Implement module logic."""
    pass