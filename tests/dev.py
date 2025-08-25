import sys
import os

# clear; python3 -m pyspecan -f "data/fm_rds_250k_1Msamples.iq" -fs 250000 -u g -d cf64

os.system(f"{sys.executable} -m pyspecan {' '.join(sys.argv[1:])}")
