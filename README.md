ARRAS - PROCEDURAL TREE GENERATOR
P01: Procedural Asset Generator

GitHub URL:
<ADD YOUR GITHUB REPOSITORY URL HERE>

Challenge Feature(s):
- Recursive branch generation: branches split into smaller branches across multiple user-selected levels to create different tree structures.
- Procedural foliage: low-poly leaf clusters receive randomized size, rotation, and placement while remaining repeatable with the selected random seed.
- Seasonal materials: Spring, Summer, Autumn, and Winter palettes are created and assigned automatically through Maya Lambert shaders.
- Tree styles: Oak, Pine, Willow, and Sakura settings change the canopy profile, branch direction, foliage shape, and color palette.
- Grove generation: create up to 8 trees in a grid with small randomized size differences and adjustable spacing.
- Custom Maya shelf launcher: the tool draws and saves its own tree icon, then installs a Tree Gen button on the currently selected Maya shelf.
- User-friendly controls: the PySide2 interface includes grouped controls, combo boxes, numeric inputs, checkboxes, status feedback, seed randomization, and output cleanup.

INSTALLATION / LAUNCH:
1. Open Autodesk Maya and open the Script Editor.
2. Select the Python tab.
3. Run the following code, replacing the path with the location of this file:

   import runpy
   _tool = runpy.run_path(r"C:\path\to\ArrasBrenda_P01_code.py")
   _tool["show_ui"]()

4. The UI opens and a custom Tree Gen button is added to the currently selected Maya shelf.
5. Use the Tree Gen shelf button for later launches.

PARAMETERS:
- Tree height
- Canopy width
- Primary branch count
- Branching levels
- Foliage density
- Tree style: Oak, Pine, Willow, or Sakura
- Season / color palette: Spring, Summer, Autumn, or Winter
- Random seed
- Number of trees in the grove
- Grove spacing
- Optional ground bases

NOTES:
- The random seed makes a generated variation repeatable. Change the seed to create a different result.
- The generator uses Maya Lambert materials so the shaders do not require Arnold.
- The source code is contained in one Python file. The shelf icon is generated automatically when the tool is launched.
- Test the script in the Maya version used for the course before submitting. Maya and PySide2 are required; this script will not run as a standalone desktop Python program.