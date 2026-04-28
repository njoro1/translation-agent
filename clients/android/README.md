# Android Client Scaffold

This directory will contain the Android client for the Translation Agent.

## Core Requirements
- Capture system audio using `MediaProjection`.
- Stream audio chunks via WebSocket to the backend.
- Display subtitles using a `WindowManager` overlay (`TYPE_APPLICATION_OVERLAY`).
- Playback dubbed audio using `AudioTrack`.
