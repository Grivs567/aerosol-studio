# Aerosol Studio (v0.1.0 beta)

Interactive aerosol particle size distribution analysis with Python and Bokeh.

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE.txt)

## What It Does

| Area | Capabilities |
| --- | --- |
| Data loading | CSV tables and NetCDF files |
| Visualization | Interactive heatmap, distribution plot, diameter time strip |
| ROI analysis | Freehand and rectangle ROI drawing, ROI save/load sessions |
| Fitting | Peak picker, appearance time, mode diameter, Gaussian LSQ, GMM |
| Overlays | Variable/concentration time-series overlays |
| Reproducibility | ROI/session JSON, dependency tracking |

## Quick Start

On Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
run_aerosol_studio.bat
```

On macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
./run_aerosol_studio.sh
```

If your unzip tool stripped the executable bit from the shell script, run:

```bash
bash run_aerosol_studio.sh
```

After installation, the package also exposes a console entry point:

```bash
aerosol-studio
```

## Package Contents

```text
src/aerosolstudio/        package source
docs/                     user documentation site
sample_data/              small CSV/NetCDF files to try the app with
run_aerosol_studio.bat    Windows launcher
run_aerosol_studio.sh     macOS/Linux launcher
```

## Try It

A small sample dataset is included in `sample_data/`:

* `hyy_dmps_data_2023_may.csv` - load this on the CSV tab.
* `NAIS_20231004.nc` - load this on the NetCDF tab.

Example data: measurements from the SMEAR II station in Hyytiälä, Finland,
provided by the University of Helsinki and licensed under CC BY 4.0. The data
have been subset or processed for demonstration purposes.

## Scientific Use Disclaimer

Aerosol Studio provides an interface for aerosol particle size-distribution
visualization and analysis methods. Users are responsible for evaluating the
suitability of the methods and results for their particular application.

## Methods and Citations

Aerosol Studio is a graphical interface for applying and inspecting aerosol
particle size-distribution analysis methods. The maximum concentration method
and the standard event growth-rate workflow follow Kulmala et al. (2012),
"Measurement of the nucleation of atmospheric aerosol particles", Nature
Protocols, 7, 1651-1667, https://doi.org/10.1038/nprot.2012.091.

The appearance-time method follows the appearance-time approach described for
small clusters by Olenius et al. (2014), "Growth rates of atmospheric molecular
clusters based on appearance times and collision-evaporation fluxes: Growth by
monomers", Journal of Aerosol Science, 78, 55-70,
https://doi.org/10.1016/j.jaerosci.2014.08.008.

The concentration, condensation sink, coagulation sink, particle-mass, and MCC
calculations are provided through the
[`aerosol-functions`](https://github.com/jlpl/aerosol-functions) Python
package where possible; Aerosol Studio focuses on data loading, interaction,
visualization, ROI selection, fitting workflows, and reproducible GUI
sessions.

The maximum cross-correlation growth-rate method follows Lampilahti et al.
(2025), "A cross-correlation-based method for determining size-resolved
particle growth rates", Aerosol Research, 3, 637-647,
https://doi.org/10.5194/ar-3-637-2025.

## Documentation

The full user guide - installation notes, analysis workflows, and
troubleshooting tips - is published at
<https://grivs567.github.io/aerosol-studio/>. The same pages ship in the
`docs/` folder of this repository and can be read offline by opening
`docs/index.html` in a browser.

## Citation

Citation metadata is provided in `CITATION.cff`.

## License

MIT. See `LICENSE.txt`.
