"""The KPI catalogue: groups, display names, units, display scales and definitions of every KPI, and the
derived lists (cross-detector KPIs, headline KPIs, signed KPIs) used by the report and the classifier.

KPI_GROUPS entries are (group id, title, description, [(kpi id, name, unit, display scale, definition), ...]);
KPI_INDEX maps a KPI id to (group id, name, unit, display scale, definition).
"""

from .constants import CRACK_ASPECT, CRACK_LENGTH_UM, PROFILE_BANDS

PERCENT, MICRON, RATIO, DENSITY, PER_UM = "%", "µm", "ratio", "per 100 µm²", "µm / µm²"
KPI_GROUPS = [
    (
        "composition",
        "Phase composition",
        "Area fractions of the segmented phases. In a "
        "cross-section, area fraction estimates volume fraction (Delesse principle).",
        [
            ("porosity", "Porosity", PERCENT, 100, "Area share of the black pore class."),
            ("graphite_fraction", "Graphite fraction", PERCENT, 100, "Area share of the dark-grey flake class."),
            (
                "bright_fraction",
                "Bright-phase fraction",
                PERCENT,
                100,
                "Area share of the bright, higher-Z class (likely the Si-containing additive).",
            ),
            (
                "bright_to_solid",
                "Bright phase share of solids",
                PERCENT,
                100,
                "Bright phase / (graphite + bright phase): the additive loading of the active material.",
            ),
        ],
    ),
    (
        "pores",
        "Pore network",
        "Connected regions of the pore class.",
        [
            ("pore_density", "Pore count density", DENSITY, 1, "Separate pore regions per 100 µm²."),
            (
                "pore_ecd_d50",
                "Median pore size",
                MICRON,
                1,
                "Median equivalent circle diameter (ECD) of pore regions, by count.",
            ),
            (
                "pore_ecd_area_d50",
                "Area-weighted pore size",
                MICRON,
                1,
                "ECD at which half of the pore area lies in larger pores.",
            ),
            (
                "largest_pore_share",
                "Largest pore network share",
                PERCENT,
                100,
                "Share of pore area in the single largest connected pore region: a 2D connectivity proxy.",
            ),
            (
                "crack_share",
                "Crack-like pore share",
                PERCENT,
                100,
                f"Share of pore area in elongated pores (aspect ≥ {CRACK_ASPECT:g}, length ≥ {CRACK_LENGTH_UM:g} µm).",
            ),
        ],
    ),
    (
        "bright",
        "Bright-phase particles",
        "Connected regions of the bright class.",
        [
            ("bright_density", "Bright particle density", DENSITY, 1, "Bright particles per 100 µm²."),
            (
                "bright_d50",
                "Bright particle D50",
                MICRON,
                1,
                "Median ECD by count. Dominated by the many small particles near the 0.25 µm detection limit.",
            ),
            (
                "bright_area_d50",
                "Area-weighted bright particle size",
                MICRON,
                1,
                "ECD at which half of the bright-phase area lies in larger particles.",
            ),
            ("bright_d90", "Bright particle D90", MICRON, 1, "90th percentile ECD by count."),
            ("bright_aspect", "Bright particle aspect ratio", RATIO, 1, "Median major / minor axis length."),
            (
                "bright_clustering",
                "Bright particle dispersion",
                RATIO,
                1,
                "Clark–Evans nearest-neighbour ratio: below 1 clustered, about 1 random, above 1 evenly spread.",
            ),
        ],
    ),
    (
        "graphite",
        "Graphite texture",
        "Mean intercept (chord) lengths through the graphite class.",
        [
            (
                "graphite_chord_x",
                "Graphite chord length, horizontal",
                MICRON,
                1,
                "Mean length of uninterrupted graphite runs along image rows.",
            ),
            (
                "graphite_chord_y",
                "Graphite chord length, vertical",
                MICRON,
                1,
                "Mean length of uninterrupted graphite runs along image columns.",
            ),
            (
                "graphite_orientation",
                "Flake orientation index",
                RATIO,
                1,
                "Horizontal / vertical chord length: above 1 means flakes lie along the image width.",
            ),
        ],
    ),
    (
        "interfaces",
        "Interfaces and transport",
        "Boundary densities and model transport estimates.",
        [
            (
                "pore_interface_density",
                "Pore–solid interface density",
                PER_UM,
                1,
                "Pore boundary length per unit area (stereological estimate of specific surface).",
            ),
            (
                "bright_interface_density",
                "Bright-phase interface density",
                PER_UM,
                1,
                "Bright-phase boundary length per unit area.",
            ),
            (
                "bruggeman_tortuosity",
                "Tortuosity (Bruggeman estimate)",
                RATIO,
                1,
                "Model value porosity^-0.5. Assumes spherical particles, so treat as a lower bound.",
            ),
            (
                "bruggeman_transport",
                "Effective transport factor (Bruggeman)",
                PERCENT,
                100,
                "Model value porosity^1.5: electrolyte conductivity as a share of bulk.",
            ),
        ],
    ),
    (
        "homogeneity",
        "Homogeneity within each image",
        f"How evenly the pore class is spread within each field of view, using {PROFILE_BANDS} bands.",
        [
            (
                "porosity_gradient",
                "Top-to-bottom porosity change",
                "pp",
                100,
                "Porosity of the bottom third minus the top third of the image, in percentage points.",
            ),
            (
                "porosity_band_cv",
                "Vertical porosity variation",
                PERCENT,
                100,
                "Coefficient of variation of porosity across horizontal bands.",
            ),
            (
                "porosity_inplane_cv",
                "Horizontal porosity variation",
                PERCENT,
                100,
                "Coefficient of variation of porosity across vertical bands.",
            ),
        ],
    ),
    (
        "detectors",
        "Cross-detector comparison",
        "The field's ETD and InLens views are segmented like the BSE "
        "view, aligned to it, and compared pixel by pixel. ETD keeps pores black; InLens fills shallow pores in and "
        "lights up particle rims. These depend on detector settings as well as the material.",
        [
            (
                "pore_agreement_etd",
                "BSE–ETD pore agreement",
                PERCENT,
                100,
                "Dice overlap of the BSE pore class and the ETD dark class.",
            ),
            (
                "porosity_confirmed_etd",
                "Porosity confirmed by ETD",
                PERCENT,
                100,
                "Area share that is pore in both the BSE and the ETD view.",
            ),
            (
                "porosity_bse_minus_etd",
                "BSE minus ETD porosity",
                "pp",
                100,
                "BSE pore share minus ETD dark share, in percentage points.",
            ),
            (
                "etd_dark_solid",
                "ETD-dark solid",
                PERCENT,
                100,
                "Area share dark in ETD but solid in BSE: sub-surface pores, shadowed edges or carbon-binder.",
            ),
            (
                "bright_lit_inlens",
                "Bright phase lit in InLens",
                PERCENT,
                100,
                "Share of BSE bright-phase pixels that are also bright in InLens.",
            ),
            (
                "pores_filled_inlens",
                "Pores filled in by InLens",
                PERCENT,
                100,
                "Share of BSE pore pixels that are not dark in InLens: shallow pores or pore walls.",
            ),
            (
                "inlens_lit_outside_bright",
                "InLens-lit outside the bright phase",
                PERCENT,
                100,
                "Area share bright in InLens but not in the BSE bright class: lit rims and edges.",
            ),
        ],
    ),
]
CROSS_DETECTOR_KPIS = [k[0] for g in KPI_GROUPS if g[0] == "detectors" for k in g[3]]
HEADLINE = [
    "porosity",
    "graphite_fraction",
    "bright_fraction",
    "bright_area_d50",
    "pore_ecd_area_d50",
    "graphite_orientation",
]
KPI_INDEX = {k[0]: (g[0], *k[1:]) for g in KPI_GROUPS for k in g[3]}


# KPIs that can be negative: a CV is meaningless for them, so they are judged by their CI instead.
SIGNED_KPIS = {"porosity_gradient", "porosity_bse_minus_etd"}
