################################
# Constants used in flow sensor
################################

# Fourier Transform
FFT_N1 = 1024
FFT_N2 = 16 * 1024
SAMPLING_RATE = 1.0 / 10.0

# Flow detection
FLOW_DETECTION_BLOCK_LEN = 128
FLOW_START_NEG_THRESHOLD = -0.015
FLOW_STOP_POS_THRESHOLD = 0.007

# Signal peak detection constants
MIN_PEAKS = 0.03
