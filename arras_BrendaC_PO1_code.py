# -*- coding: utf-8 -*-
# P01 - Procedural Tree Generator
# I made this to build different tree shapes in Maya without modeling each one.
# Run this in Maya's Python Script Editor, not regular Python.
# Example (change the path to wherever the file is saved):
# import runpy
# tree_tool = runpy.run_path(r"C:\Users\bca240000\Documents\Programming_Project_01\Asset-Generator")
# tree_tool["show_ui"]()

import math
import os
import random
import traceback

try:
    import maya.cmds as cmds
    import maya.mel as mel
    import maya.OpenMayaUI as omui
except ImportError as exc:
    raise RuntimeError(
        "ARRAS Tree Generator must run inside Autodesk Maya. "
        "Maya import failed: {0}".format(exc)
    )

# Try PySide2 first since that's what we use in class.
# The second option is for newer versions of Maya.
try:
    from PySide2 import QtCore, QtGui, QtWidgets
    from shiboken2 import wrapInstance
    QT_BINDING = "PySide2"
except ImportError:
    try:
        from PySide6 import QtCore, QtGui, QtWidgets
        from shiboken6 import wrapInstance
        QT_BINDING = "PySide6"
    except ImportError as exc:
        raise RuntimeError(
            "ARRAS Tree Generator needs Maya's PySide2/shiboken2 "
            "(or PySide6/shiboken6 on recent Maya releases). "
            "Import failed: {0}".format(exc)
        )

WINDOW_NAME = "ARRAS_P01_TreeGenerator_Dialog"
SHELF_TOOLTIP = "ARRAS P01 | Procedural Tree & Grove Generator"
SHELF_LABEL = "Tree Gen"

# Each style has different branch spread, height, and shape.
STYLES = {
    "Oak":    {"spread": 1.00, "rise": 0.52, "cluster": 1.00, "tall": 0.86, "droop": 0.00},
    "Pine":   {"spread": 0.66, "rise": 0.86, "cluster": 0.75, "tall": 1.25, "droop": 0.00},
    "Willow": {"spread": 1.16, "rise": 0.24, "cluster": 0.87, "tall": 1.27, "droop": 0.68},
    "Sakura": {"spread": 1.06, "rise": 0.52, "cluster": 1.07, "tall": 0.88, "droop": 0.00},
}

# These are the colors used for the different seasons.
PALETTES = {
    "Spring": {"bark": (0.31, 0.18, 0.10), "leaf": (0.28, 0.58, 0.20),
               "accent": (0.50, 0.74, 0.31), "ground": (0.30, 0.37, 0.19)},
    "Summer": {"bark": (0.27, 0.14, 0.08), "leaf": (0.12, 0.39, 0.14),
               "accent": (0.27, 0.55, 0.19), "ground": (0.24, 0.32, 0.14)},
    "Autumn": {"bark": (0.29, 0.16, 0.09), "leaf": (0.77, 0.26, 0.06),
               "accent": (0.94, 0.51, 0.09), "ground": (0.36, 0.26, 0.14)},
    "Winter": {"bark": (0.27, 0.25, 0.24), "leaf": (0.50, 0.64, 0.71),
               "accent": (0.77, 0.83, 0.87), "ground": (0.49, 0.55, 0.60)},
}

# Sakura gets its own pink colors instead of the usual green leaves.
SAKURA_COLORS = {
    "Spring": ((0.93, 0.42, 0.61), (1.00, 0.72, 0.80)),
    "Summer": ((0.81, 0.30, 0.49), (0.99, 0.57, 0.72)),
    "Autumn": ((0.82, 0.38, 0.32), (0.97, 0.57, 0.44)),
    "Winter": ((0.72, 0.65, 0.71), (0.88, 0.80, 0.85)),
}


# --------------------------------------------------------------------------
# Small math helpers for moving branches around
# --------------------------------------------------------------------------

def _add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _scale(vec, factor):
    return (vec[0] * factor, vec[1] * factor, vec[2] * factor)


def _unit(vec):
    length = math.sqrt(sum(component * component for component in vec))
    return _scale(vec, 1.0 / length) if length > 1.0e-8 else (0.0, 1.0, 0.0)


def validate_settings(settings):
    """Check that the settings are in range."""
    limits = {
        "height": (3.0, 16.0),
        "canopy_width": (2.0, 10.0),
        "branch_count": (3, 9),
        "branch_levels": (1, 3),
        "foliage_density": (1, 4),
        "tree_count": (1, 6),
        "spacing": (3.0, 22.0),
        "seed": (0, 999999),
    }
    # Stop any values that would be outside the slider limits.
    for key, (minimum, maximum) in limits.items():
        value = settings[key]
        if not minimum <= value <= maximum:
            raise ValueError("{0} must be between {1} and {2}".format(
                key, minimum, maximum))
    if settings["style"] not in STYLES:
        raise ValueError("Choose a valid tree style.")
    if settings["season"] not in PALETTES:
        raise ValueError("Choose a valid season.")
    if not isinstance(settings["create_base"], bool):
        raise ValueError("create_base must be True or False.")


def _material(name, rgb):
    """Make a basic material using the chosen color."""
    shader = cmds.shadingNode("lambert", asShader=True, name=name)
    group = cmds.sets(renderable=True, noSurfaceShader=True,
                      empty=True, name=name + "SG")
    cmds.connectAttr(shader + ".outColor", group + ".surfaceShader", force=True)
    cmds.setAttr(shader + ".color", *rgb, type="double3")
    return group


def _assign(mesh, shading_group):
    if mesh and cmds.objExists(mesh):
        cmds.sets(mesh, edit=True, forceElement=shading_group)


def _merge(meshes, name):
    """Join the separate pieces into one mesh."""
    existing = [m for m in meshes if cmds.objExists(m)]
    if not existing:
        return None
    if len(existing) == 1:
        return cmds.rename(existing[0], name)

    result = cmds.polyUnite(*existing, mergeUVSets=1)[0]
    result = cmds.rename(result, name)
    cmds.delete(result, constructionHistory=True)
    # Clear the original pieces after the combined mesh is finished.
    cmds.delete(existing)
    return result


def _make_trunk(height, radius, name):
    """Make the trunk out of a cylinder."""
    trunk = cmds.polyCylinder(
        radius=radius, height=height,
        subdivisionsAxis=10, subdivisionsHeight=5,
        subdivisionsCaps=1, constructionHistory=False, name=name
    )[0]
    # Narrow the top a little so the trunk is not just a straight tube.
    count = cmds.polyEvaluate(trunk, vertex=True)
    for index in range(count):
        vertex = "{0}.vtx[{1}]".format(trunk, index)
        x, y, z = cmds.xform(vertex, query=True, objectSpace=True, translation=True)
        t = max(0.0, min(1.0, (y + height * 0.5) / height))
        taper = 1.0 - 0.54 * t
        cmds.xform(vertex, objectSpace=True,
                   translation=(x * taper, y, z * taper))
    cmds.xform(trunk, worldSpace=True, translation=(0.0, height * 0.5, 0.0))
    return trunk


def _make_branch(start, direction, length, radius, name):
    """Use a cone for each branch."""
    direction = _unit(direction)
    end = _add(start, _scale(direction, length))
    midpoint = _scale(_add(start, end), 0.5)
    branch = cmds.polyCone(
        radius=max(radius, 0.026), height=length,
        subdivisionsAxis=7, subdivisionsHeight=1,
        subdivisionsCap=1, constructionHistory=False, name=name
    )[0]
    # Turn the cone so it points in the direction of the branch.
    rotation = cmds.angleBetween(
        euler=True, vector1=(0.0, 1.0, 0.0), vector2=direction
    )
    cmds.xform(branch, worldSpace=True, translation=midpoint)
    cmds.xform(branch, worldSpace=True, rotation=rotation)
    return branch, end


def _leaf(position, size, style, rng, name):
    """Make one leaf clump with a little random variation."""
    sphere = cmds.polySphere(
        radius=1.0, subdivisionsX=7, subdivisionsY=5,
        constructionHistory=False, name=name
    )[0]
    # Change the scale and rotation so the leaves do not all match.
    scale = rng.uniform(0.78, 1.22) * size
    cmds.setAttr(sphere + ".scaleX", scale * rng.uniform(0.88, 1.12))
    cmds.setAttr(sphere + ".scaleY", scale * style["tall"])
    cmds.setAttr(sphere + ".scaleZ", scale * rng.uniform(0.88, 1.12))
    cmds.xform(sphere, worldSpace=True, translation=position)
    cmds.rotate(rng.uniform(-25.0, 25.0), rng.uniform(0.0, 360.0),
                rng.uniform(-25.0, 25.0), sphere, worldSpace=True)
    return sphere


def _grow(start, direction, length, radius, level, maximum,
          canopy_width, density, style, rng, branches, leaves_a, leaves_b,
          created, prefix):
    """Keep splitting branches until the last level."""
    segment, tip = _make_branch(start, direction, length, radius,
                                prefix + "_Branch#")
    created.append(segment)
    branches.append(segment)

    # At the last level, add leaves instead of more branches.
    if level >= maximum - 1:
        leaf_size = max(0.16, canopy_width * 0.063) * style["cluster"]
        for _ in range(density):
            theta = rng.uniform(0.0, math.pi * 2.0)
            r = rng.uniform(0.0, leaf_size * 1.1)
            position = (
                tip[0] + math.cos(theta) * r,
                tip[1] + rng.uniform(-0.35, 0.60) * leaf_size,
                tip[2] + math.sin(theta) * r,
            )
            cluster = _leaf(position, leaf_size, style, rng, prefix + "_Leaf#")
            created.append(cluster)
            (leaves_b if rng.random() < 0.30 else leaves_a).append(cluster)
        return

    # Split each branch into two smaller branches.
    for child in range(2):
        angle = (child * math.pi) + rng.uniform(-0.65, 0.65)
        side = (math.cos(angle), 0.0, math.sin(angle))
        child_dir = _unit((
            direction[0] * 0.62 + side[0] * rng.uniform(0.35, 0.60),
            direction[1] * 0.52 + rng.uniform(0.20, 0.44) - style["droop"],
            direction[2] * 0.62 + side[2] * rng.uniform(0.35, 0.60),
        ))
        _grow(
            tip, child_dir, length * rng.uniform(0.57, 0.73),
            radius * 0.67, level + 1, maximum,
            canopy_width, density, style, rng,
            branches, leaves_a, leaves_b, created, prefix,
        )


def _build_tree(root, index, settings, materials, scale_factor):
    """Put the trunk, branches, and leaves together for one tree."""
    style = STYLES[settings["style"]]
    # A seed makes the same settings give the same tree again.
    rng = random.Random(settings["seed"] + index * 1009)
    name = root + "_Tree{0:02d}".format(index + 1)
    height = settings["height"] * scale_factor
    width = settings["canopy_width"] * scale_factor * style["spread"]
    radius = max(0.13, height * 0.037)

    branches, leaves_a, leaves_b = [], [], []
    created = []
    # Keep everything for this tree in its own group.
    tree_group = cmds.group(empty=True, name=name + "_GRP", parent=root)
    try:
        trunk = _make_trunk(height, radius, name + "_Trunk_GEO")
        created.append(trunk)
        density = settings["foliage_density"]
        # I used fewer leaves for the winter version.
        if settings["season"] == "Winter":
            density = max(1, density - 1)

        # Spread the main branches around the trunk.
        count = settings["branch_count"]
        for i in range(count):
            phi = (2.0 * math.pi * i / float(count)) + rng.uniform(-0.17, 0.17)
            outward = (math.cos(phi), 0.0, math.sin(phi))
            rise = 0.23 + 0.65 * ((i + 0.5) / float(count))
            start = (outward[0] * radius * 0.32,
                     height * rise, outward[2] * radius * 0.32)
            direction = _unit((outward[0], style["rise"] + rng.uniform(-0.12, 0.12),
                               outward[2]))
            branch_length = width * rng.uniform(0.46, 0.65)
            if settings["style"] == "Pine":
                branch_length *= 1.58 - rise * 0.82  # broad base, narrow crown
            elif settings["style"] == "Willow":
                branch_length *= 1.12
            _grow(
                start, direction, branch_length,
                max(0.055, radius * rng.uniform(0.26, 0.37)),
                0, settings["branch_levels"], width, density,
                style, rng, branches, leaves_a, leaves_b, created, name,
            )

        branch_geo = _merge(branches, name + "_Branches_GEO")
        if branch_geo:
            created.append(branch_geo)
        foliage_geo = _merge(leaves_a, name + "_Foliage_GEO")
        if foliage_geo:
            created.append(foliage_geo)
        accents_geo = _merge(leaves_b, name + "_FoliageAccent_GEO")
        if accents_geo:
            created.append(accents_geo)

        # Give the finished parts their colors and move them into the group.
        for obj, shader in (
            (trunk, materials["bark"]),
            (branch_geo, materials["bark"]),
            (foliage_geo, materials["leaf"]),
            (accents_geo, materials["accent"]),
        ):
            if obj and cmds.objExists(obj):
                _assign(obj, shader)
                cmds.parent(obj, tree_group)

        # Optional base under each tree.
        if settings["create_base"]:
            disk = cmds.polyCylinder(
                radius=width * 0.73, height=0.16,
                subdivisionsAxis=24, subdivisionsHeight=1,
                constructionHistory=False, name=name + "_Base_GEO"
            )[0]
            created.append(disk)
            cmds.xform(disk, worldSpace=True, translation=(0.0, -0.10, 0.0))
            _assign(disk, materials["ground"])
            cmds.parent(disk, tree_group)
        return tree_group
    except Exception:
        # If something fails, delete the unfinished tree.
        for obj in created:
            if cmds.objExists(obj):
                cmds.delete(obj)
        if cmds.objExists(tree_group):
            cmds.delete(tree_group)
        raise


def generate_asset(settings):
    """Generate one tree or a small group of trees."""
    validate_settings(settings)
    root = cmds.group(empty=True, name="ARRAS_PTG_Generated#")
    palette = dict(PALETTES[settings["season"]])
    if settings["style"] == "Sakura":
        palette["leaf"], palette["accent"] = SAKURA_COLORS[settings["season"]]

    # Make new materials so older trees can keep their original colors.
    shader_nodes = []
    try:
        shaders = {}
        for material_name in ("bark", "leaf", "accent", "ground"):
            full_name = root + "_" + material_name.capitalize() + "_MAT"
            shaders[material_name] = _material(full_name, palette[material_name])
            shader_nodes.append(full_name)
            shader_nodes.append(full_name + "SG")

        amount = settings["tree_count"]
        # Arrange multiple trees in rows instead of stacking them together.
        columns = int(math.ceil(math.sqrt(amount)))
        rows = int(math.ceil(amount / float(columns)))
        grove_rng = random.Random(settings["seed"] + 31)
        for i in range(amount):
            size = 1.0 if amount == 1 else grove_rng.uniform(0.84, 1.16)
            tree = _build_tree(root, i, settings, shaders, size)
            column, row = i % columns, i // columns
            x = (column - (columns - 1) / 2.0) * settings["spacing"]
            z = (row - (rows - 1) / 2.0) * settings["spacing"]
            cmds.xform(tree, worldSpace=True, translation=(x, 0.0, z))
        return root
    except Exception:
        if cmds.objExists(root):
            cmds.delete(root)
        for node in shader_nodes:
            if cmds.objExists(node):
                cmds.delete(node)
        raise


# --------------------------------------------------------------------------
# Making the little tree icon for Maya's shelf
# --------------------------------------------------------------------------

def _icon_path():
    directory = os.path.join(cmds.internalVar(userScriptDir=True),
                             "arras_p01_tree_icons")
    if not os.path.isdir(directory):
        os.makedirs(directory)
    path = os.path.join(directory, "arras_tree_shelf.png")

    # Draw the icon using Qt so I do not need a separate image file.
    image = QtGui.QPixmap(64, 64)
    image.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(image)
    try:
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(QtGui.QColor(31, 43, 38))
        painter.drawRoundedRect(QtCore.QRectF(2, 2, 60, 60), 10, 10)
        painter.setBrush(QtGui.QColor(145, 101, 66))
        painter.drawRect(QtCore.QRectF(28, 34, 8, 20))
        painter.setBrush(QtGui.QColor(83, 157, 89))
        painter.drawEllipse(QtCore.QRectF(11, 17, 31, 29))
        painter.setBrush(QtGui.QColor(110, 189, 103))
        painter.drawEllipse(QtCore.QRectF(24, 14, 29, 29))
        painter.setBrush(QtGui.QColor(160, 211, 124))
        painter.drawEllipse(QtCore.QRectF(17, 8, 29, 29))
    finally:
        painter.end()
    if not image.save(path, "PNG"):
        raise RuntimeError("Could not write the custom shelf icon to: " + path)
    return path


def install_shelf_button():
    """Add a button to the current Maya shelf."""
    try:
        shelf_top = mel.eval('global string $gShelfTopLevel; $gShelfTopLevel;')
        if not shelf_top or not cmds.tabLayout(shelf_top, exists=True):
            raise RuntimeError("Maya's shelf UI is not available yet.")
        selected = cmds.tabLayout(shelf_top, query=True, selectTab=True)
        if not selected or not cmds.shelfLayout(selected, exists=True):
            raise RuntimeError("Select a visible Maya shelf tab first.")
        source_file = os.path.abspath(__file__)
        if not os.path.isfile(source_file):
            raise RuntimeError("Save this Python file to disk before installing the shelf.")

        # Clicking the shelf button runs this file and opens the window.
        command = (
            "import runpy\n"
            "_arras_p01 = runpy.run_path({0})\n"
            "_arras_p01['show_ui'](install_shelf=False)\n"
        ).format(repr(source_file))
        icon = _icon_path()

        # Remove the old Tree Gen button so there is only one.
        children = cmds.shelfLayout(selected, query=True, childArray=True) or []
        for child in children:
            try:
                if cmds.shelfButton(child, query=True,
                                    annotation=True) == SHELF_TOOLTIP:
                    cmds.deleteUI(child)
            except Exception:
                pass  # Shelf separators are not shelfButtons.

        cmds.shelfButton(
            parent=selected, label=SHELF_LABEL,
            annotation=SHELF_TOOLTIP,
            image=icon, style="iconOnly",
            sourceType="python", command=command,
        )
        return True
    except Exception as error:
        cmds.warning("ARRAS P01 shelf button not installed: {0}".format(error))
        return False


# --------------------------------------------------------------------------
# The window and controls for the tree generator
# --------------------------------------------------------------------------

def _maya_window():
    pointer = omui.MQtUtil.mainWindow()
    return wrapInstance(int(pointer), QtWidgets.QWidget) if pointer else None


class TreeGeneratorWindow(QtWidgets.QDialog):
    """The main window with all the tree settings."""

    def __init__(self, parent=None):
        super(TreeGeneratorWindow, self).__init__(parent)
        self.setObjectName(WINDOW_NAME)
        self.setWindowTitle("ARRAS | Procedural Tree Generator")
        self.setMinimumWidth(420)
        self.resize(470, 690)
        self.setWindowFlags(self.windowFlags() &
                            ~QtCore.Qt.WindowContextHelpButtonHint)
        self.last_output = None
        self._setup()
        self._style()
        self._count_changed(self.number.value())

    @staticmethod
    def _spin(minimum, maximum, initial):
        widget = QtWidgets.QSpinBox()
        widget.setRange(minimum, maximum)
        widget.setValue(initial)
        return widget

    @staticmethod
    def _double(minimum, maximum, initial, suffix=""):
        widget = QtWidgets.QDoubleSpinBox()
        widget.setRange(minimum, maximum)
        widget.setValue(initial)
        widget.setDecimals(1)
        widget.setSingleStep(0.5)
        widget.setSuffix(suffix)
        return widget

    def _setup(self):
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(9)

        title = QtWidgets.QLabel("PROCEDURAL TREE + GROVE")
        title.setObjectName("Heading")
        outer.addWidget(title)
        subtitle = QtWidgets.QLabel("Model stylized trees in Maya using adjustable parameters.")
        subtitle.setWordWrap(True)
        outer.addWidget(subtitle)

        # Let the settings scroll if the window is too small.
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        content = QtWidgets.QWidget()
        inside = QtWidgets.QVBoxLayout(content)
        inside.setContentsMargins(2, 2, 2, 2)
        inside.setSpacing(10)

        # Size and shape options.
        geometry = QtWidgets.QGroupBox("01  TREE GEOMETRY")
        f = QtWidgets.QFormLayout(geometry)
        self.height = self._double(3, 16, 8, " units")
        self.width = self._double(2, 10, 5.5, " units")
        self.branches = self._spin(3, 9, 6)
        self.levels = self._spin(1, 3, 2)
        self.density = self._spin(1, 4, 3)
        f.addRow("Tree height", self.height)
        f.addRow("Canopy width", self.width)
        f.addRow("Main branches", self.branches)
        f.addRow("Branching levels", self.levels)
        f.addRow("Foliage clumps / tip", self.density)
        inside.addWidget(geometry)

        # Pick the tree type, season, and random seed.
        variation = QtWidgets.QGroupBox("02  STYLE + VARIATION")
        f = QtWidgets.QFormLayout(variation)
        self.tree_style = QtWidgets.QComboBox()
        self.tree_style.addItems(["Oak", "Pine", "Willow", "Sakura"])
        self.season = QtWidgets.QComboBox()
        self.season.addItems(["Spring", "Summer", "Autumn", "Winter"])
        self.seed = self._spin(0, 999999, 2026)
        self.random_seed = QtWidgets.QPushButton("New random seed")
        f.addRow("Tree species", self.tree_style)
        f.addRow("Season / colors", self.season)
        f.addRow("Random seed", self.seed)
        f.addRow("", self.random_seed)
        inside.addWidget(variation)

        # Options for making more than one tree.
        grove = QtWidgets.QGroupBox("03  GROVE + OUTPUT")
        f = QtWidgets.QFormLayout(grove)
        self.number = self._spin(1, 6, 1)
        self.spacing = self._double(3, 22, 8, " units")
        self.ground = QtWidgets.QCheckBox("Add a ground disc for each tree")
        self.keep = QtWidgets.QCheckBox("Keep previously generated trees")
        f.addRow("Number of trees", self.number)
        f.addRow("Distance between trees", self.spacing)
        f.addRow("", self.ground)
        f.addRow("", self.keep)
        inside.addWidget(grove)

        self.estimate = QtWidgets.QLabel("")
        self.estimate.setWordWrap(True)
        inside.addWidget(self.estimate)
        inside.addStretch(1)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        self.generate_button = QtWidgets.QPushButton("Generate tree")
        self.generate_button.setObjectName("Generate")
        self.clear_button = QtWidgets.QPushButton("Delete last generated result")
        self.clear_button.setObjectName("Clear")
        outer.addWidget(self.generate_button)
        outer.addWidget(self.clear_button)
        self.status = QtWidgets.QLabel("Ready. Adjust the controls and press Generate.")
        self.status.setWordWrap(True)
        self.status.setObjectName("Status")
        outer.addWidget(self.status)
        qt_note = QtWidgets.QLabel("GUI: {0}  |  Press F in Maya to frame the selection".format(QT_BINDING))
        qt_note.setObjectName("Note")
        outer.addWidget(qt_note)

        # Connect the buttons and inputs to their functions.
        self.generate_button.clicked.connect(self._generate)
        self.clear_button.clicked.connect(self._clear)
        self.random_seed.clicked.connect(self._randomize)
        self.number.valueChanged.connect(self._count_changed)
        self.branches.valueChanged.connect(self._estimate)
        self.levels.valueChanged.connect(self._estimate)
        self.density.valueChanged.connect(self._estimate)

    # Set the colors and overall look of the window.
    def _style(self):
        self.setStyleSheet("""
            QDialog, QWidget { background: #232a25; color: #ecf2e9; }
            QLabel { color: #dbe8d6; font-size: 10pt; }
            QLabel#Heading { color: #acd49c; font-weight: bold; font-size: 16pt; }
            QLabel#Status { background: #314034; color: #d1ebc9;
                            border: 1px solid #557159; border-radius: 5px;
                            padding: 9px; }
            QLabel#Note { color: #a8b8a7; font-size: 8pt; }
            QGroupBox { border: 1px solid #536957; border-radius: 6px;
                        margin-top: 12px; padding: 9px 8px 8px 8px;
                        font-weight: bold; color: #bfe3b2; }
            QGroupBox::title { subcontrol-origin: margin; left: 8px;
                               padding: 0px 5px; }
            QComboBox, QSpinBox, QDoubleSpinBox {
                background: #354238; color: #f3f5f1; border: 1px solid #5f7864;
                border-radius: 4px; padding: 4px; min-height: 22px; }
            QComboBox QAbstractItemView { background: #354238;
                    color: white; selection-background-color: #58765a; }
            QPushButton { background: #435847; color: white;
                border: 1px solid #64846b; border-radius: 5px;
                padding: 8px; min-height: 22px; }
            QPushButton:hover { background: #56755b; }
            QPushButton#Generate { background: #add49e; color: #192419;
                font-weight: bold; }
            QPushButton#Generate:hover { background: #bde9ad; }
            QPushButton#Clear { background: #54433d; color: #e9d1c9; }
            QScrollArea { border: none; }
        """)

    def _count_changed(self, count):
        self.generate_button.setText("Generate tree" if count == 1 else
                                     "Generate grove ({0} trees)".format(count))
        self.spacing.setEnabled(count > 1)
        self._estimate()

    def _estimate(self, *unused):
        # Show an estimate so I know when the tree might be too detailed.
        levels = self.levels.value()
        primary = self.branches.value()
        branches = primary * (2 ** levels - 1)
        leaves = primary * (2 ** (levels - 1)) * self.density.value()
        self.estimate.setText("Approx. {0} branches and {1} foliage clumps per tree. "
                              "Higher values take longer.".format(branches, leaves))

    # Get the values from the window and pass them to the generator.
    def _settings(self):
        return {
            "height": self.height.value(),
            "canopy_width": self.width.value(),
            "branch_count": self.branches.value(),
            "branch_levels": self.levels.value(),
            "foliage_density": self.density.value(),
            "style": str(self.tree_style.currentText()),
            "season": str(self.season.currentText()),
            "seed": self.seed.value(),
            "tree_count": self.number.value(),
            "spacing": self.spacing.value(),
            "create_base": self.ground.isChecked(),
        }

    def _randomize(self):
        self.seed.setValue(random.randint(0, 999999))
        self.status.setText("New seed chosen; press Generate for a new shape.")

    # This runs when Generate tree is clicked.
    def _generate(self):
        values = self._settings()
        self.generate_button.setEnabled(False)
        self.status.setText("Generating geometry in Maya...")
        QtWidgets.QApplication.processEvents()
        chunk_open = False
        try:
            # Keep the generation together as one Undo step in Maya.
            cmds.undoInfo(openChunk=True, chunkName="ARRAS P01 Generate Tree")
            chunk_open = True
            new_root = generate_asset(values)
            # Delete the older tree only after the new one is made.
            if not self.keep.isChecked() and self.last_output and \
                    cmds.objExists(self.last_output):
                cmds.delete(self.last_output)
            self.last_output = new_root
            cmds.select(new_root, replace=True)
            amount = values["tree_count"]
            self.status.setText("Created {0} {1} tree{2} using {3} colors "
                                "(seed {4}).".format(
                                    amount, values["style"],
                                    "" if amount == 1 else "s",
                                    values["season"], values["seed"]))
        except Exception as exc:
            self.status.setText("Generation failed: {0}".format(exc))
            cmds.warning(traceback.format_exc())
        finally:
            if chunk_open:
                try:
                    cmds.undoInfo(closeChunk=True)
                except Exception as close_error:
                    cmds.warning("ARRAS P01: Could not close undo chunk: {0}".format(
                        close_error))
            self.generate_button.setEnabled(True)

    # Delete the last result from this window.
    def _clear(self):
        if self.last_output and cmds.objExists(self.last_output):
            cmds.delete(self.last_output)
            self.status.setText("Deleted the most recent generated result.")
            self.last_output = None
        else:
            self.status.setText("There is no result from this window to delete.")


# --------------------------------------------------------------------------
# Open the tool window
# --------------------------------------------------------------------------

_WINDOW = None


def show_ui(install_shelf=True):
    """Open the window and set up the shelf button if needed."""
    global _WINDOW
    app = QtWidgets.QApplication.instance()
    if app is None:
        raise RuntimeError("Run this tool in Maya's graphical interface, not mayapy.")

    # Close any old copy of the window before opening another one.
    for widget in QtWidgets.QApplication.allWidgets():
        try:
            if widget.objectName() == WINDOW_NAME:
                widget.close()
                widget.deleteLater()
        except RuntimeError:
            pass

    _WINDOW = TreeGeneratorWindow(parent=_maya_window())
    _WINDOW.show()
    _WINDOW.raise_()
    _WINDOW.activateWindow()
    if install_shelf:
        if install_shelf_button():
            _WINDOW.status.setText(
                "Ready. Custom Tree Gen button installed on the selected Maya shelf."
            )
        else:
            _WINDOW.status.setText(
                "Ready to generate. Shelf setup failed; see Maya's Script Editor "
                "for the warning, then rerun install_shelf_button()."
            )
    return _WINDOW


if __name__ == "__main__":
    show_ui()

