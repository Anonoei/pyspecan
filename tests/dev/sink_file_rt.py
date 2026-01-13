import sys
import os

os.system(f"{sys.executable} -m pyspecan -m RT -f data/fm_rds_250k_1Msamples.iq -d cf64 -fs 250k")
