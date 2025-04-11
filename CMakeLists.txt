cmake_minimum_required(VERSION 3.16)
project(TumorAnnotationExtension)

find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

set(MODULE_NAME TumorAnnotation)
set(MODULE_TITLE "Tumor Annotation")

slicerMacroBuildScriptedModule(
  NAME ${MODULE_NAME}
  TITLE ${MODULE_TITLE}
  RESOURCES Resources/UI/TumorAnnotation.ui
  SCRIPTS TumorAnnotation.py
  INSTALL_RUNTIME_DESTINATION ${Slicer_INSTALL_QTSCRIPTEDMODULES_BIN_DIR}
  INSTALL_LIBRARY_DESTINATION ${Slicer_INSTALL_QTSCRIPTEDMODULES_LIB_DIR}
)