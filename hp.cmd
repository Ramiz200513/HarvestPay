@echo off
rem Wrapper for hp.ps1: works even when PowerShell script execution is disabled.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0hp.ps1" %*
