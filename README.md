# Real-Time Context-Aware Video Translation & Dubbing System

## Overview
This project is a cross-platform AI system that enables real-time translation and dubbing of video and audio content.

It runs as a background service on both Windows and Android, capturing system audio from any source (e.g. YouTube, local media, livestreams) and providing:

- Live translated subtitles (overlay)
- Real-time AI-generated voice dubbing
- Context-aware translation across continuous speech

The system is designed as a streaming pipeline, preserving meaning, tone, and domain context rather than translating isolated sentences.

## Core Features
- System-level audio capture (Windows + Android)
- Real-time speech-to-text (Chinese initially)
- Context-aware translation (Chinese → English)
- Live subtitle overlay (non-intrusive UI layer)
- AI voice dubbing with buffered playback
- Background service execution

## Key Differentiators
- Maintains rolling context across video streams
- Works across any application (not tied to a single platform like YouTube)
- Streaming-first design for low latency
- Modular architecture for multilingual expansion
- Designed for efficient token usage under constrained budgets

## System Architecture

Audio Capture (Device)
        ↓
Chunking / Streaming Layer
        ↓
Speech-to-Text (ASR)
        ↓
Context Manager
        ↓
Translation Engine (MiMo)
        ↓
   ┌───────────────┬───────────────┐
   ↓               ↓
Subtitle Renderer  Text-to-Speech (TTS)
   ↓               ↓
Overlay UI         Audio Playback

## Tech Stack

### Core AI Backend (Shared)
- Python (FastAPI)
- WebSockets (real-time streaming)
- Whisper / Faster-Whisper (ASR)
- MiMo API (translation + reasoning)
- Coqui TTS / Edge TTS

### Android Client
- Kotlin
- MediaProjection API (audio capture)
- Foreground service
- Overlay UI (WindowManager)

### Windows Client
- Python (or C# optional)
- WASAPI loopback (audio capture)
- PyQt / Electron (overlay UI)
- SoundDevice / PyAudio (audio playback)

## Streaming Design
- Audio processed in small chunks (1–2 seconds)
- Incremental transcription
- Context-aware translation using rolling memory
- Subtitle updates streamed in real time
- TTS buffered for smooth playback

## Roadmap

### Phase 1
- Audio capture (Windows + Android)
- Speech-to-text pipeline
- Basic subtitle overlay

### Phase 2
- Context-aware translation (MiMo integration)
- Streaming subtitles

### Phase 3
- Real-time voice dubbing
- Latency optimization

### Phase 4
- Multilingual expansion
- Edge/on-device inference exploration

## Challenges
- Maintaining low latency across pipeline stages
- OS-specific audio capture constraints
- Synchronization of subtitles and dubbed audio
- Efficient context window management

## Vision
To create a universal AI layer that allows users to understand any audio or video content in real time, regardless of language.

Future versions will support multiple languages and explore on-device deployment within mobile and desktop ecosystems.