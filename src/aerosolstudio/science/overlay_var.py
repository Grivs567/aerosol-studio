"""Variable-overlay method registry (concentration/CS/CoagS/etc.) used by the Bokeh overlay controls."""

import aerosol.functions as af

overlay_var_methods = {
    "Select Method": lambda df, dmin, dmax: None,
    "Concentration": lambda df, dmin, dmax: af.calc_conc(df, dmin, dmax),
    "Condensation Sink": lambda df, dmin, dmax: af.calc_cs(df, temp=293.15, pres=101325.0),
    "Coagulation Sink": lambda df, dmin, dmax: af.calc_coags(
        df, dp=[dmin], temp=293.15, pres=101325.0
    ),
    # Do not call af.calc_cs(df, dmin, dmax) here: af.calc_cs's real
    # signature is (df, temp=293.15, pres=101325.0) - it takes no diameter
    # range at all, same as "Condensation Sink" above. Passing dmin/dmax
    # positionally would silently feed the UI's diameter values (metres,
    # ~1e-9 scale) into calc_cs's temp/pres args, computing CS at physically
    # meaningless temperature/pressure with no error. dmin is still used for
    # its real purpose here: the target diameter dp that cs2coags converts
    # CS into a coagulation sink *at*.
    "CoagS from CS": lambda df, dmin, dmax: af.cs2coags(af.calc_cs(df), dp=dmin),
}

# UI metadata only (no runtime effect on the callables above): what the
# generic dmin/dmax overlay boxes actually mean for each method, since it
# varies a lot - "Concentration" genuinely integrates over [dmin, dmax], but
# "Condensation Sink" ignores both, and "Coagulation Sink"/"CoagS from CS"
# only use dmin (as a single target diameter, not a range).
#
# Each entry is (dmin_spec, dmax_spec); each spec is either None (box has no
# effect for this method - the overlay controls disable it instead of always
# showing a misleading "Dmin (nm)"/"Dmax (nm)" pair) or a (label, unit,
# default) triple. unit is "nm" for an actual diameter (converted to metres
# before reaching the callable above, same as always) or "raw" for a non-
# diameter quantity (e.g. PM's density in g/cm^3 - see PM_DIAMETER_LABELS in
# science/pm.py) passed through unconverted. default is a string to pre-fill
# the box with the moment it becomes relevant (only if currently blank - see
# _sync_diameter_controls in app/overlay.py) or None for "leave it blank,
# the user must type something" (every entry here - diameters have no
# sensible default; only PM's density does).
overlay_var_diameter_labels = {
    "Select Method": (None, None),
    "Concentration": (("Dmin (nm)", "nm", None), ("Dmax (nm)", "nm", None)),
    "Condensation Sink": (None, None),
    "Coagulation Sink": (("Target dp (nm)", "nm", None), None),
    "CoagS from CS": (("Target dp (nm)", "nm", None), None),
}
