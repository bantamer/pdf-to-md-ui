@echo off
rem One-click Windows build: venv -> dependencies -> trimmed JRE -> exe -> setup.
rem
rem Double-click this file (or run it from cmd) inside the project folder.
rem Everything lands in .venv, jre and dist next to this script; nothing is
rem installed system-wide.
rem
rem Messages are ASCII on purpose: a .bat with Cyrillic text renders as mojibake
rem under the default console codepage. See BUILD.md for the Russian version.

setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo === PDF to Markdown - build ===
echo.

rem ---------------------------------------------------------------- Python
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo [X] Python 3.10+ not found.
    echo     Install it from https://www.python.org/downloads/windows/
    echo     and tick "Add python.exe to PATH", then run this script again.
    goto :fail
)

if exist ".venv\Scripts\python.exe" (
    echo [1/4] Virtual environment .venv already exists.
) else (
    echo [1/4] Creating virtual environment .venv ...
    %PY% -m venv .venv || goto :fail
)
set "VPY=%CD%\.venv\Scripts\python.exe"

rem ---------------------------------------------------------- Dependencies
echo [2/4] Installing dependencies ^(a few minutes on first run^) ...
"%VPY%" -m pip install --upgrade pip >nul 2>nul
"%VPY%" -m pip install -r requirements.txt pyinstaller || goto :fail

rem ------------------------------------------------------------ Java runtime
echo [3/4] Preparing the bundled Java runtime ...
call :build_jre

rem -------------------------------------------------------------- The exe
echo [4/4] Building the executable ...
"%VPY%" -m PyInstaller --noconfirm --clean app.spec || goto :fail

if exist "jre\bin\java.exe" (
    rem The app looks for a "jre" folder beside the exe, so mirror the layout
    rem the installer produces and a copied dist folder works on its own too.
    echo       Copying jre\ into the build ...
    robocopy jre "dist\PDF to Markdown\jre" /e /njh /njs /ndl /nfl >nul
)

rem ----------------------------------------------------------- Installer
set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC for /f "delims=" %%i in ('where iscc 2^>nul') do set "ISCC=%%i"

if defined ISCC (
    echo       Building the installer with Inno Setup ...
    "!ISCC!" installer.iss || goto :fail
)

echo.
echo === Done ===
echo.
echo   Application: "%CD%\dist\PDF to Markdown\PDF to Markdown.exe"
if defined ISCC echo   Installer:   "%CD%\Output\PDF-to-Markdown-Setup.exe"
if not defined ISCC (
    echo   Installer:   skipped - Inno Setup is not installed.
    echo                Get it at https://jrsoftware.org/isdl.php to produce
    echo                a single Setup.exe for other machines.
)
echo.
echo   The exe needs the whole "PDF to Markdown" folder - copy the folder,
echo   not just the exe.
echo.
pause
exit /b 0

rem ------------------------------------------------------------------------
:build_jre
if exist "jre\bin\java.exe" (
    echo       jre\ already there - skipping jlink.
    exit /b 0
)
set "JLINK="
if exist "%JAVA_HOME%\bin\jlink.exe" set "JLINK=%JAVA_HOME%\bin\jlink.exe"
if not defined JLINK for /f "delims=" %%i in ('where jlink 2^>nul') do set "JLINK=%%i"
if not defined JLINK (
    echo       jlink not found - building without a bundled runtime.
    echo       The app will then need Java 11+ installed on every machine it
    echo       runs on. Install Temurin 25 ^(any JDK 17+ works^) from https://adoptium.net and re-run
    echo       this script to ship Java inside the build instead.
    exit /b 0
)
rem jdk.unsupported carries sun.misc.Unsafe, which PDFBox needs to release
rem memory-mapped files; without it every image-bearing PDF logs
rem "SEVERE: Unmapping is not supported" and keeps the file mapped until GC.
set "JMODS=java.base,java.desktop,java.logging,java.naming,java.xml,jdk.unsupported"
"!JLINK!" --add-modules %JMODS% --strip-debug --no-header-files --no-man-pages --compress=2 --output jre >nul 2>nul
if errorlevel 1 (
    rem --compress=2 was dropped in newer JDKs; retry without it.
    rd /s /q jre 2>nul
    "!JLINK!" --add-modules %JMODS% --strip-debug --no-header-files --no-man-pages --output jre || goto :jre_failed
)
echo       Bundled runtime ready in jre\.
exit /b 0

:jre_failed
echo       jlink failed - continuing without a bundled runtime.
rd /s /q jre 2>nul
exit /b 0

rem ------------------------------------------------------------------------
:fail
echo.
echo [X] Build failed - see the messages above.
echo.
pause
exit /b 1
