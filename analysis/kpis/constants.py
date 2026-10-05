"""Tunable thresholds and sizes of the KPI analysis (pixel sizes, view selection, particle limits, overlays)."""

TARGET_NM = 50.0  # analysis pixel size; raw images are ~25 nm/px
# View selection: bright-class perimeter per area (1/um, at 100 nm/px) and bright area share.
# Thresholds sit in the gap between the two clusters seen across all reference views.
RIM_CLEAN, RIM_USABLE = 2.3, 2.6
MAX_BRIGHT_SHARE = 0.15
SEPARABILITY_LIMIT = 0.80  # Otsu eta below this is flagged as weak phase separation
MIN_PORE_PX = 4  # 0.01 um^2 at 50 nm/px
MIN_BRIGHT_PX = 20  # 0.05 um^2: smaller bright specks are mostly edge noise
CRACK_ASPECT, CRACK_LENGTH_UM = 4.0, 5.0  # a pore this elongated and this long counts as a crack
PROFILE_BANDS = 16  # horizontal / vertical bands for the homogeneity KPIs
PHASE_COLORS = {0: (42, 120, 214), 2: (235, 104, 52)}  # pore, bright phase; graphite stays grey
