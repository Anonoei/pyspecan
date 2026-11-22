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

## From Python

A QPSK signal and an FM carrier: the `signals` marker finds both, the Constellation locks to the one `dsp_freq` names.

```python
--8<-- "examples/dsp.py"
```
