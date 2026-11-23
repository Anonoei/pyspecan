# Sources: files, radios and TCP IQ streams

pyspecan reads one block of samples per tick from a sink (`-s`), and draws it in a view (`-v`):

- View (`-v` / `--view`): `web`, `tk` or `cui` (any case). The web view serves http://127.0.0.1:8000; `cui` draws in
  the terminal and needs no plotting library.
- Sink (`-s` / `--sink`): `file`, `live` or `tcpiq`.

```
python3 -m pyspecan --help                                     # the view and sink options; add -v / -s for theirs
python3 -m pyspecan                                            # tkGUI, file: pick one from the window
python3 -m pyspecan -s live -d hackrf                          # tkGUI, live (hackrf)
python3 -m pyspecan -v web -f <file> -F cf32 -fs 250k          # web, file, then open http://127.0.0.1:8000
python3 -m pyspecan -v cui -f <file> -F cf32 -fs 250k          # console, file: type `help`
```

How many samples a tick reads is set by `-st` / `--sweep_time` (ms of samples), within `--min_fft` / `--max_fft`
realtime frames and `--block_max` samples; `-n` is the FFT size and `--show` the ms between frames. See
[`pyspecan.model`](../api/model.md).

The command line logs what happens to stderr: where the web view serves and every browser that connects (with its
address), commands and settings, files opened, a TCP IQ stream's address and its senders. `--log_level` sets how much
(`trace`, `debug`, `info`, `warning`, `error`; `info` by default, `warning` with the console view, `debug` adds the web
server's requests), and `--log_file <path>` also writes everything to a file. From Python, the loggers are under
`pyspecan` like any library's.

## Files

`-f` names the file and `-F` the sample format, by pysdrlib's names (`cf32`: two float32, a GNU Radio `.cfile`;
`ci16`: two int16, a gqrx `.cs16`; `cui8`: an RTL-SDR `.cu8`...). Without `-F` a SigMF recording (`x.sigmf-meta`)
brings its own format, sample rate and center frequency, and other files the format their extension names; a name that
says nothing is read as `cf32`, and pyspecan says so. `-fs` / `-cf` given win over a recording's.

!!! note "pysdrlib 0.5 renamed the formats"
    The number is now the bits of one I or Q value. What was `cf64` is `cf32`, and gqrx's `ci32t` is `ci16`.

Files are seekable: the views step back and forward, jump, and play from any point.

## Radios (`-s live`)

Live uses [pysdrlib](https://github.com/anonoei/pysdrlib) for hardware SDR abstractions.

- `-d` picks the radio by pysdrlib's target: a driver (`uhd`, `hackrf@<serial>`), or on a pysdrlib server
  `radiohost` (it picks), `radiohost/hackrf-0` (one it hosts), `radiohost/hackrf` (open a new one) or
  `radiohost:5556/hackrf@<serial>` (one attached to it); `tcp://host:port/...` works too. With no `-d` it uses the
  first radio attached to this machine.
- `--servers radiohost,other:5556` (or the `PYSPECAN_SERVERS` / pysdrlib's `PYSDRLIB_SERVERS` environment variable)
  names known servers. With no `-d` and no radio attached here, it uses the first server that has one. `--list` and
  the radio picker show their radios too.
- `--list` prints every radio it can use, with the options that pick each one.
- Record: every sample the radio delivers goes to a SigMF recording (cf32, with its rate, frequency, the radio, and
  where samples were lost) while it plays, even when the display skips blocks to keep up. Web and tkGUI: "Record";
  console: `record [path|stop]` (a path ending in a format's extension, `.cs16`, `.cu8`..., records that format
  instead). Recordings without a path go to `--record_dir` (default: here; the web view's `--root` when given),
  named `pyspecan-<UTC time>-<center>Hz.sigmf`. The web view never takes a path from the browser.
- The status line counts samples the radio lost (overflows). A block with samples lost in or before it starts the
  plots' frame streams over, instead of joining samples that do not follow each other.
- A span wider than the sample rate is the Sweep plot's: see [Plots](plots.md#spectrum).

## TCP IQ streams (`-s tcpiq`)

TCPIQ takes `--tcp_host`, `--tcp_port`, `--tcp_listen`, `--tcp_timeout`, and `--tcp_fmt`: what the sender sends
(`cf32` by default, two float32 as GNU Radio sends; `ci16` two int16; `cu8` two uint8, an RTL-SDR's layout...).

The views show where the stream comes from (the address listened on, or the server), who sends and the rate samples
arrive at, flagged when it is more than 10% off `-fs`; the log says when a sender connects, drops or takes over. The stream says
nothing about its rate, so `-fs` stays what it is: "Use measured rate" (console: `fs measured`) takes the measured
one, right only for a sender paced in real time (one replaying a file arrives at network speed).
