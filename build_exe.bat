@echo off
REM ================================================================
REM  Rebuild the standalone TranslationAgent executable.
REM  Output: dist\TranslationAgent\TranslationAgent.exe  (onedir bundle)
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
REM Detect via the module, not the launcher: the Python Scripts folder is
REM often absent from PATH, which made "where pyinstaller" fail every run and
REM trigger a pointless reinstall. The build below uses "python -m PyInstaller"
REM for the same reason.
python -c "import PyInstaller" >nul 2>&1
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
if exist "dist\TranslationAgent" rmdir /s /q "dist\TranslationAgent"
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

echo [3/3] Building onedir bundle (trimmed PySide6 - usually under 2 min)...
REM "--hidden-import yt_dlp" pulls in yt-dlp's own PyInstaller hook (declared
REM through its "pyinstaller40" entry point), which collects the extractors,
REM requests/certifi and the yt-dlp-ejs JS helpers. A onefile exe has no Python
REM interpreter to spawn, so src/ytdlp.py runs the bundled copy in-process
REM instead of shelling out to "python -m yt_dlp".
REM ffmpeg is bundled under its real name (ffmpeg-win-x86_64-v7.1.exe). NOTE:
REM PyInstaller's --add-binary treats the destination as a *directory*, so it
REM cannot rename the file here. The rename to a literal "ffmpeg.exe" happens at
REM runtime in src.youtube_media._ensure_ffmpeg_exe_named() — yt-dlp's
REM --ffmpeg-location only finds a binary literally named ffmpeg(.exe), so
REM without that rename the video+audio merge never runs and the download ships
REM as two separate files (a video-only stream + an audio-only stream).
python -m PyInstaller --noconfirm --onedir --windowed --name TranslationAgent ^
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
    --hidden-import src.youtube_media ^
    --hidden-import src.ytdlp ^
    --hidden-import src.srt_io ^
    --hidden-import src.local_asr ^
    --hidden-import src.local_server ^
    --hidden-import translate ^
    --hidden-import dotenv ^
    --hidden-import openai ^
    --hidden-import yt_dlp ^
    main.py

if errorlevel 1 (
    echo.
    echo BUILD FAILED. See output above for details.
    pause
    exit /b 1
)

if not exist "dist\TranslationAgent\TranslationAgent.exe" (
    echo.
    echo BUILD FAILED: dist\TranslationAgent\TranslationAgent.exe was not produced.
    pause
    exit /b 1
)

REM Stamp a do-not-edit banner onto the spec PyInstaller just regenerated.
REM This step is why the banner belongs here rather than in the spec itself:
REM the spec is a *build artifact*, rewritten from the flags above on every
REM run, so a hand-added comment is silently discarded by the next build. The
REM banner has to be applied after the build, by its only author.
python "%~dp0tools\stamp_spec_header.py" TranslationAgent.spec
if errorlevel 1 (
    echo WARNING: could not stamp the generated spec header.
)

echo.
echo ================================================================
echo  BUILD SUCCEEDED: dist\TranslationAgent\TranslationAgent.exe
echo ================================================================
pause
