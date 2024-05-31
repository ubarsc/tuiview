@echo off
rem * A startup script which could be added to the Windows Start menu
rem  This assumes you've installed the TuiView application
rem  into your tuiview directory in your user profile,
rem  e.g. c:\users\myname\tuiview
rem * You can change the default directory here:
cd %USERPROFILE%\Downloads
rem * You can set environment variables here:
rem   e.g. to allow loading non-georeferenced image files
rem set TUIVIEW_ALLOW_NOGEO=YES
%userprofile%\tuiview\scripts\tuiview.exe
