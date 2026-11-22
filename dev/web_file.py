import os
import sys

os.system(f"{sys.executable} -m pyspecan -f data/fm_rds_250k_1Msamples.iq -F cf32 -fs 250k -v web")
