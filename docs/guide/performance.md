# Performance

`python dev/benchmark.py` times every plot alone on a synthetic capture and gives its cost in PSDs (a PSD on the same
blocks is 1.0), its median / p90 / first block in ms, and its share of real time (over 100% it can not keep up with
live samples at that rate on its own).

```
python dev/benchmark.py                            # every plot, the analyzer's defaults (1 MS/s, 1024 FFT, 50 ms blocks)
python dev/benchmark.py --nfft 4096 --sweep 20     # other FFT size / block length
python dev/benchmark.py --plots psd,scope,scalogram
python dev/benchmark.py --markers                  # also what each marker kind adds to a PSD
python dev/benchmark.py --set "Scope trig_mode=roll" --set "PSD points=0"
python dev/benchmark.py --json benchmark.json      # the numbers, to compare runs
```

The cost is what pickers show in a plot's tooltip (light under 2 PSDs, heavy from 10). The benchmark marks a plot
whose measured cost is more than twice off the declared one: update its `ABOUT`.

## Keeping a layout live

- In a layout plots share the FFT frames (plots asking for the same mode, FFT size and window get the same frames,
  computed once a block) and the DSP plots one signal search and lock, so together they cost less than the sum.
- A heavy plot's "Update every" set to N renders every Nth block and skips the ones between, so the rest of the layout
  keeps up.
- `-st` (ms of samples a tick reads) and `--show` (ms between frames) set the update rate: lower both for a faster
  scope, raise `-st` to read more of a fast radio per frame. Blocks hold at most `--max_fft` realtime frames and
  `--block_max` samples.
- A live radio's recording keeps every sample even when the display skips blocks.
