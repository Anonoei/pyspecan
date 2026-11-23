"""The model: where samples come from, and how many one tick reads

`Model` holds one sink and the parameters that size a block: `nfft`, `sweep_time` (the ms of samples a tick reads),
`overlap` (of the realtime frames), and the limits `min_fft` / `max_fft` (realtime frames a block holds at least / at
most) and `block_max` (samples). `Model.get_block_size` turns them into samples; plots then cut that block into frames
themselves (see `pyspecan.plots.source`), so swept and realtime plots both see every sample.

`model.GetModel(Sink.FILE)` returns a constructor taking the command line options by dest (`path`, `fmt`, `Fs`, `cf`,
`nfft`...), and `model.ModelArgs` registers those options: the model never sees a view's options.

The sinks (`pyspecan.model.sink`) read the samples, through pysdrlib:

| Sink | Reads | Notes |
|---|---|---|
| `SinkFile` (`-s file`) | a file in any complex pysdrlib format | seekable (step back, jump); a SigMF recording brings its format, rate, frequency and start time |
| `SinkLive` (`-s live`) | a radio, attached here or on a pysdrlib server (`-d`) | tunes, sweeps, records SigMF, counts overflows |
| `SinkTcpIq` (`-s tcpiq`) | a TCP IQ stream, as client or listening server | measures the rate samples arrive at |

Every sink sets `contiguous` per block: False when samples were lost in or before it (a radio overflow), which makes
`Source.tick` skip a sequence number so everything stitching blocks together starts over instead of joining samples
that do not follow each other. `block_index` and `block_time` place the block in the stream and in time (a radio's
clock when it holds a date, else the host's; a recording's start plus the offset).
"""
from .. import logger
