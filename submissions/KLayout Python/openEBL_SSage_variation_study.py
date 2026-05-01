'''
Ring resonator variation study for openEBL-2026-05.

Test chip to resolve the dominant source of resonance variation
identified in Sage et al. (in preparation). Key experiments:

1. RADIUS SCALING (5 devices): R = 5, 8, 12, 20, 30 um
   If resonance variance scales as 1/R^2, geometric (circumference)
   variation is implicated. If flat, non-geometric source confirmed.
   6x radius range gives 36x expected variance ratio if geometric.

2. COUPLING GAP VARIATION (3 devices): R = 12 um, g = 50, 150, 200 nm
   Tests etch microloading: different coupling gaps create different
   local pattern density, affecting local etch conditions.

Total: 8 double-bus ring resonators in 605um x 410um.
All with 500 nm waveguide width, oxide cladding (openEBL standard).
Automated measurement via standard SiEPIC optical probe setup.

Author: S. Sage, STELLiQ AI
Date: April 2026
'''

designer_name = 'SSage'
top_cell_name = 'openEBL_%s_variation_study' % designer_name
export_type = 'static'  # flatten PCells for fabrication-ready output

import pya
from pya import *

import SiEPIC
from SiEPIC._globals import Python_Env
from SiEPIC.scripts import zoom_out, export_layout
from SiEPIC.verification import layout_check
import os

if Python_Env == 'Script':
    try:
        import siepic_ebeam_pdk
    except:
        import os, sys
        path_GitHub = os.path.expanduser('~/Documents/GitHub/')
        sys.path.insert(0, os.path.join(path_GitHub, 'SiEPIC_EBeam_PDK/klayout'))
        import siepic_ebeam_pdk

tech_name = 'EBeam'


def variation_study_chip():
    from SiEPIC.extend import to_itype
    from SiEPIC.scripts import connect_cell, connect_pins_with_waveguide
    from SiEPIC.utils.layout import new_layout, floorplan

    # --- Device parameters ---
    pol = 'TE'
    wg_width = 0.5       # um
    wg_bend_radius = 5   # um
    GC_pitch = 127        # um, fiber array spacing

    # Area budget: 605um x 410um. Offset ~40um. Usable X: ~565um.
    # Each double-bus ring takes ~60um (R=12) to ~120um (R=50) in X.
    # GC minimum X-spacing between adjacent devices: 60um.
    #
    # From test run: R=5 to R=30 fills x=0..392 (~392um).
    # Remaining: ~173um for 2-3 more R=12 devices.
    #
    # Decision: drop R=50 (too large, takes ~150um alone).
    # R=5 to R=30 gives 6x range -- sufficient to test 1/R^2 scaling.
    # Use remaining space for gap variation (etch microloading test).

    # Experiment 1: Radius scaling (same gap, g=100nm)
    # 5 devices: R = 5, 8, 12, 20, 30 um
    radii_scaling = [5, 8, 12, 20, 30]
    gaps_scaling = [0.10] * len(radii_scaling)

    # Experiment 2: Coupling gap variation (etch microloading test)
    # 3 devices: R = 12 um, g = 50, 150, 200 nm
    # Different gaps change local pattern density around the ring,
    # affecting etch conditions. If resonance shifts beyond what
    # gap alone predicts, etch microloading is confirmed.
    radii_gap = [12, 12, 12]
    gaps_gap = [0.05, 0.15, 0.20]

    # Combine all devices
    all_radii = radii_scaling + radii_gap
    all_gaps = gaps_scaling + gaps_gap
    all_labels = (
        ['RadiusR%s' % r for r in radii_scaling] +
        ['GapG%s' % int(g * 1000) for g in gaps_gap]
    )

    n_devices = len(all_radii)
    print(f'Designing {n_devices} devices')

    # --- Create layout ---
    cell, ly = new_layout(tech_name, top_cell_name, GUI=True, overwrite=True)
    floorplan(cell, 605e3, 410e3)

    if SiEPIC.__version__ < '0.5.1':
        raise Exception("Errors",
                         "This example requires SiEPIC-Tools version 0.5.1 or greater.")

    LayerSiN = ly.layer(ly.TECHNOLOGY['Si'])
    fpLayerN = cell.layout().layer(ly.TECHNOLOGY['FloorPlan'])
    TextLayerN = cell.layout().layer(ly.TECHNOLOGY['Text'])

    top_cell = cell
    dbu = ly.dbu
    cell = cell.layout().create_cell("VariationStudy")
    t = Trans(Trans.R0, to_itype(40, dbu), to_itype(14, dbu))
    top_cell.insert(CellInstArray(cell.cell_index(), t))

    # Grating coupler
    cell_ebeam_gc = ly.create_cell("GC_%s_1550_8degOxide_BB" % pol, "EBeam")
    gc_length = cell_ebeam_gc.bbox().width() * dbu

    waveguide_type = 'Strip TE 1550 nm, w=500 nm'

    # --- Place devices ---
    x = 0  # running X position

    for idx in range(n_devices):
        r = all_radii[idx]
        g = all_gaps[idx]
        label = all_labels[idx]

        if idx > 0:
            # Standard spacing: previous device right edge + GC length + margin
            # Ensures GC minimum spacing of 60um between adjacent devices
            x = max(
                prev_right * dbu + gc_length + 1,
                prev_gc_x + 60
            )

        # 4 grating couplers (double-bus ring: through + drop)
        instGCs = []
        for gc_i in range(4):
            t = Trans(Trans.R0, to_itype(x, dbu), gc_i * 127 / dbu)
            instGCs.append(cell.insert(
                CellInstArray(cell_ebeam_gc.cell_index(), t)))

        # Measurement label
        t = Trans(Trans.R90, to_itype(x, dbu), to_itype(GC_pitch * 2, dbu))
        text = Text(
            "opt_in_%s_1550_device_%s_%s_r%sg%s" % (
                pol.upper(), designer_name, label, r, int(round(g * 1000))),
            t)
        text.halign = 1
        cell.shapes(TextLayerN).insert(text).text_size = 5 / dbu

        # Ring resonator from two half-ring directional couplers
        cell_dc = ly.create_cell("ebeam_dc_halfring_straight", "EBeam",
                                  {"r": r, "w": wg_width, "g": g, "bustype": 0})
        y_ring = GC_pitch * 3 / 2
        t1 = Trans(Trans.R270,
                    to_itype(x + wg_bend_radius, dbu),
                    to_itype(y_ring, dbu))
        inst_dc1 = cell.insert(CellInstArray(cell_dc.cell_index(), t1))
        inst_dc2 = connect_cell(inst_dc1, 'pin2', cell_dc, 'pin4')

        # Connect waveguides: GCs to ring ports
        connect_pins_with_waveguide(instGCs[1], 'opt1', inst_dc1, 'pin3',
                                     waveguide_type=waveguide_type)
        connect_pins_with_waveguide(instGCs[2], 'opt1', inst_dc1, 'pin1',
                                     waveguide_type=waveguide_type)
        connect_pins_with_waveguide(instGCs[0], 'opt1', inst_dc2, 'pin1',
                                     waveguide_type=waveguide_type)
        connect_pins_with_waveguide(instGCs[3], 'opt1', inst_dc2, 'pin3',
                                     waveguide_type=waveguide_type)

        # Track position for next device
        prev_right = inst_dc2.bbox().right
        prev_gc_x = instGCs[0].trans.disp.x * dbu

        print(f'  Device {idx + 1}/{n_devices}: {label} '
              f'R={r}um g={g*1000:.0f}nm at x={x:.0f}um')

    return ly, cell


ly, cell = variation_study_chip()

# Verify
num_errors = layout_check(cell=cell, verbose=False, GUI=True)
print('Number of errors: %s' % num_errors)

# Export
path = os.path.dirname(os.path.realpath(__file__))
filename, extension = os.path.splitext(os.path.basename(__file__))
if export_type == 'static':
    file_out = export_layout(cell, path, filename,
                              relative_path='..', format='oas', screenshot=True)
else:
    file_out = os.path.join(path, '..', filename + '.oas')
    ly.write(file_out)

# Verification report
file_lyrdb = os.path.join(path, filename + '.lyrdb')
num_errors = layout_check(cell=cell, verbose=False, GUI=True, file_rdb=file_lyrdb)
print('Verification errors: %s' % num_errors)

if Python_Env == 'Script':
    from SiEPIC.utils import klive
    klive.show(file_out, lyrdb_filename=file_lyrdb, technology=tech_name)

print('Layout script done')
