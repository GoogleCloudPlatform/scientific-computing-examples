# ==============================================================================
# Production VMD Scene Definition: 3D Biomolecular Structure & Dynamics
# Configures NewCartoon secondary structure, active-site catalytic dyad,
# semi-transparent QuickSurf solvent envelope, and trajectory animation loop.
# ==============================================================================

# 1. Display Environment Setup
display projection Orthographic
color Display Background black
color Display Depthcue off
axes location off
display depthcue on
display cuemode Exp2
display cueenergy 0.5
stage location off

# 2. Representation Pipeline
# Remove default line representation
mol delrep 0 top

# Rep 0: Protein Backbone in NewCartoon colored by Secondary Structure (STRIDE)
# Alpha-helices (magenta), Beta-sheets (yellow), Turns (cyan), Coils (white)
mol representation NewCartoon 0.300000 12.000000 4.100000 0
mol color Structure
mol selection {protein}
mol material Glossy
mol addrep top

# Rep 1: Catalytic Active Site Dyad (Glu35 & Asp52 in Lysozyme) in Licorice
mol representation Licorice 0.300000 12.000000 12.000000
mol color Name
mol selection {protein and (resid 35 52)}
mol material Opaque
mol addrep top

# Rep 2: Counterions (Cl- ions neutralizing the net +8 charge) in VDW
mol representation VDW 0.550000 12.000000
mol color ResType
mol selection {resname CL CLA NA SOD}
mol material Glossy
mol addrep top

# Rep 3: Semi-Transparent Molecular Solvent Envelope (QuickSurf)
mol representation QuickSurf 1.000000 0.500000 0.500000 1.000000
mol color ColorID 8
mol selection {protein}
mol material Transparent
mol addrep top
mol scaleminmax top 3 0.000000 0.250000

# 3. Camera View & Optimal Angle
mol reinitgui top
rotate x by -15
rotate y by 30
rotate z by 5
scale by 1.15
display update

# 4. Trajectory Playback Loop
animate style Loop
animate speed 0.75
animate forward

puts "================================================================================"
puts "⚡ VMD 3D MOLECULAR SCENE CONFIGURED SUCCESSFULLY"
puts "   - Representation 0: NewCartoon (Secondary Structure)"
puts "   - Representation 1: Licorice (Catalytic Active-Site Dyad: Glu35 / Asp52)"
puts "   - Representation 2: VDW (Neutralizing Counterions)"
puts "   - Representation 3: QuickSurf (Semi-Transparent Molecular Envelope)"
puts "================================================================================"
