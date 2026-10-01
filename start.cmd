@echo off
rem Start Claude History Viewer in the background (restarts it if already running).
rem Extra arguments go to the viewer, e.g.  start.cmd --no-browser
rem Keep this file ASCII only with CRLF line endings: cmd.exe misreads UTF-8 and LF-only batch files.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\viewer.ps1" start %*
if errorlevel 1 pause
