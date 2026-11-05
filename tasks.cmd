@echo off
rem Wrapper around tasks.ps1. Works regardless of PowerShell ExecutionPolicy.
rem Usage: tasks.cmd <up|down|migrate|test|lint|fmt|psql|ps|clean|help>
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tasks.ps1" %*
exit /b %ERRORLEVEL%
