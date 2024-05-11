@echo off
rem  This assumes you've installed the TuiView application
rem  into your tuiview directory in your user profile,
rem  e.g. c:\users\myname\tuiview
rem  You can change the default directory here:
cd %USERPROFILE%\Downloads
set TUIVIEW_ALLOW_NOGEO=YES
%userprofile%\tuiview\scripts\tuiview.exe