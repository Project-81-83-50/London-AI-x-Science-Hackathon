"""Constants shared by the GET4 modules: class names, the 95 % z value and FFT size limits."""

PHASES = {0: "pore", 1: "graphite", 2: "bright phase"}
INTENSITY_CLASSES = {0: "low-intensity class", 1: "mid-intensity class", 2: "high-intensity class"}
Z95 = 1.959964
IMAGE_SUFFIXES = {".tif", ".tiff", ".png"}
FULL_FFT_MAX_PX = 40_000_000  # above this, accumulate the correlation over tiles
FFT_TILE = 4096
