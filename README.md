# pyspecan
 A spectrum analyzer library

 - [Documentation](https://anonoei.github.io/pyspecan/)
 - [PyPI](https://pypi.org/project/pyspecan/)

# Examples
tkGUI, SWEPT mode
![tkGUI_Swept](/media/SWEPT_tkGUI.png)

tkGUI, RT mode
![tkGUI_RT](/media/RT_tkGUI.png)

# Usage
## Module
- `python3 -m pyspecan --help`
- GUI, swept: `python3 -m pyspecan`
- GUI, RT: `python3 -m pyspecan -m RT`

## Script
- GUI, swept: `pyspecan`
- GUI, RT: `pyspecan -m RT`

# Install
1. Run `python3 -m pip install pyspecan`
2. Run `python3 -m pyspecan`

# Contributing
1. `git clone https://github.com/Anonoei/pyspecan`
2. `cd pyspecan`
3. `git branch -c feature/<your feature>`
4. `python3 builder.py -b -l` build and install locally

## Build executable
1. `pyinstaller src/pyspecan.spec`
2. `./dist/pyspecan`
