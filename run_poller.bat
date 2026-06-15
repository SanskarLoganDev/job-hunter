@echo off
REM run_poller.bat
REM Called by Windows Task Scheduler every 30 minutes.
REM Output is captured by the rotating log file at logs/poller.log
REM You can also run this manually from any terminal to test.

cd /d E:\Coding-practice\Projects\job-hunter
.venv\Scripts\python.exe poller.py
