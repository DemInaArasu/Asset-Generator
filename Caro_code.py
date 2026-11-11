
import math  # Math functions help calculate branch directions and angles.
import os  # Lets the tool work with file paths and folders.
import random  # Creates random variations in the trees.
import traceback  # Shows detailed error information if something fails.

try:  # Try importing Maya's built-in tools.
    import maya.cmds as cmds  # Gives Python access to Maya's modeling commands.
    import maya.mel as mel  # Allows Python to run Maya's MEL commands.
    import maya.OpenMayaUI as omui  # Allows the tool to attach its window to Maya.
except ImportError as exc:  # Runs if Maya's modules cannot be imported.
    raise RuntimeError(  # Show an explanation instead of an unclear import error.
        "ARRAS Tree Generator must run inside Autodesk Maya. "
        "Maya import failed: {0}".format(exc)
    )

try:  # Try the version of Qt used by older Maya releases first.
    from PySide2 import QtCore, QtGui, QtWidgets  # Imports widgets, drawing tools, and other GUI components.
    from shiboken2 import wrapInstance  # Lets Qt use a window that Maya already created.
    QT_BINDING = "PySide2"  # Records which GUI library was successfully loaded.
except ImportError:  # If PySide2 is missing, try the newer version.
    try:  # Try the Qt library supplied with newer Maya releases.
        from PySide6 import QtCore, QtGui, QtWidgets  # Imports the newer version of the GUI components.
        from shiboken6 import wrapInstance  # Imports its matching Maya window wrapper.
        QT_BINDING = "PySide6"  # Records that PySide6 is in use.
    except ImportError as exc:  # Handles failure to load either Qt version.
        raise RuntimeError(  # Explain why the interface cannot start.
            "ARRAS Tree Generator needs Maya's PySide2/shiboken2 "
            "(or PySide6/shiboken6 on recent Maya releases). "
            "Import failed: {0}".format(exc)
        )

WINDOW_NAME = "ARRAS_P01_TreeGenerator_Dialog"  # Unique internal name so Maya can find this window later.
SHELF_TOOLTIP = "ARRAS P01 | Procedural Tree & Grove Generator"  # Text shown when hovering over the shelf button.
SHELF_LABEL = "Tree Gen"  # Short label for the custom shelf button.

STYLES = {  # Stores the shape settings for each tree species.
    "Oak":    {"spread": 1.00, "rise": 0.52, "cluster": 1.00, "tall": 0.86, "droop": 0.00},  # Oak spreads outward with a fairly rounded canopy.
    "Pine":   {"spread": 0.66, "rise": 0.86, "cluster": 0.75, "tall": 1.25, "droop": 0.00},  # Pine has a narrower, taller shape.
    "Willow": {"spread": 1.16, "rise": 0.24, "cluster": 0.87, "tall": 1.27, "droop": 0.68},  # Willow branches bend downward more strongly.
    "Sakura": {"spread": 1.06, "rise": 0.52, "cluster": 1.07, "tall": 0.88, "droop": 0.00},  # Sakura has a broad canopy for blossoms.
}

PALETTES = {  # Sets the bark, foliage, and ground colors for each season.
    "Spring": {"bark": (0.31, 0.18, 0.10), "leaf": (0.28, 0.58, 0.20),  # Spring uses light green foliage and brown bark.
               "accent": (0.50, 0.74, 0.31), "ground": (0.30, 0.37, 0.19)},
    "Summer": {"bark": (0.27, 0.14, 0.08), "leaf": (0.12, 0.39, 0.14),  # Summer uses deeper green foliage.
               "accent": (0.27, 0.55, 0.19), "ground": (0.24, 0.32, 0.14)},
    "Autumn": {"bark": (0.29, 0.16, 0.09), "leaf": (0.77, 0.26, 0.06),  # Autumn uses orange and golden leaves.
               "accent": (0.94, 0.51, 0.09), "ground": (0.36, 0.26, 0.14)},
    "Winter": {"bark": (0.27, 0.25, 0.24), "leaf": (0.50, 0.64, 0.71),  # Winter uses pale, cool-colored foliage.
               "accent": (0.77, 0.83, 0.87), "ground": (0.49, 0.55, 0.60)},
}

SAKURA_COLORS = {  # Extra blossom colors used by Sakura trees.
    "Spring": ((0.93, 0.42, 0.61), (1.00, 0.72, 0.80)),  # Spring Sakura blossoms use pink shades.
    "Summer": ((0.81, 0.30, 0.49), (0.99, 0.57, 0.72)),  # Summer Sakura uses deeper pink shades.
    "Autumn": ((0.82, 0.38, 0.32), (0.97, 0.57, 0.44)),  # Autumn Sakura uses warmer coral shades.
    "Winter": ((0.72, 0.65, 0.71), (0.88, 0.80, 0.85)),  # Winter Sakura uses pale lavender shades.
}


def _add(a, b):  # Adds two 3D position or direction vectors together.
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])  # Adds matching x, y, and z coordinates.


def _scale(vec, factor):  # Multiplies every part of a 3D vector by a number.
    return (vec[0] * factor, vec[1] * factor, vec[2] * factor)  # Scales its x, y, and z values equally.


def _unit(vec):  # Turns a direction vector into one with length 1.
    length = math.sqrt(sum(component * component for component in vec))  # Calculates the vector's current length.
    return _scale(vec, 1.0 / length) if length > 1.0e-8 else (0.0, 1.0, 0.0)  # Avoids division by zero when the vector is too small.


def validate_settings(settings):  # Checks that all user choices are within safe limits.
    limits = {  # Defines the minimum and maximum allowed settings.
        "height": (3.0, 16.0),  # Tree height must stay between 3 and 16 units.
        "canopy_width": (2.0, 10.0),  # Controls the allowed canopy width.
        "branch_count": (3, 9),  # Controls how many main branches start at the trunk.
        "branch_levels": (1, 3),  # Limits how many times branches can split.
        "foliage_density": (1, 4),  # Limits the number of foliage clumps per tip.
        "tree_count": (1, 6),  # Limits a grove to six trees.
        "spacing": (3.0, 22.0),  # Sets the allowed distance between trees.
        "seed": (0, 999999),  # Sets the allowed random seed values.
    }
    for key, (minimum, maximum) in limits.items():  # Check each numeric setting against its allowed range.
        value = settings[key]  # Read the user's value for this setting.
        if not minimum <= value <= maximum:  # Reject a value if it falls outside the range.
            raise ValueError("{0} must be between {1} and {2}".format(  # Show which setting needs to be changed.
                key, minimum, maximum))
    if settings["style"] not in STYLES:  # Only allow one of the defined tree styles.
        raise ValueError("Choose a valid tree style.")  # Stop if an unknown tree style was supplied.
    if settings["season"] not in PALETTES:  # Only allow a defined season.
        raise ValueError("Choose a valid season.")  # Stop if the season is not recognized.
    if not isinstance(settings["create_base"], bool):  # The ground-disc option must be True or False.
        raise ValueError("create_base must be True or False.")  # Reject invalid values for the ground option.


def _material(name, rgb):  # Creates one Maya material using the requested color.
    shader = cmds.shadingNode("lambert", asShader=True, name=name)  # Create a simple material called Lambert.
    group = cmds.sets(renderable=True, noSurfaceShader=True,  # Create a shading group to hold the material.
                      empty=True, name=name + "SG")
    cmds.connectAttr(shader + ".outColor", group + ".surfaceShader", force=True)  # Connect the material to its shading group.
    cmds.setAttr(shader + ".color", *rgb, type="double3")  # Set the material's red, green, and blue values.
    return group  # Return the shading group for use on meshes.


def _assign(mesh, shading_group):  # Applies a shading group to an existing 3D object.
    if mesh and cmds.objExists(mesh):  # Check that the object was created successfully.
        cmds.sets(mesh, edit=True, forceElement=shading_group)  # Assign the material to the object.



def _merge(meshes, name):  # Combines several 3D objects into one named mesh.

    existing = [m for m in meshes if cmds.objExists(m)]  # Ignore meshes that no longer exist in the scene.

    if not existing:  # Nothing to combine if the list is empty.
        return None  # Report that no mesh was created.

    if len(existing) == 1:  # A single mesh only needs to be renamed.
        return cmds.rename(existing[0], name)  # Rename and return that one mesh.

    result = cmds.polyUnite(*existing, mergeUVSets=1)[0]  # Merge all existing meshes into one Maya mesh.

    result = cmds.rename(result, name)  # Give the merged mesh its final name.

    cmds.delete(result, constructionHistory=True)  # Remove construction history to keep the mesh independent.

    remaining = [m for m in existing if cmds.objExists(m)]  # Check which original source meshes still remain.

    if remaining:  # Only delete originals if Maya kept any of them.
        cmds.delete(*remaining)  # Delete the remaining source objects without deleting the result.

    return result  # Return the finished combined mesh.



def _make_trunk(height, radius, name):  # Creates the tree's central trunk.
    trunk = cmds.polyCylinder(  # Build a polygon cylinder for the trunk.
        radius=radius, height=height,  # Set the trunk's thickness and height.
        subdivisionsAxis=10, subdivisionsHeight=5,  # Set the polygon detail along and around the trunk.
        subdivisionsCaps=1, constructionHistory=False, name=name
    )[0]
    count = cmds.polyEvaluate(trunk, vertex=True)  # Count all vertices so the trunk can be tapered.
    for index in range(count):  # Visit every vertex of the trunk.
        vertex = "{0}.vtx[{1}]".format(trunk, index)  # Build the name of the current vertex.
        x, y, z = cmds.xform(vertex, query=True, objectSpace=True, translation=True)  # Read its original x, y, and z position.
        t = max(0.0, min(1.0, (y + height * 0.5) / height))  # Find how far up the trunk this vertex sits.
        taper = 1.0 - 0.54 * t  # Make higher vertices narrower than lower ones.
        cmds.xform(vertex, objectSpace=True,  # Update the current vertex position.
                   translation=(x * taper, y, z * taper))
    cmds.xform(trunk, worldSpace=True, translation=(0.0, height * 0.5, 0.0))  # Lift the trunk so its bottom rests at ground height.
    return trunk  # Return the completed trunk object.


def _make_branch(start, direction, length, radius, name):  # Creates one angled branch and finds its endpoint.
    direction = _unit(direction)  # Make sure the growth direction has length 1.
    end = _add(start, _scale(direction, length))  # Calculate where the branch ends.
    midpoint = _scale(_add(start, end), 0.5)  # Find the midpoint where Maya should place the cone.
    branch = cmds.polyCone(  # Create a cone to represent the tapered branch.
        radius=max(radius, 0.026), height=length,  # Set the branch length and minimum thickness.
        subdivisionsAxis=7, subdivisionsHeight=1,  # Use a low polygon count for simpler geometry.
        subdivisionsCap=1, constructionHistory=False, name=name
    )[0]
    rotation = cmds.angleBetween(  # Find the rotation needed to point the cone upward along the branch.
        euler=True, vector1=(0.0, 1.0, 0.0), vector2=direction
    )
    cmds.xform(branch, worldSpace=True, translation=midpoint)  # Move the branch to its calculated midpoint.
    cmds.xform(branch, worldSpace=True, rotation=rotation)  # Rotate the cone so it points in its growth direction.
    return branch, end  # Return both the branch mesh and the tip position.


def _leaf(position, size, style, rng, name):  # Creates a rounded, low-poly clump of foliage.
    sphere = cmds.polySphere(  # Use a sphere as a simple cluster of leaves.
        radius=1.0, subdivisionsX=7, subdivisionsY=5,  # Keep the sphere low-poly instead of smooth and heavy.
        constructionHistory=False, name=name
    )[0]
    scale = rng.uniform(0.78, 1.22) * size  # Randomly vary each clump's overall size.
    cmds.setAttr(sphere + ".scaleX", scale * rng.uniform(0.88, 1.12))  # Randomly adjust its width.
    cmds.setAttr(sphere + ".scaleY", scale * style["tall"])  # Adjust its height to match the tree style.
    cmds.setAttr(sphere + ".scaleZ", scale * rng.uniform(0.88, 1.12))  # Randomly adjust its depth.
    cmds.xform(sphere, worldSpace=True, translation=position)  # Place the foliage clump at the branch tip.
    cmds.rotate(rng.uniform(-25.0, 25.0), rng.uniform(0.0, 360.0),  # Rotate it randomly so clumps do not all look identical.
                rng.uniform(-25.0, 25.0), sphere, worldSpace=True)
    return sphere  # Return the new foliage object.


def _grow(start, direction, length, radius, level, maximum,  # Grows more branches using the same function repeatedly.
          canopy_width, density, style, rng, branches, leaves_a, leaves_b,
          created, prefix):
    segment, tip = _make_branch(start, direction, length, radius,  # Make this branch segment and calculate its new tip.
                                prefix + "_Branch#")
    created.append(segment)  # Track every object for cleanup if an error occurs.
    branches.append(segment)  # Add the segment to the branches that will be merged.

    if level >= maximum - 1:  # Check whether this is the last level of branching.
        leaf_size = max(0.16, canopy_width * 0.063) * style["cluster"]  # Calculate how large the foliage clumps should be.
        for _ in range(density):  # Create the requested number of clumps on this tip.
            theta = rng.uniform(0.0, math.pi * 2.0)  # Choose a random angle around the branch tip.
            r = rng.uniform(0.0, leaf_size * 1.1)  # Choose a random distance from that tip.
            position = (  # Calculate where the leaf clump will appear.
                tip[0] + math.cos(theta) * r,
                tip[1] + rng.uniform(-0.35, 0.60) * leaf_size,
                tip[2] + math.sin(theta) * r,
            )
            cluster = _leaf(position, leaf_size, style, rng, prefix + "_Leaf#")  # Create the foliage clump at that position.
            created.append(cluster)  # Track the clump in case cleanup is needed.
            (leaves_b if rng.random() < 0.30 else leaves_a).append(cluster)  # Put some clumps in the accent-color group.
        return  # Stop splitting when the tip is finished.

    for child in range(2):  # Create two smaller branches from this branch.
        angle = (child * math.pi) + rng.uniform(-0.65, 0.65)  # Give the two child branches different directions.
        side = (math.cos(angle), 0.0, math.sin(angle))  # Find a sideways direction from that angle.
        child_dir = _unit((  # Mix the parent direction with the new sideways direction.
            direction[0] * 0.62 + side[0] * rng.uniform(0.35, 0.60),
            direction[1] * 0.52 + rng.uniform(0.20, 0.44) - style["droop"],  # Lower the vertical direction for drooping Willow branches.
            direction[2] * 0.62 + side[2] * rng.uniform(0.35, 0.60),
        ))
        _grow(  # Call this same function to grow another level of branches.
            tip, child_dir, length * rng.uniform(0.57, 0.73),  # Start at the parent tip and shorten the new branch.
            radius * 0.67, level + 1, maximum,  # Make each next-level branch thinner.
            canopy_width, density, style, rng,
            branches, leaves_a, leaves_b, created, prefix,
        )


def _build_tree(root, index, settings, materials, scale_factor):  # Builds one complete tree inside the output group.
    style = STYLES[settings["style"]]  # Look up the selected species' shape settings.
    rng = random.Random(settings["seed"] + index * 1009)  # Use a predictable random sequence for this tree.
    name = root + "_Tree{0:02d}".format(index + 1)  # Make a unique name for this tree in its grove.
    height = settings["height"] * scale_factor  # Scale the requested tree height.
    width = settings["canopy_width"] * scale_factor * style["spread"]  # Scale the canopy width according to tree style.
    radius = max(0.13, height * 0.037)  # Choose a trunk radius based on height.

    branches, leaves_a, leaves_b = [], [], []  # Prepare separate lists for branches and foliage colors.
    created = []  # Keep track of created objects for error cleanup.
    tree_group = cmds.group(empty=True, name=name + "_GRP", parent=root)  # Create a Maya group to organize this tree.
    try:  # Start protected construction so failures can be cleaned up.
        trunk = _make_trunk(height, radius, name + "_Trunk_GEO")  # Build the tapered trunk geometry.
        created.append(trunk)  # Keep track of the new trunk.
        density = settings["foliage_density"]  # Read the user's foliage density setting.
        if settings["season"] == "Winter":  # Use a little less foliage in winter.
            density = max(1, density - 1)  # Never reduce foliage below one clump per tip.

        count = settings["branch_count"]  # Read how many main branches to make.
        for i in range(count):  # Create each main branch around the trunk.
            phi = (2.0 * math.pi * i / float(count)) + rng.uniform(-0.17, 0.17)  # Spread the branches around a full circle with some variation.
            outward = (math.cos(phi), 0.0, math.sin(phi))  # Turn the angle into an outward direction.
            rise = 0.23 + 0.65 * ((i + 0.5) / float(count))  # Place main branches at different heights on the trunk.
            start = (outward[0] * radius * 0.32,  # Find the position where this branch begins.
                     height * rise, outward[2] * radius * 0.32)
            direction = _unit((outward[0], style["rise"] + rng.uniform(-0.12, 0.12),  # Aim the branch outward and somewhat upward.
                               outward[2]))
            branch_length = width * rng.uniform(0.46, 0.65)  # Randomize its length based on the canopy width.
            if settings["style"] == "Pine":  # Give Pine a wider lower part and narrower upper part.
                branch_length *= 1.58 - rise * 0.82   # Adjust Pine branch lengths by their height.
            elif settings["style"] == "Willow":  # Let Willow branches extend farther.
                branch_length *= 1.12  # Increase Willow branch length slightly.
            _grow(  # Grow the entire smaller branch system from this point.
                start, direction, branch_length,
                max(0.055, radius * rng.uniform(0.26, 0.37)),
                0, settings["branch_levels"], width, density,
                style, rng, branches, leaves_a, leaves_b, created, name,
            )

        branch_geo = _merge(branches, name + "_Branches_GEO")  # Join the branch segments into one mesh.
        if branch_geo:  # Only track the merged branch mesh if it exists.
            created.append(branch_geo)  # Remember it for possible cleanup.
        foliage_geo = _merge(leaves_a, name + "_Foliage_GEO")  # Combine the main-color foliage into one mesh.
        if foliage_geo:  # Only track the merged foliage if it exists.
            created.append(foliage_geo)  # Remember the merged foliage object.
        accents_geo = _merge(leaves_b, name + "_FoliageAccent_GEO")  # Combine accent-color foliage into a second mesh.
        if accents_geo:  # Check whether accent foliage was created.
            created.append(accents_geo)  # Remember the accent-colored mesh.

        for obj, shader in (  # Pair each finished mesh with its intended material.
            (trunk, materials["bark"]),  # Use bark color on the trunk.
            (branch_geo, materials["bark"]),  # Use the same bark color on branches.
            (foliage_geo, materials["leaf"]),  # Use the main foliage color on the leaves.
            (accents_geo, materials["accent"]),  # Use the accent color on some leaf clumps.
        ):
            if obj and cmds.objExists(obj):  # Skip missing or empty meshes.
                _assign(obj, shader)  # Apply the intended material.
                cmds.parent(obj, tree_group)  # Place the mesh inside this tree's Maya group.

        if settings["create_base"]:  # Check whether the ground-disc option was enabled.
            disk = cmds.polyCylinder(  # Make a flat cylinder to serve as a ground base.
                radius=width * 0.73, height=0.16,  # Size its radius to the tree canopy.
                subdivisionsAxis=24, subdivisionsHeight=1,  # Use enough sides to make the disc look round.
                constructionHistory=False, name=name + "_Base_GEO"
            )[0]
            created.append(disk)  # Track the disc in case generation fails.
            cmds.xform(disk, worldSpace=True, translation=(0.0, -0.10, 0.0))  # Put the disc slightly below the ground surface.
            _assign(disk, materials["ground"])  # Apply the ground material.
            cmds.parent(disk, tree_group)  # Put the disc into this tree's group.
        return tree_group  # Return the completed tree group.
    except Exception:  # If any construction step fails, clean up partial objects.
        for obj in created:  # Check every object created during the attempt.
            if cmds.objExists(obj):  # Delete only objects that still exist.
                cmds.delete(obj)  # Remove this unfinished object.
        if cmds.objExists(tree_group):  # Check whether the tree group itself remains.
            cmds.delete(tree_group)  # Remove the unfinished tree group.
        raise  # Pass the original error upward so Maya can report it.


def generate_asset(settings):  # Creates either one tree or a whole grove.
    validate_settings(settings)  # Check the user's settings before building anything.
    root = cmds.group(empty=True, name="ARRAS_PTG_Generated#")  # Create a top-level group for this generated result.
    palette = dict(PALETTES[settings["season"]])  # Copy the selected season's material colors.
    if settings["style"] == "Sakura":  # Give Sakura a special blossom palette.
        palette["leaf"], palette["accent"] = SAKURA_COLORS[settings["season"]]  # Replace Sakura foliage colors with blossom colors.
    shader_nodes = []  # Track newly created materials in case cleanup is needed.
    try:  # Begin protected generation so failures can be handled.
        shaders = {}  # Store the shading groups by material purpose.
        for material_name in ("bark", "leaf", "accent", "ground"):  # Make bark, foliage, accent, and ground materials.
            full_name = root + "_" + material_name.capitalize() + "_MAT"  # Build a distinct material name for this generation.
            shaders[material_name] = _material(full_name, palette[material_name])  # Create that material and store its shading group.
            shader_nodes.append(full_name)  # Remember the material so it can be cleaned up on failure.
            shader_nodes.append(full_name + "SG")  # Remember its shading group as well.

        amount = settings["tree_count"]  # Read how many trees the user requested.
        columns = int(math.ceil(math.sqrt(amount)))  # Choose how many columns to use in the grove.
        rows = int(math.ceil(amount / float(columns)))  # Choose how many rows are required.
        grove_rng = random.Random(settings["seed"] + 31)  # Use the seed to make grove sizes repeatable.
        for i in range(amount):  # Build every requested tree.
            size = 1.0 if amount == 1 else grove_rng.uniform(0.84, 1.16)  # Vary tree sizes a little in a multi-tree grove.
            tree = _build_tree(root, i, settings, shaders, size)  # Create one tree with this size and set of materials.
            column, row = i % columns, i // columns  # Find the tree's row and column in the grove.
            x = (column - (columns - 1) / 2.0) * settings["spacing"]  # Calculate its horizontal x position from spacing.
            z = (row - (rows - 1) / 2.0) * settings["spacing"]  # Calculate its depth z position from spacing.
            cmds.xform(tree, worldSpace=True, translation=(x, 0.0, z))  # Move this tree group to its grove position.
        return root  # Return the completed output group.
    except Exception:  # If a tree fails, remove the unfinished generation.
        if cmds.objExists(root):  # Check whether the output group was created.
            cmds.delete(root)  # Delete the incomplete grove.
        for node in shader_nodes:  # Visit materials made for this failed attempt.
            if cmds.objExists(node):  # Check whether each material still exists.
                cmds.delete(node)  # Remove materials left from the failed generation.
        raise  # Report the failure to the interface.

def _icon_path():  # Creates the custom icon file for Maya's shelf.
    directory = os.path.join(cmds.internalVar(userScriptDir=True),  # Start with Maya's own user scripts directory.
                             "arras_p01_tree_icons")
    if not os.path.isdir(directory):  # Make the icon folder if it does not exist yet.
        os.makedirs(directory)  # Create a directory for the tool's icon.
    path = os.path.join(directory, "arras_tree_shelf.png")  # Choose the full filename of the tree icon.

    image = QtGui.QPixmap(64, 64)  # Create a blank 64-by-64 image.
    image.fill(QtCore.Qt.transparent)  # Make the image background transparent.
    painter = QtGui.QPainter(image)  # Start drawing into that image.
    try:  # Use a try block so drawing can always be finished.
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)  # Turn on smooth edges for the drawing.
        painter.setPen(QtCore.Qt.NoPen)  # Draw shapes without border outlines.
        painter.setBrush(QtGui.QColor(31, 43, 38))  # Choose the dark background color.
        painter.drawRoundedRect(QtCore.QRectF(2, 2, 60, 60), 10, 10)  # Draw the rounded square behind the tree.
        painter.setBrush(QtGui.QColor(145, 101, 66))  # Choose brown for the tree trunk.
        painter.drawRect(QtCore.QRectF(28, 34, 8, 20))  # Draw the trunk rectangle.
        painter.setBrush(QtGui.QColor(83, 157, 89))  # Choose the first green foliage shade.
        painter.drawEllipse(QtCore.QRectF(11, 17, 31, 29))  # Draw the first round part of the canopy.
        painter.setBrush(QtGui.QColor(110, 189, 103))  # Choose a second green foliage shade.
        painter.drawEllipse(QtCore.QRectF(24, 14, 29, 29))  # Draw the next round canopy section.
        painter.setBrush(QtGui.QColor(160, 211, 124))  # Choose the lightest foliage shade.
        painter.drawEllipse(QtCore.QRectF(17, 8, 29, 29))  # Draw the front canopy section.
    finally:  # Always finish the drawing process.
        painter.end()  # Release the drawing tool cleanly.
    if not image.save(path, "PNG"):  # Check whether the PNG image saved successfully.
        raise RuntimeError("Could not write the custom shelf icon to: " + path)  # Explain where saving the icon failed.
    return path  # Return the filename of the finished icon.


def install_shelf_button():  # Installs a clickable launch button on Maya's shelf.
    try:  # Handle shelf errors without crashing the generator.
        shelf_top = mel.eval('global string $gShelfTopLevel; $temp = $gShelfTopLevel;')  # Ask Maya's MEL system for the current shelf container.

        if not shelf_top or not cmds.tabLayout(shelf_top, exists=True):  # Make sure Maya actually has a usable shelf area.
            raise RuntimeError("Maya's shelf UI is not available yet.")  # Explain why the shelf could not be found.
        selected = cmds.tabLayout(shelf_top, query=True, selectTab=True)  # Find the currently selected shelf tab.
        if not selected or not cmds.shelfLayout(selected, exists=True):  # Check that this shelf tab exists.
            raise RuntimeError("Select a visible Maya shelf tab first.")  # Tell the user to select a visible shelf.
        source_file = os.path.abspath(__file__)  # Find the saved Python file's absolute path.
        if not os.path.isfile(source_file):  # Check that the Python file really exists.
            raise RuntimeError("Save this Python file to disk before installing the shelf.")  # Ask for a saved source file if it cannot be found.

        command = (  # Build the Python code that the shelf button will run.
            "import runpy\n"  # Import Python's file-running utility when clicked.
            "_arras_p01 = runpy.run_path({0})\n"  # Load this same generator script from its saved path.
            "_arras_p01['show_ui'](install_shelf=False)\n"  # Open the GUI without installing another shelf button.
        ).format(repr(source_file))
        icon = _icon_path()  # Generate or find the custom shelf icon image.
        children = cmds.shelfLayout(selected, query=True, childArray=True) or []  # List buttons already on the current shelf.
        for child in children:  # Check each existing shelf item.
            try:
                if cmds.shelfButton(child, query=True,  # Look at the item's tooltip to identify our button.
                                    annotation=True) == SHELF_TOOLTIP:
                    cmds.deleteUI(child)  # Delete an older copy to prevent duplicate shelf buttons.
            except Exception:  # Ignore items that are not shelf buttons.
                pass

        cmds.shelfButton(  # Create the button on the chosen shelf.
            parent=selected, label=SHELF_LABEL,  # Put it on the shelf with the Tree Gen label.
            annotation=SHELF_TOOLTIP,  # Give it a useful tooltip.
            image=icon, style="iconOnly",  # Show the custom tree icon instead of a generic Python icon.
            sourceType="python", command=command,  # Tell Maya to execute the button's command as Python.
        )
        return True  # Report that the shelf installation succeeded.
    except Exception as error:  # Handle problems during shelf installation.
        cmds.warning("ARRAS P01 shelf button not installed: {0}".format(error))  # Display a warning instead of closing the whole tool.
        return False  # Report that the shelf installation failed.

def _maya_window():  # Find Maya's main window so our dialog belongs to it.
    pointer = omui.MQtUtil.mainWindow()  # Get the Maya window's internal pointer.
    return wrapInstance(int(pointer), QtWidgets.QWidget) if pointer else None  # Turn that pointer into a usable Qt parent window.


class TreeGeneratorWindow(QtWidgets.QDialog):  # Defines the tree generator's popup window.

    def __init__(self, parent=None):  # Set up the window when it is created.
        super(TreeGeneratorWindow, self).__init__(parent)  # Initialize the standard Qt dialog behavior.
        self.setObjectName(WINDOW_NAME)  # Give Maya a recognizable name for this dialog.
        self.setWindowTitle("ARRAS | Procedural Tree Generator")  # Set the text shown in the window's title bar.
        self.setMinimumWidth(420)  # Keep the controls wide enough to read.
        self.resize(470, 690)  # Choose the starting window size.
        self.setWindowFlags(self.windowFlags() &  # Remove the unused question-mark help button.
                            ~QtCore.Qt.WindowContextHelpButtonHint)
        self.last_output = None  # Remember the most recent tree generated by this window.
        self._setup()  # Create all of the interface controls.
        self._style()  # Apply the custom visual theme.
        self._count_changed(self.number.value())  # Update the tree-count controls to their starting values.

    @staticmethod  # This helper creates whole-number input boxes.
    def _spin(minimum, maximum, initial):  # Accept the smallest, largest, and starting values.
        widget = QtWidgets.QSpinBox()  # Create the whole-number input control.
        widget.setRange(minimum, maximum)  # Set its allowed range.
        widget.setValue(initial)  # Fill in its starting value.
        return widget  # Return the finished control.

    @staticmethod  # This helper creates input boxes that accept decimals.
    def _double(minimum, maximum, initial, suffix=""):  # Include an optional text suffix such as units.
        widget = QtWidgets.QDoubleSpinBox()  # Create the decimal-number input control.
        widget.setRange(minimum, maximum)  # Limit the values a user can enter.
        widget.setValue(initial)  # Set the starting value.
        widget.setDecimals(1)  # Show one decimal place.
        widget.setSingleStep(0.5)  # Move by half a unit when clicking the arrows.
        widget.setSuffix(suffix)  # Show the supplied units beside the number.
        return widget  # Return the finished control.

    def _setup(self):  # Builds all the controls in the generator window.
        outer = QtWidgets.QVBoxLayout(self)  # Create the window's main vertical layout.
        outer.setContentsMargins(12, 12, 12, 12)  # Set the spacing around the edges.
        outer.setSpacing(9)  # Set the spacing between controls.

        title = QtWidgets.QLabel("PROCEDURAL TREE + GROVE")  # Create the window heading.
        title.setObjectName("Heading")  # Give the heading a name for styling.
        outer.addWidget(title)  # Place the heading in the window.
        subtitle = QtWidgets.QLabel("Model stylized trees in Maya using adjustable parameters.")  # Create the short instructions below the heading.
        subtitle.setWordWrap(True)  # Let the instructions wrap onto another line.
        outer.addWidget(subtitle)  # Add those instructions to the window.
        scroll = QtWidgets.QScrollArea()  # Create a scrollable area for all settings.
        scroll.setWidgetResizable(True)  # Make the scroll area adjust to its contents.
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)  # Hide the scroll area's outer frame.
        content = QtWidgets.QWidget()  # Create the inner widget that holds the settings.
        inside = QtWidgets.QVBoxLayout(content)  # Place controls vertically inside the scrolling widget.
        inside.setContentsMargins(2, 2, 2, 2)  # Set inner margins.
        inside.setSpacing(10)  # Set vertical spacing between sections.

        geometry = QtWidgets.QGroupBox("01  TREE GEOMETRY")  # Create the Tree Geometry section heading.
        f = QtWidgets.QFormLayout(geometry)  # Arrange its labels and inputs in rows.
        self.height = self._double(3, 16, 8, " units")  # Add the input for tree height.
        self.width = self._double(2, 10, 5.5, " units")  # Add the input for canopy width.
        self.branches = self._spin(3, 9, 6)  # Add the input for number of main branches.
        self.levels = self._spin(1, 3, 2)  # Add the input for number of branch-splitting levels.
        self.density = self._spin(1, 4, 3)  # Add the input for leaf clumps per branch tip.
        f.addRow("Tree height", self.height)  # Place tree height beside its label.
        f.addRow("Canopy width", self.width)  # Place canopy width beside its label.
        f.addRow("Main branches", self.branches)  # Place main branches beside its label.
        f.addRow("Branching levels", self.levels)  # Place branching levels beside its label.
        f.addRow("Foliage clumps / tip", self.density)  # Place foliage density beside its label.
        inside.addWidget(geometry)  # Add the geometry section to the window.

        variation = QtWidgets.QGroupBox("02  STYLE + VARIATION")  # Create the Style and Variation section.
        f = QtWidgets.QFormLayout(variation)  # Arrange its controls in labeled rows.
        self.tree_style = QtWidgets.QComboBox()  # Create the tree-species dropdown.
        self.tree_style.addItems(["Oak", "Pine", "Willow", "Sakura"])  # Fill it with the four tree styles.
        self.season = QtWidgets.QComboBox()  # Create the season dropdown.
        self.season.addItems(["Spring", "Summer", "Autumn", "Winter"])  # Fill it with the four seasons.
        self.seed = self._spin(0, 999999, 2026)  # Create the random-seed number input.
        self.random_seed = QtWidgets.QPushButton("New random seed")  # Add a button that chooses a new random seed.
        f.addRow("Tree species", self.tree_style)  # Place the tree-style dropdown into the form.
        f.addRow("Season / colors", self.season)  # Place the season dropdown into the form.
        f.addRow("Random seed", self.seed)  # Place the seed input into the form.
        f.addRow("", self.random_seed)  # Place the randomize button into the form.
        inside.addWidget(variation)  # Add this whole section to the window.

        grove = QtWidgets.QGroupBox("03  GROVE + OUTPUT")  # Create the Grove and Output section.
        f = QtWidgets.QFormLayout(grove)  # Arrange the grove options in labeled rows.
        self.number = self._spin(1, 6, 1)  # Choose how many trees to create.
        self.spacing = self._double(3, 22, 8, " units")  # Choose the distance between grove trees.
        self.ground = QtWidgets.QCheckBox("Add a ground disc for each tree")  # Add an option for a ground disc under each tree.
        self.keep = QtWidgets.QCheckBox("Keep previously generated trees")  # Add an option to keep earlier generated trees.
        f.addRow("Number of trees", self.number)  # Place the number-of-trees input in its row.
        f.addRow("Distance between trees", self.spacing)  # Place the spacing input in its row.
        f.addRow("", self.ground)  # Add the ground-disc checkbox to the layout.
        f.addRow("", self.keep)  # Add the keep-previous checkbox to the layout.
        inside.addWidget(grove)  # Place the grove section into the window.

        self.estimate = QtWidgets.QLabel("")  # Create a label for the estimated geometry count.
        self.estimate.setWordWrap(True)  # Allow long estimates to wrap onto another line.
        inside.addWidget(self.estimate)  # Add the estimate label to the form.
        inside.addStretch(1)  # Leave stretchable empty space at the bottom.
        scroll.setWidget(content)  # Put the settings widget into the scroll area.
        outer.addWidget(scroll, 1)  # Add the scroll area to the overall window.

        self.generate_button = QtWidgets.QPushButton("Generate tree")  # Create the button that makes the tree or grove.
        self.generate_button.setObjectName("Generate")  # Give it a styling name so it can be green.
        self.clear_button = QtWidgets.QPushButton("Delete last generated result")  # Create the button that removes the last result.
        self.clear_button.setObjectName("Clear")  # Give the delete button its styling name.
        outer.addWidget(self.generate_button)  # Place the Generate button below the controls.
        outer.addWidget(self.clear_button)  # Place the Delete button below Generate.
        self.status = QtWidgets.QLabel("Ready. Adjust the controls and press Generate.")  # Create a status label showing messages to the user.
        self.status.setWordWrap(True)  # Allow the status text to wrap if it is long.
        self.status.setObjectName("Status")  # Give the status label a styling name.
        outer.addWidget(self.status)  # Place the status label in the window.
        qt_note = QtWidgets.QLabel("GUI: {0}  |  Press F in Maya to frame the selection".format(QT_BINDING))  # Display which PySide version is active.
        qt_note.setObjectName("Note")  # Set a special styling name for the note.
        outer.addWidget(qt_note)  # Place that note at the bottom.

        self.generate_button.clicked.connect(self._generate)  # Connect a Generate click to the generation function.
        self.clear_button.clicked.connect(self._clear)  # Connect a Delete click to the cleanup function.
        self.random_seed.clicked.connect(self._randomize)  # Connect the random-seed button to its function.
        self.number.valueChanged.connect(self._count_changed)  # Update spacing and button text when tree count changes.
        self.branches.valueChanged.connect(self._estimate)  # Update the estimates when the branch count changes.
        self.levels.valueChanged.connect(self._estimate)  # Update the estimates when the branching levels change.
        self.density.valueChanged.connect(self._estimate)  # Update the estimates when foliage density changes.

    def _style(self):  # Applies colors, borders, and text styling to the GUI.
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
        """)  # Finish the stylesheet containing the GUI's visual rules.

    def _count_changed(self, count):  # Updates controls when the user changes tree count.
        self.generate_button.setText("Generate tree" if count == 1 else  # Show the correct Generate button text for one or more trees.
                                     "Generate grove ({0} trees)".format(count))
        self.spacing.setEnabled(count > 1)  # Disable spacing when generating only one tree.
        self._estimate()  # Recalculate the estimated mesh counts.

    def _estimate(self, *unused):  # Estimates how much geometry generation will create.
        levels = self.levels.value()  # Read the number of branch-splitting levels.
        primary = self.branches.value()  # Read how many main branches will be grown.
        branches = primary * (2 ** levels - 1)  # Calculate the approximate total number of branches.
        leaves = primary * (2 ** (levels - 1)) * self.density.value()  # Calculate the approximate number of foliage clumps.
        self.estimate.setText("Approx. {0} branches and {1} foliage clumps per tree. "  # Show the estimates so users can avoid heavy settings.
                              "Higher values take longer.".format(branches, leaves))

    def _settings(self):  # Collects all GUI values into one dictionary.
        return {
            "height": self.height.value(),  # Read the height input.
            "canopy_width": self.width.value(),  # Read the canopy width input.
            "branch_count": self.branches.value(),  # Read the main branch count.
            "branch_levels": self.levels.value(),  # Read how many branch levels to make.
            "foliage_density": self.density.value(),  # Read the foliage-density input.
            "style": str(self.tree_style.currentText()),  # Read the chosen species from its dropdown.
            "season": str(self.season.currentText()),  # Read the chosen season from its dropdown.
            "seed": self.seed.value(),  # Read the current random seed.
            "tree_count": self.number.value(),  # Read how many trees to generate.
            "spacing": self.spacing.value(),  # Read the spacing between trees.
            "create_base": self.ground.isChecked(),  # Read whether ground discs are enabled.
        }

    def _randomize(self):  # Chooses a new seed to change the random variations.
        self.seed.setValue(random.randint(0, 999999))  # Generate a random whole-number seed.
        self.status.setText("New seed chosen; press Generate for a new shape.")  # Tell the user to press Generate to apply the new seed.

    def _generate(self):  # Runs when the user clicks the Generate button.
        values = self._settings()  # Read the current settings from the GUI.
        self.generate_button.setEnabled(False)  # Disable Generate to prevent repeated clicks while working.
        self.status.setText("Generating geometry in Maya...")  # Let the user know that geometry is being made.
        QtWidgets.QApplication.processEvents()  # Refresh the window so the status message appears.
        chunk_open = False  # Remember whether Maya's undo group has been opened.
        try:  # Start a protected generation attempt.
            cmds.undoInfo(openChunk=True, chunkName="ARRAS P01 Generate Tree")  # Group the whole generation into one Undo action.
            chunk_open = True  # Record that the undo group was opened.
            new_root = generate_asset(values)  # Generate the new tree or grove.
            if not self.keep.isChecked() and self.last_output and \
                    cmds.objExists(self.last_output):
                cmds.delete(self.last_output)  # Delete the last output after the new one succeeded.
            self.last_output = new_root  # Remember the new result for Delete Last.
            cmds.select(new_root, replace=True)  # Select the completed result inside Maya.
            amount = values["tree_count"]  # Read the number of trees just generated.
            self.status.setText("Created {0} {1} tree{2} using {3} colors "  # Show a successful creation message in the GUI.
                                "(seed {4}).".format(
                                    amount, values["style"],
                                    "" if amount == 1 else "s",
                                    values["season"], values["seed"]))
        except Exception as exc:  # Catch any errors during generation.
            self.status.setText("Generation failed: {0}".format(exc))  # Show a short error message in the status label.
            cmds.warning(traceback.format_exc())  # Print the full error details to Maya's Script Editor.
        finally:  # Always run this cleanup code after generation.
            if chunk_open:  # Check whether the undo group needs closing.
                try:  # Try to finish the grouped undo action.
                    cmds.undoInfo(closeChunk=True)  # Close the undo group so Maya's Undo works normally.
                except Exception as close_error:  # Catch problems while closing the undo group.
                    cmds.warning("ARRAS P01: Could not close undo chunk: {0}".format(  # Show a warning if closing the undo group fails.
                        close_error))
            self.generate_button.setEnabled(True)  # Enable Generate again whether the attempt succeeded or failed.

    def _clear(self):  # Runs when the user clicks Delete Last Result.
        if self.last_output and cmds.objExists(self.last_output):  # Check whether the last-generated output still exists.
            cmds.delete(self.last_output)  # Delete that group of trees from the Maya scene.
            self.status.setText("Deleted the most recent generated result.")  # Show a confirmation message.
            self.last_output = None  # Clear the saved reference to the deleted group.
        else:  # Handle the case where there is nothing left to remove.
            self.status.setText("There is no result from this window to delete.")  # Explain that there is no recent result to delete.
_WINDOW = None  # Remember the currently open generator window.


def show_ui(install_shelf=True):  # Opens the GUI and optionally creates the shelf button.
    global _WINDOW  # Use the shared window variable from this script.
    app = QtWidgets.QApplication.instance()  # Look for Maya's existing Qt application.
    if app is None:  # Make sure the tool is running inside Maya's graphical program.
        raise RuntimeError("Run this tool in Maya's graphical interface, not mayapy.")  # Explain why the standalone Python environment cannot show the GUI.

    for widget in QtWidgets.QApplication.allWidgets():  # Find other open windows belonging to this generator.
        try:
            if widget.objectName() == WINDOW_NAME:  # Recognize them using the special window name.
                widget.close()  # Close an earlier copy to avoid duplicate windows.
                widget.deleteLater()  # Schedule that older window for safe removal.
        except RuntimeError:  # Ignore an old window that Maya already deleted.
            pass

    _WINDOW = TreeGeneratorWindow(parent=_maya_window())  # Create the window and attach it to Maya.
    _WINDOW.show()  # Make the new window visible.
    _WINDOW.raise_()  # Bring the window in front of other windows.
    _WINDOW.activateWindow()  # Give the window keyboard and mouse focus.
    if install_shelf:  # Check whether shelf installation was requested.
        if install_shelf_button():  # Try to add the custom Tree Gen shelf button.
            _WINDOW.status.setText(  # Display a success message for the shelf setup.
                "Ready. Custom Tree Gen button installed on the selected Maya shelf."
            )
        else:  # Handle the case where shelf setup failed.
            _WINDOW.status.setText(  # Show a message directing the user to the warning.
                "Ready to generate. Shelf setup failed; see Maya's Script Editor "
                "for the warning, then rerun install_shelf_button()."
            )
    return _WINDOW  # Return the open GUI window to Python callers.

if __name__ == "__main__":  # Run this only when the file is launched directly.
    show_ui()  # Open the user interface.
