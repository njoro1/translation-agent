Bundled CJK fonts
=================

Drop an open-license CJK font here so Japanese/Chinese/Korean text renders
consistently in the GUI (source cue column, review table, logs).

Recommended: Noto Sans CJK JP (SIL Open Font License 1.1)
    https://github.com/notofonts/noto-cjk/releases

Accepted files: *.ttf, *.otf, *.ttc

The directory is optional: if it is missing or empty the app starts normally
and Qt falls back to system fonts. When packaging with PyInstaller, bundle
this directory (see translation_agent.spec datas).
