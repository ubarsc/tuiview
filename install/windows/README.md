# Create a Windows installer for TuiView

Use conda `constructor` to create a Windows installer. This is quite simple for the basic case of installing tuiview from `conda-forge`. However, in the case where the version of tuiview in the git repo is newer than the version in conda-forge, we need a few additional steps to a) create a Python wheel, b) include that wheel in the installer, c) run `pip install` during the installation process to override the conda version with the pip version. An additional complication is that building the wheel will require a C compiler but if you don't have one then we simply copy the pre-compiled version (on the assumption it's not changed in git) and only use the newer python files.

## Install TuiView via conda

* install Miniconda
    * download from https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe
    * install only for me, don't add to PATH, don't use as system Python
    * install path should be similar to `C:\Users\Me\miniconda3`

* Open a command prompt and run:
```
%USERPROFILE%\miniconda3\condabin\activate.bat
conda config --env --add channels conda-forge
conda config --env --set channel_priority strict
conda create -n tuiview tuiview
conda activate tuiview
```

## To run TuiView

To run TuiView you can create a batch file:
```
call %USERPROFILE%\miniconda3\condabin\activate.bat
call conda activate tuiview
set TUIVIEW_ALLOW_NOGEO=YES
tuiview
```

## Create a Windows installer

Create a standalone Windows installer which combines conda and tuiview

* Open a command prompt to install `constructor`

```
%USERPROFILE%\miniconda3\Scripts\activate.bat
conda activate tuiview
conda install constructor
```

* Clone the git repo and build a new wheel

```
cd %USERPROFILE%\miniconda3
mkdir src
cd src
git clone https://github.com/ubarsc/tuiview
cd tuiview
mkdir build
mkdir build\lib.win-amd64-cpython-312
mkdir build\lib.win-amd64-cpython-312\tuiview
set GDAL_HOME=%USERPROFILE%\miniconda3\envs\tuiview\Library
python .\setup.py bdist_wheel
```

* If you can't build vectorrasterizer (no C compiler) then copy the existing one:
```
copy %USERPROFILE%\miniconda3\envs\tuiview/Lib/site-packages/tuiview/vectorrasterizer.cp312-win_amd64.pyd build\lib.win-amd64-cpython-312\tuiview
python .\setup.py bdist_wheel
```

* Install the new wheel into the conda environment and test run tuiview to make sure it works
```
pip install --force-reinstall dist\TuiView-1.2.13-cp312-cp312-win_amd64.whl
```

* Copy the wheel into the `constructor` directory

```
copy dist\TuiView-1.2.13-cp312-cp312-win_amd64.whl install\windows
```

* Use `constructor` to build the installer

```
cd install\windows
constructor .
```

* Tell the user to run `tuiviewexe.bat` to start the application
* TO DO: add tuiviewexe.bat into the Start menu

## How it works

Conda `constructor` reads `construct.yaml` which installs the packages listed in `specs` from the given `channels`. We include `menuinst` to allow creation of a Start Menu item, and `console_shortcut` to allow Anaconda Prompt to be added to the Start Menu. Three additional files will be installed, two batch files and the python wheel we built above. After installation the script `post_install.bat` will be run; this script simply activates the environment and runs `pip install`.
