@echo off
cd /d "%~dp0"
python -m PyInstaller --noconfirm --onefile --windowed --name TranslationAgent ^
    --hidden-import PySide6.QtCore ^
    --hidden-import PySide6.QtGui ^
    --hidden-import PySide6.QtQml ^
    --hidden-import PySide6.QtQuick ^
    --hidden-import PySide6.QtQuickControls2 ^
    --hidden-import PySide6.QtNetwork ^
    --hidden-import PySide6.QtWidgets ^
    --add-data "ui;ui" ^
    --add-binary "C:\Users\Njoro\AppData\Local\Programs\Python\Python312\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe;." ^
    --add-data "vendor\funasr;vendor\funasr" ^
    --add-data "vendor\llama;vendor\llama" ^
    --add-data "ui/qml;ui/qml" ^
    --add-data "ui/qml/components;ui/qml/components" ^
    --add-data "ui/qml/views;ui/qml/views" ^
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
echo EXITCODE=%ERRORLEVEL% > _build_result.txt
