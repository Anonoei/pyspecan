# pyspecan
 A spectrum analyzer library

 - [Documentation](https://anonoei.github.io/pyspecan/)
 - [PyPI](https://pypi.org/project/pyspecan/)


# Examples
tkGUI, SWEPT mode
![tkGUI_Swept](/media/SWEPT_tkGUI.png)
![tkGUI_Swept](/media/SWEPT_tkGUI2.png)

tkGUI, RT mode
![tkGUI_RT](/media/RT_tkGUI.png)
![tkGUI_RT](/media/RT_tkGUI2.png)

# Usage
- View (-v|--view): specifies which frontend to use (tkGUI)
- Mode (-m|--mode): specifies which processing mode to use (swept, rt)
- Sink (-s|--sink): specifies which interface to use (file, live)
  - Live uses [pysdrlib](https://github.com/anonoei/pysdrlib) for hardware SDR abstractions

## Module
- `python3 -m pyspecan --help`
- tkGUI, swept, file: `python3 -m pyspecan`
- tkGUI, RT, file: `python3 -m pyspecan -m RT`
- tkGUI, swept, live (hackrf): `python3 -m pyspecan -s live -d hackrf`

# Install
1. Run `pip install pyspecan`, to install
2. Run `python3 -m pyspecan --help` to view available arguments

# Contributing
1. `git clone https://github.com/Anonoei/pyspecan`
2. `cd pyspecan`
3. `git branch -c feature/<your feature>`
4. `python3 builder.py -b -l` build and install locally

## Build executable
1. `pyinstaller src/pyspecan.spec`
2. `./dist/pyspecan`
