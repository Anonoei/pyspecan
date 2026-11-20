import sys
import os

# os.system(f"{sys.executable} -m pyspecan -f data/fm_rds_250k_1Msamples.iq -d cf64 -fs 250k")

os.system(f"{sys.executable} -m pyspecan -f ../RPPS/data/610BE338EA883D94_gqrx_20230303_030038_3690035999_100000000.cs16 -d ci32t -fs 100000000")
