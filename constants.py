################################
# Constants used in flow sensor
################################
from scipy.signal import kaiser

# Fourier Transform
FFT_N1 = 1024
FFT_N2 = 16 * 1024
SAMPLING_RATE = 1.0 / 10.0
KAISER_WINDOW_BETA = 14
KAISER_WINDOW = kaiser(FFT_N1, KAISER_WINDOW_BETA)

# Flow detection
FLOW_DETECTION_BLOCK_LEN = 256
FLOW_START_NEG_THRESHOLD = -0.015
FLOW_STOP_POS_THRESHOLD = 0.007

# Signal peak detection constants
MIN_PEAKS = 0.03  # mV
