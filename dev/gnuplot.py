import subprocess
import numpy as np

def plot(data):
    d_str = " ".join([f"{d}" for d in data])
    d_str += "\n"

    print(f"{d_str}")
    subprocess.Popen(f"""echo {d_str} | gnuplot -p -e "set terminal dumb; plot '<cat'" """, shell=True)

def main():
    data = [0,3,1,2,4]
    plot(data)

    # cat data.txt | cut -f2 -d' ' | gnuplot -p -e "plot '<cat'"

if __name__ == "__main__":
    main()
