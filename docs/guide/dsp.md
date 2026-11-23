# DSP plots

With [RPPS](https://github.com/Anonoei/RPPS) installed (`pip install pyspecan[dsp]`), pyspecan finds and analyses
signals. Without it everything else works the same, and these plots are not listed (`PYSPECAN_NO_RPPS=1` hides them
even when it is installed).

- The `signals` marker (any spectrum: PSD, spectrograms, persistence, 3D spectrogram) boxes every signal found in the
  block, with its width, SNR and duty cycle in the marker table. The analysed one is green: click a box to analyse
  that signal, drag a box's edges to adjust it.
- "Constellation": the analysed signal's symbols after timing, carrier and gain recovery, over the ideal points, with
  modulation, symbol rate, roll-off, Es/N0, EVM and carrier offset.
- "Eye Diagram": its matched filter output over two symbols, I and Q.
- "Network Analyzer": the link's frequency response across the signal (magnitude, phase, group delay), measured blind
  from the decided symbols, no stimulus needed; "Impulse Response": the same inverse transformed, echoes by delay and
  level.
- "3D Constellation": I and Q against time, the symbols on the matched filter's path; "Vector Diagram": the
  constellation with the path between the symbols; "Constellation Density": the symbols as a heat map.
- "Error Vector": EVM, magnitude and phase error per symbol, with the error summary (peak EVM, MER, IQ offset, gain
  imbalance, quadrature error); "Error Vector Spectrum": where in the band the errors are.
- "Cyclic Spectrum": the spectral correlation against cycle frequency and the spectral coherence image, with the
  symbol rate and carrier symmetry found blind (no lock needed).
- "Symbol Table": the decided symbols.
- "Waveform ID": what kind of signal the selection is, each of RPPS's tests in a table with why it holds: tones,
  OFDM (subcarrier spacing, cyclic prefix and the system they fit), bursts (duty and period), the envelope statistic;
  then the FSK parameters of a constant envelope signal, or the constellation a single carrier's symbols fit by their
  higher order cumulants.
- "Hopping": a frequency hopper over the whole span, its dwells boxed on a short-time spectrum, the visits to each
  channel since the last reset, and the hop set's spacing, the dwell time and the hop rate.
- "Bursts": TDMA bursts, each acquired on the preamble they share and demodulated on its own, boxed on the power
  against time by slot, their symbols as one constellation, and per burst its start, length, carrier offset, EVM,
  frame and slot.
- "Frame Raster": the locked symbols wrapped at the period they repeat with, one frame a row from its unique word,
  colored by the decided symbol (fixed fields show as stripes), with each position's coherence. The lock is followed
  block by block, each block's symbols joining the last's with none dropped or repeated, and the last `symbols` kept,
  so frames longer than a block show; a gap or a likely slip starts them over. `interval` searches less often (seconds
  of signal between searches) for a long record.
- "Signal Profile": every step that processes the selection (or every signal found), as far as RPPS's analysis tells:
  channel, rate and modulation, timing, carrier, then the code and framing or a profile that decodes it, with what is
  left unsolved and its likeliest candidates. It captures `capture` seconds, then profiles them; "run" does it again.
- "Decode": a signal through one of RPPS's profiles (ADS-B, BLE advertising, AX.25, DVB-S/S2, CCSDS, LTE and NR to
  SIB1...): its messages as a table, newest first (time, kind, check, framing fields, payload in hex), and how many
  each block gave. `profile` picks one; left blank, the table lists them and which the sample rate can run. It decodes
  at the center frequency, at `channel`, or with `follow` at the analysed signal; `kinds` keeps only some messages
  (and skips the work the others need); failed checks are listed with `failed`. The readout has the decoder's state
  (measuring, searching, locked, lost) and its load: over 100% it can not keep up. Messages carry the radio's time
  (its clock when it has a date, else the host's), or a SigMF recording's.
- The "Analysis" globals (`--dsp_freq`, `--dsp_bw`, `--dsp_mod`, `--dsp_baud`) pick the signal and, when known, its
  modulation and symbol rate. Blank picks the strongest signal and finds the rest.

```
python3 -m pyspecan -v web -f <file> -F cf32 -fs 1M \
    --plot "PSD marker=signals" --plot constellation --row --plot "eye diagram" --plot "network analyzer"
```

The plots of a layout share one signal search and one lock per block, so several DSP plots cost about as much as one
(see [`pyspecan.plots.dsp`](../api/plots.md#pyspecan.plots.dsp)).

Waveform ID, Hopping, Bursts, Frame Raster and Signal Profile run RPPS's analysis in the background: each render hands
the newest block to it when the last run is done and draws the latest result, so the view stays live while a result
lags by about one run. The readout says when it is still analysing, how long the last run took, and why it failed.

## From Python

A QPSK signal and an FM carrier: the `signals` marker finds both, the Constellation locks to the one `dsp_freq` names.

```python
--8<-- "examples/dsp.py"
```

A TDMA signal: Waveform ID finds the bursts and their period, Bursts demodulates each one. A script waits for the
background analysis (`plot.job.wait()`) before reading a frame.

```python
--8<-- "examples/bursts.py"
```
