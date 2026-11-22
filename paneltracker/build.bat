@echo off
REM ============================================================
REM  Build PanelTracker.exe  (double-click file ini di Windows)
REM  Syarat: Python 3.10 - 3.13 (64-bit) sudah terinstall
REM          centang "Add python.exe to PATH" saat install.
REM ============================================================
setlocal
cd /d "%~dp0"

set PY=
where py >nul 2>nul && set PY=py -3
if not defined PY (where python >nul 2>nul && set PY=python)
if not defined PY (
  echo [X] Python tidak ditemukan. Install dari https://www.python.org/downloads/windows/
  pause & exit /b 1
)

echo [1/4] Membuat virtual environment...
if not exist .venv %PY% -m venv .venv || (echo Gagal membuat venv & pause & exit /b 1)
call .venv\Scripts\activate.bat

echo [2/4] Install library...
python -m pip install --upgrade pip >nul
pip install -r requirements.txt || (echo Gagal install library & pause & exit /b 1)

echo [3/4] Build exe (2-5 menit)...
pyinstaller --noconfirm --clean PanelTracker.spec || (echo Build gagal & pause & exit /b 1)

echo [4/4] Self-test exe...
if exist build\selftest rmdir /s /q build\selftest
start /wait "" dist\PanelTracker.exe --selftest build\selftest
if exist build\selftest\punchlist.pdf (
  echo     Self-test OK - report contoh ada di build\selftest
) else (
  echo     [!] Self-test gagal - coba jalankan dist\PanelTracker.exe manual
)

echo.
echo ============================================================
echo  SELESAI:  %cd%\dist\PanelTracker.exe   (portable, 1 file)
echo  Copy exe ke folder mana saja / flashdisk. Data otomatis
echo  disimpan di folder PanelTracker_Data di samping exe.
echo ============================================================
explorer dist
pause
