@echo off
REM ================================================================
REM  Rebuild the standalone TranslationAgent executable.
REM  Output: dist\TranslationAgent.exe
REM
REM  Run this any time after changing Python or QML source files.
REM
REM  The build is trimmed to only the PySide6 modules the app uses
REM  (QtCore / QtGui / QtQml / QtQuick / QtQuickControls2), instead of
REM  bundling all of PySide6 (~300 modules). This makes builds much
REM  faster and the exe much smaller. If you add a new Qt import to
REM  the code, add the matching hidden-import below.
REM ================================================================
setlocal
cd /d "%~dp0"

echo [1/3] Checking PyInstaller...
where pyinstaller >nul 2>&1
if errorlevel 1 (
    echo PyInstaller not found. Installing...
    python -m pip install pyinstaller
    if errorlevel 1 (
        echo ERROR: Failed to install PyInstaller.
        pause
        exit /b 1
    )
)

echo [2/3] Removing previous build output...
if exist "dist\TranslationAgent.exe" del /f /q "dist\TranslationAgent.exe"

for /f "usebackq delims=" %%P in (`python -c "import PySide6, os; print(os.path.dirname(PySide6.__file__))"`) do set PYSIDE6_DIR=%%P
if not defined PYSIDE6_DIR (
    echo ERROR: Could not locate the PySide6 package directory via python.
    pause
    exit /b 1
)
echo Found PySide6 at: %PYSIDE6_DIR%

for /f "usebackq delims=" %%F in (`python -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())"`) do set FFMPEG_EXE=%%F
if not defined FFMPEG_EXE (
    echo ERROR: Could not locate a bundled ffmpeg binary via imageio-ffmpeg.
    echo        Install it with: python -m pip install imageio-ffmpeg
    pause
    exit /b 1
)
echo Found ffmpeg at: %FFMPEG_EXE%

if not exist "vendor\funasr\llama-funasr-sensevoice.exe" (
    echo ERROR: Missing vendor\funasr\llama-funasr-sensevoice.exe
    echo        Place the FunASR SenseVoice runtime binary there before building.
    pause
    exit /b 1
)
echo Found llama-funasr-sensevoice in: vendor\funasr\

if not exist "vendor\funasr\llama-funasr-vad.exe" (
    echo ERROR: Missing vendor\funasr\llama-funasr-vad.exe
    echo        Place the FunASR VAD runtime binary there before building.
    pause
    exit /b 1
)
echo Found llama-funasr-vad in: vendor\funasr\

if not exist "vendor\llama\llama-server.exe" (
    echo ERROR: Bundled llama-server not found at vendor\llama\llama-server.exe.
    echo        Download the llama.cpp Windows CPU release and put llama-server.exe
    echo        plus its DLLs in vendor\llama\.
    pause
    exit /b 1
)
echo Found llama-server in: vendor\llama\

echo [3/3] Building executable (trimmed PySide6 - usually under 2 min)...
pyinstaller --noconfirm --onefile --windowed --name TranslationAgent ^
    --hidden-import PySide6.QtCore ^
    --hidden-import PySide6.QtGui ^
    --hidden-import PySide6.QtQml ^
    --hidden-import PySide6.QtQuick ^
    --hidden-import PySide6.QtQuickControls2 ^
    --hidden-import PySide6.QtNetwork ^
    --hidden-import PySide6.QtWidgets ^
    --add-data "ui;ui" ^
    --add-binary "%FFMPEG_EXE%;." ^
    --add-data "vendor\funasr;vendor/funasr" ^
    --add-data "vendor\llama;vendor\llama" ^
    --add-data "ui/qml;ui/qml" ^
    --add-data "ui/qml/components;ui/qml/components" ^
    --add-data "ui/qml/views;ui/qml/views" ^
    --add-data "%PYSIDE6_DIR%\qml\Qt;PySide6/qml/Qt" ^
    --add-data "%PYSIDE6_DIR%\qml\QtQml;PySide6/qml/QtQml" ^
    --add-data "%PYSIDE6_DIR%\qml\QtQuick;PySide6/qml/QtQuick" ^
    --add-data "%PYSIDE6_DIR%\qml\builtins.qmltypes;PySide6/qml" ^
    --add-data "%PYSIDE6_DIR%\qml\jsroot.qmltypes;PySide6/qml" ^
    --add-data "%PYSIDE6_DIR%\plugins\platforms;PySide6/plugins/platforms" ^
    --add-data "%PYSIDE6_DIR%\plugins\imageformats;PySide6/plugins/imageformats" ^
    --add-data "%PYSIDE6_DIR%\plugins\styles;PySide6/plugins/styles" ^
    --add-data "%PYSIDE6_DIR%\plugins\iconengines;PySide6/plugins/iconengines" ^
    --add-data "%PYSIDE6_DIR%\plugins\qmltooling;PySide6/plugins/qmltooling" ^
    --hidden-import backend ^
    --hidden-import backend.bridge ^
    --hidden-import backend.controllers ^
    --hidden-import backend.controllers.translation ^
    --hidden-import backend.models ^
    --hidden-import backend.models.run_config ^
    --hidden-import src ^
    --hidden-import src.config ^
    --hidden-import src.fetch_subs ^
    --hidden-import src.translate ^
    --hidden-import src.srt_io ^
    --hidden-import src.local_asr ^
    --hidden-import src.local_server ^
    --hidden-import translate ^
    --hidden-import dotenv ^
    --hidden-import openai ^
    main.py

if errorlevel 1 (
    echo.
    echo BUILD FAILED. See output above for details.
    pause
    exit /b 1
)

if not exist "dist\TranslationAgent.exe" (
    echo.
    echo BUILD FAILED: dist\TranslationAgent.exe was not produced.
    pause
    exit /b 1
)

echo.
echo ================================================================
echo  BUILD SUCCEEDED: dist\TranslationAgent.exe
echo ================================================================
pause
