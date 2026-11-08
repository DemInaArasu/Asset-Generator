# -*- coding: utf-8 -*-
""" 
ARRAS | Procedural Tree & Grove Generator
-----------------------------------------
A Maya tool that creates stylized trees from user-controlled parameters.

Requirements:
    - Autodesk Maya with Python 3
    - PySide2 (included with supported Maya releases)

Launch:
    1. Open Maya's Script Editor and switch to the Python tab.
    2. Run the following, changing the path if needed:

       import runpy
       _tool = runpy.run_path(r"C:/path/to/ArrasBrenda_P01_code.py")
       _tool["show_ui"]()

    3. The tool creates a custom-icon button on the currently selected shelf.
       Use that shelf button for future launches.

All procedural geometry and UI code are contained in this one Python file.
"""

from __future__ import print_function

import math
import os
import random
import runpy
import traceback

try:
    import maya.cmds as cmds
    import maya.mel as mel
    import maya.OpenMayaUI as omui
    from shiboken2 import wrapInstance
    from PySide2 import QtCore, QtGui, QtWidgets
except ImportError as import_error:
    raise RuntimeError(
        "Arras Procedural Tree Generator must be run inside Autodesk Maya "
        "with PySide2 available. Original import error: {0}".format(import_error)
    )


# ---------------------------------------------------------------------------
# Global settings
# ---------------------------------------------------------------------------

WINDOW_OBJECT_NAME = "ArrasProceduralTreeGeneratorWindow"
WINDOW_TITLE = "ARRAS | Procedural Tree Generator"
SHELF_ANNOTATION = "Arras Procedural Tree & Grove Generator"
SHELF_LABEL = "Tree Gen"

# A small style dictionary keeps the geometry-generation code readable.
TREE_STYLES = {
    "Oak": {
        "width": 1.00,
        "upward": 0.62,
        "cluster": 1.00,
        "leaf_y": 0.95,
        "leaf_xz": 1.00,
        "droop": 0.00,
    },
    "Pine": {
        "width": 0.68,
        "upward": 0.80,
        "cluster": 0.78,
        "leaf_y": 1.35,
        "leaf_xz": 0.78,
        "droop": 0.00,
    },
    "Willow": {
        "width": 1.18,
        "upward": 0.38,
        "cluster": 0.88,
        "leaf_y": 1.35,
        "leaf_xz": 0.78,
        "droop": 0.22,
    },
    "Sakura": {
        "width": 1.02,
        "upward": 0.58,
        "cluster": 1.12,
        "leaf_y": 0.92,
        "leaf_xz": 1.06,
        "droop": 0.00,
    },
}

SEASON_PALETTES = {
    "Spring": {
        "leaf": (0.34, 0.66, 0.22),
        "leaf_accent": (0.58, 0.79, 0.31),
        "bark": (0.30, 0.16, 0.075),
        "ground": (0.25, 0.34, 0.17),
    },
    "Summer": {
        "leaf": (0.12, 0.42, 0.12),
        "leaf_accent": (0.27, 0.57, 0.16),
        "bark": (0.25, 0.13, 0.065),
        "ground": (0.20, 0.29, 0.13),
    },
    "Autumn": {
        "leaf": (0.72, 0.24, 0.055),
        "leaf_accent": (0.94, 0.49, 0.075),
        "bark": (0.28, 0.13, 0.06),
        "ground": (0.38, 0.23, 0.11),
    },
    "Winter": {
        "leaf": (0.42, 0.54, 0.61),
        "leaf_accent": (0.72, 0.79, 0.82),
        "bark": (0.24, 0.22, 0.20),
        "ground": (0.35, 0.39, 0.42),
    },
}

SAKURA_PALETTES = {
    "Spring": ((0.91, 0.39, 0.57), (1.00, 0.68, 0.76)),
    "Summer": ((0.83, 0.25, 0.48), (0.98, 0.53, 0.66)),
    "Autumn": ((0.73, 0.25, 0.24), (0.91, 0.49, 0.40)),
    "Winter": ((0.72, 0.64, 0.69), (0.90, 0.82, 0.85)),
}


# ---------------------------------------------------------------------------
# Maya helpers
# ---------------------------------------------------------------------------

def _maya_main_window():
    """Return Maya's main window as a Qt parent, when available."""
    pointer = omui.MQtUtil.mainWindow()
    if not pointer:
        return None
    return wrapInstance(int(pointer), QtWidgets.QWidget)


def _normalize(vector):
    length = math.sqrt(vector[0] ** 2 + vector[1] ** 2 + vector[2] ** 2)
    if length < 0.000001:
        return (0.0, 1.0, 0.0)
    return (vector[0] / length, vector[1] / length, vector[2] / length)


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _multiply(vector, amount):
    return (vector[0] * amount, vector[1] * amount, vector[2] * amount)


def _ensure_lambert_material(name, color):
    """Create or update a simple Maya Lambert material and shading group."""
    shading_group = name + "_SG"

    if not cmds.objExists(name):
        shader = cmds.shadingNode("lambert", asShader=True, name=name)
    else:
        shader = name

    if not cmds.objExists(shading_group):
        shading_group = cmds.sets(
            renderable=True,
            noSurfaceShader=True,
            empty=True,
            name=shading_group,
        )
        cmds.connectAttr(shader + ".outColor", shading_group + ".surfaceShader", force=True)

    cmds.setAttr(shader + ".color", color[0], color[1], color[2], type="double3")
    return shading_group


def _assign_material(objects, shading_group):
    if not objects:
        return
    for obj in objects:
        if obj and cmds.objExists(obj):
            cmds.sets(obj, edit=True, forceElement=shading_group)


def _combine_meshes(meshes, name):
    """Combine a list of mesh transforms to keep the Outliner organized."""
    meshes = [mesh for mesh in meshes if mesh and cmds.objExists(mesh)]
    if not meshes:
        return None
    if len(meshes) == 1:
        return meshes[0]

    combined = cmds.polyUnite(*meshes, mergeUVSets=1)[0]
    combined = cmds.rename(combined, name)
    # Bake the combine node before deleting its source transforms. This keeps
    # the result independent from the temporary branch / leaf objects.
    cmds.delete(combined, constructionHistory=True)
    for mesh in meshes:
        if mesh != combined and cmds.objExists(mesh):
            cmds.delete(mesh)
    return combined


def _make_tapered_trunk(height, radius, name):
    """Create a segmented cylinder and taper its upper rings in object space."""
    trunk = cmds.polyCylinder(
        radius=radius,
        height=height,
        subdivisionsAxis=10,
        subdivisionsHeight=5,
        subdivisionsCaps=1,
        name=name,
    )[0]

    vertex_count = cmds.polyEvaluate(trunk, vertex=True)
    for index in range(vertex_count):
        component = "{0}.vtx[{1}]".format(trunk, index)
        position = cmds.xform(component, query=True, objectSpace=True, translation=True)
        x, y, z = position
        height_ratio = (y + (height * 0.5)) / height
        taper_factor = 1.0 - (0.48 * max(0.0, min(1.0, height_ratio)))
        cmds.xform(
            component,
            objectSpace=True,
            translation=(x * taper_factor, y, z * taper_factor),
        )

    cmds.xform(trunk, worldSpace=True, translation=(0.0, height * 0.5, 0.0))
    return trunk


def _make_branch(start, direction, length, radius, name):
    """Create a tapered cone whose base starts at start and whose tip follows direction."""
    direction = _normalize(direction)
    end = _add(start, _multiply(direction, length))
    midpoint = (
        (start[0] + end[0]) * 0.5,
        (start[1] + end[1]) * 0.5,
        (start[2] + end[2]) * 0.5,
    )

    branch = cmds.polyCone(
        radius=max(0.025, radius),
        height=length,
        subdivisionsAxis=7,
        subdivisionsHeight=1,
        subdivisionsCap=1,
        name=name,
    )[0]
    rotation = cmds.angleBetween(
        euler=True,
        vector1=(0.0, 1.0, 0.0),
        vector2=direction,
    )
    cmds.xform(branch, worldSpace=True, translation=midpoint)
    cmds.xform(branch, worldSpace=True, rotation=rotation)
    return branch, end


def _create_leaf_cluster(position, base_size, style_settings, rng, name):
    """Create one low-poly foliage cluster with small randomized shape changes."""
    cluster = cmds.polySphere(
        radius=1.0,
        subdivisionsX=7,
        subdivisionsY=5,
        name=name,
    )[0]

    random_size = rng.uniform(0.78, 1.22)
    sx = base_size * style_settings["leaf_xz"] * random_size * rng.uniform(0.88, 1.12)
    sy = base_size * style_settings["leaf_y"] * random_size * rng.uniform(0.88, 1.12)
    sz = base_size * style_settings["leaf_xz"] * random_size * rng.uniform(0.88, 1.12)

    cmds.setAttr(cluster + ".scaleX", sx)
    cmds.setAttr(cluster + ".scaleY", sy)
    cmds.setAttr(cluster + ".scaleZ", sz)
    cmds.xform(cluster, worldSpace=True, translation=position)
    cmds.rotate(
        rng.uniform(-35.0, 35.0),
        rng.uniform(0.0, 360.0),
        rng.uniform(-35.0, 35.0),
        cluster,
        worldSpace=True,
    )
    return cluster


# ---------------------------------------------------------------------------
# Procedural tree construction
# ---------------------------------------------------------------------------

def _grow_branch(start, direction, length, radius, depth, max_depth,
                 canopy_width, foliage_density, style_settings, rng,
                 branch_meshes, leaf_primary, leaf_accent, prefix):
    """Recursively split a branch into smaller branches and terminal foliage."""
    branch, end = _make_branch(
        start,
        direction,
        length,
        radius,
        prefix + "_Branch#",
    )
    branch_meshes.append(branch)

    if depth >= max_depth - 1:
        # Several offset clusters make each twig end look fuller than a single ball.
        leaf_size = max(0.13, canopy_width * 0.058) * style_settings["cluster"]
        for leaf_index in range(foliage_density):
            offset_radius = leaf_size * rng.uniform(0.0, 1.15)
            angle = rng.uniform(0.0, math.pi * 2.0)
            vertical_offset = rng.uniform(-0.45, 0.65) * leaf_size
            leaf_position = (
                end[0] + math.cos(angle) * offset_radius,
                end[1] + vertical_offset,
                end[2] + math.sin(angle) * offset_radius,
            )
            cluster = _create_leaf_cluster(
                leaf_position,
                leaf_size,
                style_settings,
                rng,
                prefix + "_Leaf#",
            )
            if rng.random() < 0.28:
                leaf_accent.append(cluster)
            else:
                leaf_primary.append(cluster)
        return

    child_count = rng.choice((2, 2, 3))
    for child_index in range(child_count):
        angle = rng.uniform(0.0, math.pi * 2.0)
        side = (math.cos(angle), 0.0, math.sin(angle))
        spread = rng.uniform(0.34, 0.72)
        upward = rng.uniform(0.16, 0.55)
        child_direction = _normalize((
            direction[0] * 0.58 + side[0] * spread,
            direction[1] * 0.58 + upward - style_settings["droop"],
            direction[2] * 0.58 + side[2] * spread,
        ))
        child_length = length * rng.uniform(0.56, 0.74)
        child_radius = radius * rng.uniform(0.60, 0.73)
        _grow_branch(
            end,
            child_direction,
            child_length,
            child_radius,
            depth + 1,
            max_depth,
            canopy_width,
            foliage_density,
            style_settings,
            rng,
            branch_meshes,
            leaf_primary,
            leaf_accent,
            prefix,
        )


def _build_tree(name, height, canopy_width, branch_count, branch_levels,
                foliage_density, style, season, seed, create_base,
                materials, size_multiplier=1.0):
    """Build one tree and return its top-level transform."""
    rng = random.Random(seed)
    settings = TREE_STYLES[style]
    height *= size_multiplier
    canopy_width *= size_multiplier * settings["width"]
    trunk_radius = max(0.13, height * 0.034)

    trunk = _make_tapered_trunk(height, trunk_radius, name + "_Trunk_GEO")
    branch_meshes = []
    leaf_primary = []
    leaf_accent = []

    # Winter trees keep more visible branching by reducing the number of clusters.
    effective_density = foliage_density
    if season == "Winter":
        effective_density = max(1, int(round(foliage_density * 0.55)))

    # Main branches are distributed around the trunk at staggered heights.
    for branch_index in range(branch_count):
        angle = (math.pi * 2.0 * branch_index / float(branch_count))
        angle += rng.uniform(-0.18, 0.18)
        height_ratio = 0.25 + (0.62 * ((branch_index + 0.5) / float(branch_count)))
        radial_x = math.cos(angle)
        radial_z = math.sin(angle)
        start = (
            radial_x * trunk_radius * 0.32,
            height * height_ratio,
            radial_z * trunk_radius * 0.32,
        )

        upward = settings["upward"] + rng.uniform(-0.10, 0.14)
        direction = _normalize((radial_x, upward, radial_z))
        length_factor = rng.uniform(0.48, 0.68)
        if style == "Pine":
            # Longer lower limbs and shorter upper limbs create a conifer silhouette.
            length_factor *= (1.36 - height_ratio * 0.62)
        elif style == "Willow":
            length_factor *= 1.10

        primary_length = canopy_width * length_factor
        primary_radius = max(0.055, trunk_radius * rng.uniform(0.25, 0.34))
        _grow_branch(
            start,
            direction,
            primary_length,
            primary_radius,
            0,
            branch_levels,
            canopy_width,
            effective_density,
            settings,
            rng,
            branch_meshes,
            leaf_primary,
            leaf_accent,
            name,
        )

    branch_geo = _combine_meshes(branch_meshes, name + "_Branches_GEO")
    primary_geo = _combine_meshes(leaf_primary, name + "_Foliage_GEO")
    accent_geo = _combine_meshes(leaf_accent, name + "_FoliageAccent_GEO")

    geometry = [trunk]
    if branch_geo:
        geometry.append(branch_geo)
    if primary_geo:
        geometry.append(primary_geo)
    if accent_geo:
        geometry.append(accent_geo)

    if create_base:
        base = cmds.polyCylinder(
            radius=canopy_width * 0.78,
            height=0.18,
            subdivisionsAxis=24,
            subdivisionsHeight=1,
            name=name + "_GroundBase_GEO",
        )[0]
        cmds.xform(base, worldSpace=True, translation=(0.0, -0.13, 0.0))
        geometry.append(base)
        _assign_material([base], materials["ground"])

    _assign_material([trunk, branch_geo], materials["bark"])
    _assign_material([primary_geo], materials["leaf"])
    _assign_material([accent_geo], materials["leaf_accent"])

    tree_group = cmds.group(*geometry, name=name + "_GRP")
    return tree_group


def generate_asset(settings):
    """Generate one tree or a small grid-based grove from a settings dictionary."""
    season = settings["season"]
    style = settings["style"]
    palette = dict(SEASON_PALETTES[season])
    if style == "Sakura":
        palette["leaf"], palette["leaf_accent"] = SAKURA_PALETTES[season]

    materials = {
        "bark": _ensure_lambert_material("ARRAS_PTG_Bark_MAT", palette["bark"]),
        "leaf": _ensure_lambert_material("ARRAS_PTG_Foliage_MAT", palette["leaf"]),
        "leaf_accent": _ensure_lambert_material(
            "ARRAS_PTG_FoliageAccent_MAT", palette["leaf_accent"]
        ),
        "ground": _ensure_lambert_material("ARRAS_PTG_Ground_MAT", palette["ground"]),
    }

    tree_count = settings["tree_count"]
    columns = int(math.ceil(math.sqrt(tree_count)))
    rows = int(math.ceil(tree_count / float(columns)))
    created_trees = []
    base_rng = random.Random(settings["seed"])

    for index in range(tree_count):
        row = index // columns
        column = index % columns
        x_position = (column - (columns - 1) * 0.5) * settings["spacing"]
        z_position = (row - (rows - 1) * 0.5) * settings["spacing"]

        tree_seed = settings["seed"] + (index * 1009)
        size_multiplier = 1.0
        if tree_count > 1:
            size_multiplier = base_rng.uniform(0.84, 1.16)

        tree = _build_tree(
            name="ARRAS_PTG_Tree{0:02d}".format(index + 1),
            height=settings["height"],
            canopy_width=settings["canopy_width"],
            branch_count=settings["branch_count"],
            branch_levels=settings["branch_levels"],
            foliage_density=settings["foliage_density"],
            style=style,
            season=season,
            seed=tree_seed,
            create_base=settings["create_base"],
            materials=materials,
            size_multiplier=size_multiplier,
        )
        cmds.move(x_position, 0.0, z_position, tree, relative=True, worldSpace=True)
        created_trees.append(tree)

    output_group = cmds.group(*created_trees, name="ARRAS_PTG_Generated_GRP#")
    return output_group


# ---------------------------------------------------------------------------
# Custom shelf icon and shelf installer
# ---------------------------------------------------------------------------

def _create_shelf_icon():
    """Draw a small tree icon at runtime so no extra image file is required."""
    scripts_directory = cmds.internalVar(userScriptDir=True)
    icon_directory = os.path.join(scripts_directory, "arras_ptg_icons")
    if not os.path.isdir(icon_directory):
        os.makedirs(icon_directory)
    icon_path = os.path.join(icon_directory, "arras_tree_generator.png")

    pixmap = QtGui.QPixmap(64, 64)
    pixmap.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.Antialiasing, True)

    painter.setPen(QtGui.QPen(QtGui.QColor(39, 56, 46), 2))
    painter.setBrush(QtGui.QColor(35, 48, 42))
    painter.drawRoundedRect(QtCore.QRectF(2, 2, 60, 60), 12, 12)

    # Three overlapping canopy shapes and a tapered trunk make the icon readable
    # at the compact size used by Maya shelves.
    painter.setPen(QtCore.Qt.NoPen)
    painter.setBrush(QtGui.QColor(117, 175, 105))
    painter.drawEllipse(QtCore.QRectF(13, 12, 27, 28))
    painter.setBrush(QtGui.QColor(87, 145, 83))
    painter.drawEllipse(QtCore.QRectF(27, 17, 25, 25))
    painter.setBrush(QtGui.QColor(153, 195, 119))
    painter.drawEllipse(QtCore.QRectF(20, 7, 23, 24))

    trunk_pen = QtGui.QPen(QtGui.QColor(190, 139, 91), 6)
    trunk_pen.setCapStyle(QtCore.Qt.RoundCap)
    painter.setPen(trunk_pen)
    painter.drawLine(QtCore.QPointF(32, 35), QtCore.QPointF(32, 54))
    painter.setPen(QtGui.QPen(QtGui.QColor(190, 139, 91), 4, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap))
    painter.drawLine(QtCore.QPointF(32, 43), QtCore.QPointF(22, 34))
    painter.drawLine(QtCore.QPointF(32, 43), QtCore.QPointF(43, 34))
    painter.end()

    pixmap.save(icon_path, "PNG")
    return icon_path


def install_shelf_button():
    """Install/update the custom Tree Gen button on Maya's selected shelf."""
    try:
        shelf_top = mel.eval("$tmp = $gShelfTopLevel")
        selected_shelf = cmds.tabLayout(shelf_top, query=True, selectTab=True)
        if not selected_shelf or not cmds.objExists(selected_shelf):
            cmds.warning("ARRAS PTG: Select a Maya shelf before installing the button.")
            return False

        icon_path = _create_shelf_icon()
        source_path = os.path.abspath(__file__)
        # repr() creates a valid Python string literal on both Windows and macOS.
        source_path_literal = repr(source_path)
        shelf_command = (
            "import runpy\n"
            "_arras_ptg = runpy.run_path({0})\n"
            "_arras_ptg['show_ui'](install_shelf=False)\n"
        ).format(source_path_literal)

        # Remove an older copy of this tool's button instead of making duplicates.
        shelf_children = cmds.shelfLayout(selected_shelf, query=True, childArray=True) or []
        for child in shelf_children:
            try:
                annotation = cmds.shelfButton(child, query=True, annotation=True)
                if annotation == SHELF_ANNOTATION:
                    cmds.deleteUI(child)
            except Exception:
                pass

        cmds.shelfButton(
            parent=selected_shelf,
            label=SHELF_LABEL,
            annotation=SHELF_ANNOTATION,
            image=icon_path,
            sourceType="python",
            command=shelf_command,
        )
        return True
    except Exception as shelf_error:
        cmds.warning("ARRAS PTG: Could not install shelf button: {0}".format(shelf_error))
        return False


# ---------------------------------------------------------------------------
# PySide2 user interface
# ---------------------------------------------------------------------------

class ProceduralTreeGeneratorUI(QtWidgets.QDialog):
    """Main PySide2 window for building procedural trees and groves."""

    def __init__(self, parent=None):
        super(ProceduralTreeGeneratorUI, self).__init__(parent)
        self.setObjectName(WINDOW_OBJECT_NAME)
        self.setWindowTitle(WINDOW_TITLE)
        self.setMinimumWidth(430)
        self.setMaximumWidth(560)
        self.setWindowFlags(self.windowFlags() ^ QtCore.Qt.WindowContextHelpButtonHint)
        self._last_generated_group = None
        self._build_ui()
        self._apply_style()

    def _build_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(18, 16, 18, 16)
        main_layout.setSpacing(12)

        header = QtWidgets.QLabel("PROCEDURAL TREE GENERATOR")
        header.setObjectName("HeaderLabel")
        subtitle = QtWidgets.QLabel(
            "Create stylized trees or a randomized grove directly in your Maya scene."
        )
        subtitle.setObjectName("SubtitleLabel")
        subtitle.setWordWrap(True)
        main_layout.addWidget(header)
        main_layout.addWidget(subtitle)

        shape_group = QtWidgets.QGroupBox("TREE SHAPE")
        shape_layout = QtWidgets.QFormLayout(shape_group)
        shape_layout.setLabelAlignment(QtCore.Qt.AlignLeft)
        shape_layout.setFormAlignment(QtCore.Qt.AlignTop)
        shape_layout.setHorizontalSpacing(18)
        shape_layout.setVerticalSpacing(9)

        self.height_spin = self._double_spin(4.0, 18.0, 8.0, 1)
        self.width_spin = self._double_spin(2.0, 12.0, 5.5, 1)
        self.branches_spin = self._int_spin(3, 12, 7)
        self.levels_spin = self._int_spin(1, 3, 3)
        self.density_spin = self._int_spin(1, 4, 3)

        shape_layout.addRow("Tree height", self._with_suffix(self.height_spin, " units"))
        shape_layout.addRow("Canopy width", self._with_suffix(self.width_spin, " units"))
        shape_layout.addRow("Primary branches", self.branches_spin)
        shape_layout.addRow("Branching levels", self.levels_spin)
        shape_layout.addRow("Foliage density", self.density_spin)
        main_layout.addWidget(shape_group)

        variation_group = QtWidgets.QGroupBox("STYLE & VARIATION")
        variation_layout = QtWidgets.QFormLayout(variation_group)
        variation_layout.setHorizontalSpacing(18)
        variation_layout.setVerticalSpacing(9)

        self.style_combo = QtWidgets.QComboBox()
        self.style_combo.addItems(["Oak", "Pine", "Willow", "Sakura"])
        self.season_combo = QtWidgets.QComboBox()
        self.season_combo.addItems(["Spring", "Summer", "Autumn", "Winter"])
        self.seed_spin = self._int_spin(1, 999999, 2026)
        self.count_spin = self._int_spin(1, 8, 1)
        self.spacing_spin = self._double_spin(4.0, 24.0, 8.0, 1)

        variation_layout.addRow("Tree style", self.style_combo)
        variation_layout.addRow("Season / color palette", self.season_combo)
        variation_layout.addRow("Random seed", self.seed_spin)
        variation_layout.addRow("Trees in grove", self.count_spin)
        variation_layout.addRow("Grove spacing", self._with_suffix(self.spacing_spin, " units"))
        main_layout.addWidget(variation_group)

        options_layout = QtWidgets.QHBoxLayout()
        self.base_checkbox = QtWidgets.QCheckBox("Create ground bases")
        self.base_checkbox.setChecked(False)
        self.keep_checkbox = QtWidgets.QCheckBox("Keep previous output")
        self.keep_checkbox.setChecked(False)
        options_layout.addWidget(self.base_checkbox)
        options_layout.addStretch(1)
        options_layout.addWidget(self.keep_checkbox)
        main_layout.addLayout(options_layout)

        button_row = QtWidgets.QHBoxLayout()
        self.random_button = QtWidgets.QPushButton("Randomize Seed")
        self.random_button.setObjectName("SecondaryButton")
        self.generate_button = QtWidgets.QPushButton("Generate Tree / Grove")
        self.generate_button.setObjectName("PrimaryButton")
        button_row.addWidget(self.random_button)
        button_row.addWidget(self.generate_button, 1)
        main_layout.addLayout(button_row)

        self.clear_button = QtWidgets.QPushButton("Clear Last Generated Output")
        self.clear_button.setObjectName("ClearButton")
        main_layout.addWidget(self.clear_button)

        self.status_label = QtWidgets.QLabel(
            "Ready. Change the parameters and generate a tree."
        )
        self.status_label.setObjectName("StatusLabel")
        self.status_label.setWordWrap(True)
        main_layout.addWidget(self.status_label)

        footer = QtWidgets.QLabel(
            "Tip: Change the seed to create a repeatable new variation."
        )
        footer.setObjectName("FooterLabel")
        main_layout.addWidget(footer)

        self.generate_button.clicked.connect(self._on_generate)
        self.random_button.clicked.connect(self._on_randomize)
        self.clear_button.clicked.connect(self._on_clear)
        self.count_spin.valueChanged.connect(self._on_tree_count_changed)

    @staticmethod
    def _double_spin(minimum, maximum, value, decimals=1):
        widget = QtWidgets.QDoubleSpinBox()
        widget.setRange(minimum, maximum)
        widget.setValue(value)
        widget.setDecimals(decimals)
        widget.setSingleStep(0.5)
        return widget

    @staticmethod
    def _int_spin(minimum, maximum, value):
        widget = QtWidgets.QSpinBox()
        widget.setRange(minimum, maximum)
        widget.setValue(value)
        return widget

    @staticmethod
    def _with_suffix(widget, suffix):
        widget.setSuffix(suffix)
        return widget

    def _apply_style(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #202722;
                color: #edf2eb;
            }
            QLabel {
                color: #e7eee5;
                font-size: 10pt;
            }
            QLabel#HeaderLabel {
                color: #b7dca9;
                font-size: 16pt;
                font-weight: 700;
                letter-spacing: 1px;
            }
            QLabel#SubtitleLabel {
                color: #b5c1b4;
                font-size: 9pt;
                padding-bottom: 3px;
            }
            QLabel#StatusLabel {
                color: #c7dfbd;
                background-color: #29362d;
                border: 1px solid #405443;
                border-radius: 5px;
                padding: 8px;
            }
            QLabel#FooterLabel {
                color: #98a797;
                font-size: 8pt;
            }
            QGroupBox {
                color: #b7dca9;
                font-size: 9pt;
                font-weight: 700;
                border: 1px solid #48584a;
                border-radius: 6px;
                margin-top: 10px;
                padding: 12px 10px 10px 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QComboBox, QSpinBox, QDoubleSpinBox {
                color: #edf2eb;
                background-color: #303b33;
                border: 1px solid #566657;
                border-radius: 4px;
                padding: 5px 7px;
                min-height: 22px;
            }
            QComboBox QAbstractItemView {
                color: #edf2eb;
                background-color: #303b33;
                selection-background-color: #597b59;
            }
            QCheckBox {
                color: #dce6d9;
                spacing: 6px;
            }
            QCheckBox::indicator {
                width: 15px;
                height: 15px;
            }
            QPushButton {
                color: #edf2eb;
                background-color: #3b4b3e;
                border: 1px solid #5b735d;
                border-radius: 5px;
                padding: 8px 10px;
                min-height: 22px;
            }
            QPushButton:hover {
                background-color: #4b614e;
            }
            QPushButton#PrimaryButton {
                color: #172019;
                background-color: #a7ce98;
                border: 1px solid #b9dfaa;
                font-weight: 700;
            }
            QPushButton#PrimaryButton:hover {
                background-color: #bce0ad;
            }
            QPushButton#SecondaryButton {
                background-color: #34443a;
            }
            QPushButton#ClearButton {
                color: #d8c7c2;
                background-color: #443b38;
                border: 1px solid #65504a;
            }
            QPushButton#ClearButton:hover {
                background-color: #594942;
            }
        """)

    def _read_settings(self):
        return {
            "height": self.height_spin.value(),
            "canopy_width": self.width_spin.value(),
            "branch_count": self.branches_spin.value(),
            "branch_levels": self.levels_spin.value(),
            "foliage_density": self.density_spin.value(),
            "style": self.style_combo.currentText(),
            "season": self.season_combo.currentText(),
            "seed": self.seed_spin.value(),
            "tree_count": self.count_spin.value(),
            "spacing": self.spacing_spin.value(),
            "create_base": self.base_checkbox.isChecked(),
        }

    def _on_tree_count_changed(self, count):
        if count == 1:
            self.generate_button.setText("Generate Tree")
        else:
            self.generate_button.setText("Generate Grove ({0} trees)".format(count))

    def _on_randomize(self):
        self.seed_spin.setValue(random.randint(1, 999999))
        self.status_label.setText("New seed selected. Generate to create a different variation.")

    def _on_generate(self):
        settings = self._read_settings()
        old_group = self._last_generated_group
        keep_previous = self.keep_checkbox.isChecked()

        self.generate_button.setEnabled(False)
        self.status_label.setText("Generating geometry... please wait.")
        QtWidgets.QApplication.processEvents()

        try:
            cmds.undoInfo(openChunk=True, chunkName="ARRAS Procedural Tree Generator")
            if old_group and not keep_previous and cmds.objExists(old_group):
                cmds.delete(old_group)

            output_group = generate_asset(settings)
            self._last_generated_group = output_group
            cmds.select(output_group, replace=True)

            if settings["tree_count"] == 1:
                description = "1 {0} tree".format(settings["style"])
            else:
                description = "{0} {1} trees".format(settings["tree_count"], settings["style"])
            self.status_label.setText(
                "Created {0} ({1} palette, seed {2}).".format(
                    description,
                    settings["season"],
                    settings["seed"],
                )
            )
        except Exception as generation_error:
            self.status_label.setText("Generation failed: {0}".format(generation_error))
            cmds.warning(traceback.format_exc())
        finally:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass
            self.generate_button.setEnabled(True)

    def _on_clear(self):
        if self._last_generated_group and cmds.objExists(self._last_generated_group):
            cmds.delete(self._last_generated_group)
            self.status_label.setText("Removed the last generated tree or grove.")
            self._last_generated_group = None
        else:
            self.status_label.setText("There is no generated output from this window to clear.")


# ---------------------------------------------------------------------------
# Public launch function
# ---------------------------------------------------------------------------

_PROCEDURAL_TREE_WINDOW = None


def show_ui(install_shelf=True):
    """Open the generator. The first launch also installs the custom shelf icon."""
    global _PROCEDURAL_TREE_WINDOW

    # Search by object name as well as using the module reference. This also
    # closes an older window when the shelf button reloads this file via runpy.
    for widget in QtWidgets.QApplication.allWidgets():
        try:
            if widget.objectName() == WINDOW_OBJECT_NAME:
                widget.close()
                widget.deleteLater()
        except Exception:
            pass

    _PROCEDURAL_TREE_WINDOW = ProceduralTreeGeneratorUI(parent=_maya_main_window())
    _PROCEDURAL_TREE_WINDOW.show()
    _PROCEDURAL_TREE_WINDOW.raise_()
    _PROCEDURAL_TREE_WINDOW.activateWindow()

    if install_shelf:
        installed = install_shelf_button()
        if installed:
            _PROCEDURAL_TREE_WINDOW.status_label.setText(
                "Ready. Custom Tree Gen shelf button installed on the selected shelf."
            )
    return _PROCEDURAL_TREE_WINDOW


# Running this file directly from Maya's Script Editor will open the UI.
# The shelf button itself calls show_ui(install_shelf=False) to avoid replacing
# the button while it is being clicked.
if __name__ == "__main__":
    show_ui(install_shelf=True)
