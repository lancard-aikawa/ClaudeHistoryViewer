@echo off
rem Stop Claude History Viewer.
rem Keep this file ASCII only with CRLF line endings: cmd.exe misreads UTF-8 and LF-only batch files.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\viewer.ps1" stop
