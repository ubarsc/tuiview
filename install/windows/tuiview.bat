@echo off
rem * You can change directory to where your files are stored
cd %USERPROFILE%\Downloads
rem * You can activate the conda environment if you want
rem call %USERPROFILE%\miniconda3\condabin\activate.bat
rem call conda activate tuiview
rem * You can set some environment variables if you want
rem   e.g. to allow loading non-georeferenced image files
rem set TUIVIEW_ALLOW_NOGEO=YES
%userprofile%\tuiview\scripts\tuiview.exe
