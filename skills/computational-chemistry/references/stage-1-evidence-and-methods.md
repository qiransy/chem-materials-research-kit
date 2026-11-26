# Stage 1 Evidence and Method Selection

## Contents

1. Select by system and question
2. Assign evidence functions
3. Choose software and modules
4. Relate calculations to experiments
5. Select parameters responsibly
6. Prevent category errors

## Select by system and question

Choose methods from the scientific decision, system scale, periodicity, required observable, available file formats, installed software, and resources. Do not begin with a favorite program and enumerate its features.

Adapt the route by system class:

| System | Typical priorities | Common cautions |
| --- | --- | --- |
| Isolated molecule or molecular complex | conformers/spins, optimization and frequencies, solvation, reaction or orbital analysis | basis-set effects, BSSE where relevant, imaginary frequencies, multireference character |
| Periodic bulk crystal | cell and k-point/cutoff convergence, structure, DOS/PDOS, band structure when scientifically useful | pseudopotential consistency, metallic occupations, correlation corrections, magnetic order |
| Surface, interface, adsorption | slab/supercell and vacuum checks, configurations, adsorption/binding definitions, charge redistribution, local states | finite-size/dipole effects, reference consistency, over-analysis of every configuration |
| Catalytic reaction | stable states, candidate paths, transition states or minimum-energy paths, activation/free energies | endpoint energy differences do not replace barriers; verify path connectivity |
| Classical molecular dynamics | force-field validity, minimization, equilibration, sampling, structural ensembles/free energies | one RMSD curve does not prove convergence or adequate sampling |
| QM/MM, AIMD, or large periodic dynamics | region/model validation, ensemble and timestep, equilibration, representative windows | cost, boundary artifacts, sampling length, statistical uncertainty |

## Assign evidence functions

Use each observable only for what it can defensibly show:

- Optimization, convergence tests, basis/cutoff/k-point tests, pseudopotential checks, wavefunction stability, and MD equilibration establish reliability; they usually are not final mechanism evidence.
- Binding, adsorption, formation, reaction, and free energies address thermodynamic stability or tendency when their reference definitions are explicit.
- Bond lengths, angles, adsorption distances, coordination numbers, distortions, and conformational changes show geometric response and help explain energy differences.
- Charge-density difference shows where accumulation and depletion occur; it does not by itself give an unambiguous transferred-electron count.
- Select one suitable Bader, Hirshfeld, CM5, NPA, or other population method to quantify transfer direction and magnitude. Do not stack schemes without a method-sensitivity question.
- DOS gives the global state distribution; PDOS attributes states to elements, atoms, or orbitals. Treat them as global/local complements.
- Use band structures for systems with meaningful translational periodicity and a band-dispersion question. Prefer DOS/PDOS for molecules, disordered interfaces, or very large supercells unless band unfolding or another explicit analysis is justified.
- Use COHP/COOP, bond order, or orbital-interaction analysis for defined atom-pair bonding/antibonding or interaction-strength questions.
- Use QTAIM for density-topology questions involving critical points, density, Laplacian, and energy-density descriptors.
- Use ELF/LOL for localization or delocalization. Do not equate them directly with charge transfer.
- Use transition states, activation barriers, and minimum-energy paths for kinetic feasibility. Reactant-product energy differences are insufficient.
- Use RMSD, RMSF, radius of gyration, SASA, hydrogen bonds, distance distributions, clustering, and free-energy landscapes as complementary ensemble descriptors. Evaluate equilibration, stationarity, replicas or block behavior as appropriate before claiming adequate sampling.

## Choose software and modules

Verify the installed version and official capability before committing to a route. Confirm that each program can directly produce or export the required data and that cross-program formats are compatible.

- Use Gaussian for molecular optimization, frequency analysis, transition-state searches, single points, continuum solvation, wavefunction stability, natural-bond-orbital workflows when available/licensed, and molecular properties.
- Use ORCA for molecular DFT, frequencies, transition states, excited states, DLPNO high-level calculations, orbital analysis, and solvation models.
- Use Quantum ESPRESSO `pw.x` for periodic relaxation, SCF/NSCF, and band calculations; `dos.x` for total DOS; `projwfc.x` for projected states; and `pp.x` for supported density, potential, and wavefunction post-processing.
- Use CP2K for periodic materials, interfaces, large-scale DFT, AIMD, classical MD, and QM/MM when its representation and modules fit the model.
- Use GROMACS for classical MD, trajectory analysis, structural-ensemble analysis, and supported free-energy workflows.
- Use Multiwfn for supported wavefunction analyses such as population, QTAIM, ELF/LOL, RDG, ESP, bond order, and orbital composition, subject to compatible input data.
- Use LOBSTER for supported projection-based COHP/COOP, bond indicators, and local-orbital bonding analysis from compatible plane-wave calculations.

Treat this list as a capability guide, not a mandate. Prefer available tools that generate the target observable reliably. Do not invent a module or assume file interoperability.

## Relate calculations to experiments

State whether every proposed comparison is qualitative, semi-quantitative, or quantitative, and name major limitations.

| Calculation | Possible experimental relation | Default strength/cautions |
| --- | --- | --- |
| Structural parameters or coordination | XRD, EXAFS, FTIR, Raman | Often qualitative/semi-quantitative; account for temperature, disorder, and model size |
| Charge, orbital occupation, local electronic environment | XPS shifts/valence, work function, Kelvin probe | Usually qualitative/semi-quantitative unless core-level or surface-potential protocols are explicit |
| Adsorption energy, diffusion/desorption barrier | sensing response, selectivity, response/recovery time, operating temperature | Mechanistic trend; kinetics, coverage, entropy, and environment can dominate |
| DOS/PDOS, band gap, states near the Fermi level | conductivity/resistance, optical or electrochemical response | Trend-level unless transport/excitation physics is modeled directly |
| Calculated vibrations | FTIR/Raman shifts | Apply justified scaling and account for phase, temperature, solvent, and environment |
| MD contacts, hydrogen bonds, conformations, free energies | binding stability, activity, structure-activity relationships | Ensemble/statistical evidence; force-field and sampling quality limit inference |

Do not tune the interpretation merely to agree with experiment. Report mismatches and alternate explanations.

## Select parameters responsibly

For functionals, basis sets, pseudopotentials, dispersion, solvation, Hubbard U, cutoff, k-points, cells, vacuum, force fields, timestep, ensemble, thermostat/barostat, and simulation length:

1. identify which decision the parameter can change;
2. cite an appropriate basis: official guidance, primary literature on closely related systems, convergence testing, experimental conditions, or validated prior practice;
3. distinguish fixed project constraints from provisional choices;
4. give a range or candidate set when a unique value is not justified;
5. define the comparison metric and acceptance threshold before testing;
6. keep settings consistent across directly compared systems.

Do not present a familiar numerical value as universal. Do not claim literature support without a verifiable source.

## Prevent category errors

- Do not equate successful job termination with scientific reliability.
- Do not use a thermodynamic observable to claim kinetics.
- Do not use a spatial charge map as an exact transfer count.
- Do not use localization descriptors as direct charge-transfer measures.
- Do not force band structures onto systems lacking meaningful periodic dispersion.
- Do not claim conductivity or catalytic rates directly from DOS or endpoint energies alone.
- Do not describe correlation with experiment as proof of a unique mechanism when alternatives remain.
