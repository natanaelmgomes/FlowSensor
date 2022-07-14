################################
# Constants used in flow sensor
################################
from scipy.signal import kaiser

# Fourier Transform
FFT_N1 = 1024
FFT_N2 = 16 * 1024
SAMPLING_RATE = 1.0 / 10.0
KAISER_WINDOW_BETA = 8
KAISER_WINDOW = kaiser(FFT_N1, KAISER_WINDOW_BETA)

# Flow detection for Alaris GW Cardinal Health
ALGW_FLOW_DETECTION_BLOCK_LEN = 128
ALGW_FLOW_START_NEG_THRESHOLD = -0.015
ALGW_FLOW_STOP_POS_THRESHOLD = 0.007

# Flow detection for B Braun Perfusor Space
BBPS_FLOW_DETECTION_BLOCK_LEN = 128
BBPS_FLOW_START_NEG_THRESHOLD = -0.00075
BBPS_FLOW_STOP_POS_THRESHOLD = 0.000725
# constants to estimate the base voltage before the flow started
BBPS_START = -500  # 50 seconds before the flow started
BBPS_STOP = -100  # 10 seconds before the flow started
# Constants to flow estimation through
BBPS_A = 0.2183
BBPS_B = 0.5583

MIN_DEQUE_SIZE = 500
MAX_DEQUE_SIZE = 600

# Report generation
BASE_VOLTAGE_START = 400
BASE_VOLTAGE_STOP = 100

DROP_VOLTAGE_START = 600
DROP_VOLTAGE_STOP = 100

# Signal peak detection constants
MIN_PEAKS = 0.02  # mV - 20uV
