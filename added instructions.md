# EXECUTION PROMPT — Clearly Delineate Application Flows in the UI

You are implementing UI/UX and flow-control changes for **Translation Agent / YouTube Subtitle Translator**.

Your task is to make the different pipeline flows clearly separated in the interface, especially for **local video files**.

The application must clearly distinguish between:

1. **YouTube subtitle translation flows**
2. **Local video flows**
3. **Fully Offline local flow**
4. **Hybrid local flow**

Do not mix these concepts into a single ambiguous “backend” dropdown. The user should always know exactly which pipeline they are running.

---

# 1. Project Context

This application produces English `.srt` subtitles from either:

- a YouTube URL using existing original-language captions, or
- a local media file using local ASR transcription.

The target hardware is low-spec:

- 8th-gen Intel i5
- 16 GB RAM
- no GPU
- CPU-only inference

The default local translation model is:

```text
Hy-MT2-1.8B-1.25bit-v2.gguf
```

Local ASR uses:

- FunASR
- SenseVoiceSmall
- FSMN VAD

Whisper.cpp must not be introduced.

The project has hard invariants:

- Timestamps are sacred for YouTube/cloud caption output.
- Cue count in == cue count out.
- Target language is fixed to English.
- Do not rewrite the foreignization directive.
- Do not block the QML thread.
- Local servers may use placeholder API keys.
- Fully offline mode must not require internet access.

---

# 2. Primary Objective

Make the interface clearly communicate the active pipeline.

For **local video**, expose two distinct user-facing flows:

## 2.1 Fully Offline

Description:

> Transcribe and translate entirely on this computer. No internet connection is used.

Pipeline:

```text
Local media file
  → local FFmpeg audio extraction
  → local FunASR + SenseVoice ASR
  → local Hy-MT2 translation
  → local SRT output
```

Requirements:

- Must not call remote cloud LLM endpoints.
- Must not require `OPENAI_API_KEY`.
- Must not require internet access.
- Local llama.cpp server on localhost is allowed.
- Cloud API fields should be hidden or clearly disabled.
- This should be the default local-video flow.

## 2.2 Hybrid — Offline-first with Optional Cloud Rescue

Description:

> Transcribe and translate locally first. Use cloud only if local translation fails, and only for the failed lines.

Pipeline:

```text
Local media file
  → local FFmpeg audio extraction
  → local FunASR + SenseVoice ASR
  → local Hy-MT2 translation
  → if local translation fails for specific cues:
      → optional cloud rescue for those cues only
  → local SRT output
```

Requirements:

- Must remain offline-first.
- Must not use cloud as the primary translator unless the user explicitly chooses a separate full-cloud mode, if exposed.
- Cloud rescue must be optional.
- If cloud credentials are missing or invalid, the run should still proceed locally and log a warning.
- The UI must clearly indicate when cloud rescue is enabled.
- The UI must show if cloud rescue actually translated any cues.

---

# 3. Required Flow Matrix

Implement the UI and run configuration around this matrix.

| Source | Flow name | Subtitle source | ASR | Translation | Cloud rescue | Internet required |
|---|---|---:|---|---|---|---|
| YouTube URL | YouTube + Cloud Translation | YouTube captions | None | Cloud LLM | No | Yes |
| YouTube URL | YouTube + Local Translation | YouTube captions | None | Local Hy-MT2 | No | No |
| Local video | Local Video + Fully Offline | Local ASR | FunASR local | Local Hy-MT2 | No | No |
| Local video | Local Video + Hybrid | Local ASR | FunASR local | Local Hy-MT2 first | Optional, failed cues only | Only if rescue is triggered |

Do not expose local video ASR as a cloud service. Local video transcription remains local.

---

# 4. UI Requirements

## 4.1 Top-level source selection

The Dashboard must clearly separate source type:

```text
Source
  ( ) YouTube URL
  ( ) Local Video File
```

Use radio buttons, segmented buttons, or cards. Do not rely on a generic mode label only.

When **YouTube URL** is selected:

- Show YouTube URL input.
- Show output path.
- Show translation backend choice:
  - Cloud Translation
  - Local Translation

When **Local Video File** is selected:

- Show local file path input.
- Show output path.
- Show local pipeline choice:
  - Fully Offline
  - Hybrid — Offline-first with Cloud Rescue

Do not show the YouTube URL field when local video is selected.

Do not show the local file picker when YouTube is selected.

---

## 4.2 Local video pipeline selector

For local video, show a clearly labeled section:

```text
Local Video Translation Pipeline
```

Options:

### Option A — Fully Offline

Label:

```text
Fully Offline
```

Helper text:

```text
Transcribe and translate entirely on this computer. No internet connection is used.
```

### Option B — Hybrid

Label:

```text
Hybrid — Offline-first with Cloud Rescue
```

Helper text:

```text
Transcribe and translate locally first. If local translation fails for specific lines, use a cloud model only for those lines.
```

Default selection:

```text
Fully Offline
```

Hybrid must never be the default.

---

## 4.3 Pipeline summary panel

Add a visible pipeline summary that updates when the user changes options.

For local offline:

```text
Selected pipeline:
1. Read local video file
2. Extract audio locally
3. Transcribe locally with FunASR + SenseVoice
4. Translate locally with Hy-MT2
5. Write English SRT

Internet required: No
Cloud assistance: Disabled
```

For local hybrid:

```text
Selected pipeline:
1. Read local video file
2. Extract audio locally
3. Transcribe locally with FunASR + SenseVoice
4. Translate locally with Hy-MT2
5. If local translation fails, optionally rescue failed lines with cloud
6. Write English SRT

Internet required: Only if cloud rescue is triggered
Cloud assistance: Failed cues only
```

For YouTube cloud:

```text
Selected pipeline:
1. Fetch original YouTube captions
2. Translate with cloud LLM
3. Write English SRT

Internet required: Yes
Cloud assistance: Full translation
```

For YouTube local:

```text
Selected pipeline:
1. Fetch original YouTube captions
2. Translate locally with Hy-MT2
3. Write English SRT

Internet required: Only for fetching YouTube captions
Cloud assistance: Disabled
```

This summary is important. It prevents user confusion.

---

## 4.4 Disable irrelevant settings by flow

The interface must not present irrelevant controls as active.

### Fully Offline local video

Hide or disable:

- API key
- cloud base URL
- cloud model
- cloud rescue model
- cloud rescue batch size

Show:

- local model path/status
- ASR model status
- VAD model status
- local server host/port if advanced settings are shown
- local ASR settings

If cloud fields are shown in a shared Settings page, mark them as disabled with a note:

```text
Cloud settings are not used in Fully Offline mode.
```

### Hybrid local video

Show:

- all Fully Offline fields
- cloud rescue enabled indicator
- cloud rescue model, optional
- cloud credentials status

Do not imply that cloud is required.

Show a credential status line:

```text
Cloud rescue credentials: Configured
```

or:

```text
Cloud rescue credentials: Not configured. The run will continue locally if rescue is needed.
```

### YouTube Cloud Translation

Show:

- API key
- base URL
- cloud model
- batch size

Hide or disable:

- local ASR settings, because YouTube captions are used
- local model download, unless the user switches to local translation

### YouTube Local Translation

Show:

- local model status
- local server settings
- batch size

Hide or disable:

- API key/cloud fields, or mark them unused
- local ASR settings, because YouTube captions are used

---

# 5. AppBridge / State Requirements

Update `backend/bridge.py` so the QML UI can clearly control and display flows.

You may preserve existing properties for backward compatibility, but add clear flow-oriented properties.

## 5.1 Recommended properties

Add or adapt these properties:

```python
sourceMode: str
```

Values:

```text
"youtube"
"local"
```

```python
localPipelineMode: str
```

Values:

```text
"offline"
"hybrid"
```

```python
youtubeBackend: str
```

Values:

```text
"cloud"
"local"
```

If reusing the existing `backend` property, make its meaning context-dependent and document it carefully. However, for UI clarity, it is better to have explicit properties.

## 5.2 Computed pipeline ID

Add a computed property:

```python
pipelineId: str
```

Values:

```text
"youtube_cloud"
"youtube_local"
"local_offline"
"local_hybrid"
```

Expose it to QML for the pipeline summary panel.

## 5.3 Validation state

Add properties for UI readiness:

```python
localModelsReady: bool
asrModelsReady: bool
cloudCredentialsReady: bool
pipelineWarning: str
pipelineError: str
```

Examples:

```text
localModelsReady = Hy-MT2 GGUF exists
asrModelsReady = SenseVoice GGUF and FSMN VAD GGUF exist
cloudCredentialsReady = API key/base URL/model appear valid
```

Do not persist API key.

---

# 6. RunConfig Mapping

Update `AppBridge._build_run_config()` so the selected UI flow maps cleanly to CLI arguments and environment variables.

## 6.1 Local Video + Fully Offline

Required behavior:

```text
No remote cloud LLM calls.
```

Recommended CLI mapping:

```text
--file {filePath}
--local
--local-model {localModel}
--pipeline offline
```

Or, if `--pipeline` is not implemented, use equivalent flags:

```text
--file {filePath}
--local
--local-model {localModel}
--no-cloud-rescue
```

Recommended env:

```env
PIPELINE_FLOW=local_offline
OFFLINE_STRICT=1
CLOUD_RESCUE_ENABLED=0
```

`OFFLINE_STRICT=1` must mean:

- Do not construct a remote OpenAI client.
- Do not use `OPENAI_API_KEY` for translation.
- Fail if the pipeline attempts to use a non-local translation endpoint.

Localhost llama.cpp server is still allowed.

## 6.2 Local Video + Hybrid

Required behavior:

```text
Local ASR + local Hy-MT2 first, cloud rescue only for failed cues.
```

Recommended CLI mapping:

```text
--file {filePath}
--local
--local-model {localModel}
--pipeline hybrid
--cloud-rescue
```

Recommended env:

```env
PIPELINE_FLOW=local_hybrid
OFFLINE_STRICT=0
CLOUD_RESCUE_ENABLED=1
```

If cloud credentials are missing, do not block the run. Instead, pass configuration and let the pipeline log a warning if rescue becomes necessary.

## 6.3 YouTube + Cloud Translation

Recommended env:

```env
PIPELINE_FLOW=youtube_cloud
CLOUD_RESCUE_ENABLED=0
OFFLINE_STRICT=0
```

## 6.4 YouTube + Local Translation

Recommended env:

```env
PIPELINE_FLOW=youtube_local
CLOUD_RESCUE_ENABLED=0
OFFLINE_STRICT=1
```

For YouTube local translation, internet is still needed to fetch YouTube captions, but translation must not use a remote LLM.

---

# 7. CLI Compatibility

The CLI must remain compatible with existing usage.

Preserve existing flags:

```text
--file
--local
--model
--out
--batch
--local-host
--local-port
--local-model
--local-model-name
--asr-*
```

Add new flow flags if useful:

```text
--pipeline offline|hybrid|cloud
--cloud-rescue
--no-cloud-rescue
```

Recommended behavior:

| CLI input | Effective flow |
|---|---|
| `translate.py URL` | YouTube cloud translation |
| `translate.py URL --local` | YouTube local translation |
| `translate.py --file video.mp4 --local` | Local video fully offline, unless rescue flags say otherwise |
| `translate.py --file video.mp4 --pipeline offline` | Local video fully offline |
| `translate.py --file video.mp4 --pipeline hybrid` | Local video hybrid |
| `translate.py --file video.mp4 --local --cloud-rescue` | Local video hybrid |
| `translate.py --file video.mp4` without `--local` | Preserve legacy behavior if possible, but GUI should always set an explicit pipeline |

Do not break old CLI runs.

If `--pipeline` and `--local` conflict, resolve predictably:

```text
--pipeline offline implies --local and disables rescue.
--pipeline hybrid implies --local and enables rescue.
--pipeline cloud disables local translation.
```

Log the resolved flow:

```text
[flow] Resolved pipeline: local_offline
```

or:

```text
[flow] Resolved pipeline: local_hybrid
```

---

# 8. Guardrails for Fully Offline Mode

Fully Offline mode must be enforceable in code, not just in UI wording.

When `OFFLINE_STRICT=1` or `--pipeline offline` is active:

1. Do not require `OPENAI_API_KEY`.
2. Do not call remote cloud endpoints.
3. Do not enable cloud rescue.
4. If the translation model is not local, raise a clear configuration error.
5. If a remote base URL is configured, ignore it for translation or reject it with a clear message.

Example error:

```text
Fully Offline mode requires a local translation model.
Remove --model or choose a local GGUF model.
```

Localhost is allowed for the local llama.cpp server.

Example allowed endpoint:

```text
http://127.0.0.1:8080/v1
```

Example disallowed endpoint in offline mode:

```text
https://openrouter.ai/api/v1
```

---

# 9. Hybrid Mode Behavior Requirements

Hybrid mode must be conservative and transparent.

## 9.1 What hybrid may do

Hybrid may:

- use local ASR,
- use local Hy-MT2 translation first,
- send only failed local translation cues to a cloud model,
- log which cues were rescued,
- fall back to offline behavior if cloud credentials are unavailable.

## 9.2 What hybrid must not do

Hybrid must not:

- send the whole file to the cloud by default,
- replace local translation with cloud translation silently,
- require cloud credentials to start,
- fail the whole run if cloud rescue is unavailable,
- change timestamps,
- break cue count alignment.

## 9.3 Rescue reporting

At the end of a hybrid run, print a clear summary:

```text
[rescue] Local translation succeeded for 428/431 cues
[rescue] Cloud rescue succeeded for 3 cues
[rescue] Cloud rescue failed for 0 cues
```

If no rescue was needed:

```text
[rescue] Cloud rescue was enabled but not needed
```

If rescue was needed but credentials were missing:

```text
[rescue] Cloud rescue was needed for 3 cues, but no cloud credentials are configured
[rescue] Those cues were handled by local fallback/failure behavior
```

The GUI should show this in the log panel.

---

# 10. QML Implementation Requirements

Update the QML views so the flow separation is visually obvious.

## 10.1 DashboardView

Modify:

```text
ui/qml/views/DashboardView.qml
```

Add:

1. Source selector:
   - YouTube URL
   - Local Video File

2. Contextual input area:
   - URL field for YouTube
   - file picker for local video

3. Pipeline selector:
   - For YouTube: Cloud Translation / Local Translation
   - For local video: Fully Offline / Hybrid

4. Pipeline summary card.

5. Readiness indicators:
   - local translation model present
   - ASR model present
   - VAD model present
   - cloud credentials configured, only relevant for cloud/hybrid

6. Run button label that reflects the flow.

Recommended Run button labels:

| Flow | Button label |
|---|---|
| YouTube cloud | `Translate with Cloud` |
| YouTube local | `Translate Locally` |
| Local offline | `Translate Fully Offline` |
| Local hybrid | `Translate Hybrid` |

## 10.2 SettingsView

Modify:

```text
ui/qml/views/SettingsView.qml
```

Organize settings into sections:

```text
Cloud Translation
Local Translation Model
Local ASR
Hybrid / Cloud Rescue
Advanced
```

Show only relevant sections based on current flow, or clearly disable irrelevant sections.

For example:

- In Local Offline mode, disable Cloud Translation section.
- In YouTube Cloud mode, disable Local ASR section.
- In YouTube Local mode, disable Local ASR section but enable Local Translation Model section.
- In Local Hybrid mode, enable Local Translation, Local ASR, and Hybrid/Cloud Rescue sections.

## 10.3 Visual clarity

Use clear section titles and helper text.

Example:

```text
Local Video Pipeline
Choose how local video subtitles are produced.
```

Example option cards:

```text
Fully Offline
Best for privacy and low-spec hardware.
Uses local ASR and local Hy-MT2 translation.

Hybrid — Offline-first with Cloud Rescue
Uses local processing first.
Cloud is only used if local translation fails.
```

Use subtle visual distinction:

- Offline: green or neutral indicator
- Hybrid: blue or amber indicator
- Cloud: blue/purple indicator

Do not make the UI look like all modes are equivalent. The flows are different.

---

# 11. Model and Readiness UX

For local flows, show model availability clearly.

## 11.1 Required local components

For local video fully offline:

```text
Hy-MT2 translation model
SenseVoice ASR model
FSMN VAD model
```

For YouTube local translation:

```text
Hy-MT2 translation model
```

For local ASR flows:

```text
SenseVoice ASR model
FSMN VAD model
```

## 11.2 Status chips

Show status such as:

```text
Hy-MT2 model: Ready
SenseVoice model: Missing
VAD model: Ready
```

If a required model is missing, show download button or instruction.

Example:

```text
Hy-MT2 model is missing. Download it before running Fully Offline translation.
```

Do not block the UI thread while downloading.

---

# 12. Error and Warning Messages

Use clear, flow-specific messages.

## 12.1 Fully Offline missing local model

```text
Fully Offline mode requires the Hy-MT2 local translation model.
Download the model or choose a different pipeline.
```

## 12.2 Fully Offline missing ASR models

```text
Local video translation requires SenseVoice and FSMN VAD models.
Download the ASR models before running Fully Offline mode.
```

## 12.3 Hybrid missing cloud credentials

```text
Hybrid mode is running, but cloud credentials are not configured.
Local translation will still run. Cloud rescue will be skipped if needed.
```

## 12.4 Hybrid rescue unavailable

```text
Cloud rescue was needed for 3 cues, but cloud credentials are not available.
The pipeline continued using local fallback behavior.
```

## 12.5 Offline strict violation

```text
Fully Offline mode cannot use a remote cloud endpoint.
Use a local model or switch to Hybrid/Cloud mode.
```

---

# 13. Logging Requirements

Use clear prefixes so users can understand what happened.

Recommended prefixes:

```text
[flow]
[offline]
[hybrid]
[rescue]
[local]
[cloud]
[asr]
[quality]
```

Examples:

```text
[flow] Source: local video
[flow] Pipeline: local_offline
[offline] Cloud rescue disabled
[asr] Using local FunASR + SenseVoice
[local] Using Hy-MT2 model: gguf/Hy-MT2-1.8B-1.25bit-v2.gguf
```

Hybrid:

```text
[flow] Source: local video
[flow] Pipeline: local_hybrid
[hybrid] Local translation first; cloud rescue enabled for failed cues only
[rescue] Cloud rescue translated 2/431 cues
```

---

# 14. Persistence Requirements

Persist non-secret flow preferences using `QSettings`.

Recommended keys:

```text
flow/sourceMode
flow/localPipelineMode
flow/youtubeBackend
```

Do not persist API keys.

Restore the selected flow on startup.

If a restored flow is invalid because required models are missing, still restore the selection but show a clear warning.

---

# 15. Acceptance Criteria

The implementation is complete when the following are true.

## 15.1 UI clarity

- The user can clearly choose between YouTube and Local Video.
- Local Video exposes exactly two primary pipeline choices:
  - Fully Offline
  - Hybrid — Offline-first with Cloud Rescue
- The selected pipeline is summarized before running.
- Irrelevant settings are hidden or disabled.
- Run button label reflects the selected flow.

## 15.2 Offline behavior

- Fully Offline mode does not require internet.
- Fully Offline mode does not require cloud API key.
- Fully Offline mode does not call remote LLM endpoints.
- Fully Offline mode fails clearly if required local models are missing.

## 15.3 Hybrid behavior

- Hybrid mode defaults to local processing.
- Hybrid mode uses cloud only for failed local cues.
- Hybrid mode works without cloud credentials, with a warning.
- Hybrid mode logs how many cues were rescued.
- Hybrid mode never silently becomes full cloud translation.

## 15.4 Configuration mapping

- GUI selected flow maps correctly to CLI/env.
- CLI old behavior remains compatible.
- New flow flags work predictably.
- Logs show the resolved pipeline.

## 15.5 Invariants

- Cue count remains aligned.
- Timestamps are not modified where prohibited.
- QML thread is not blocked.
- Foreignization directive is unchanged.
- Whisper.cpp is not introduced.

---

# 16. Manual Test Checklist

Run these tests after implementation.

## Test 1 — Local Video Fully Offline

1. Select Local Video File.
2. Choose Fully Offline.
3. Provide a local CJK video.
4. Disconnect internet if possible.
5. Run translation.
6. Verify:
   - no cloud calls are attempted,
   - local ASR runs,
   - local Hy-MT2 runs,
   - SRT is written,
   - log says `local_offline`.

## Test 2 — Local Video Fully Offline missing models

1. Remove or rename Hy-MT2 model.
2. Select Fully Offline.
3. Verify clear error/download prompt.
4. Do not crash.

## Test 3 — Local Video Hybrid without credentials

1. Select Local Video File.
2. Choose Hybrid.
3. Ensure no API key is configured.
4. Run translation.
5. Verify:
   - local processing runs,
   - warning says cloud rescue may be skipped,
   - run does not fail merely because credentials are missing.

## Test 4 — Local Video Hybrid with credentials

1. Select Hybrid.
2. Configure valid cloud credentials.
3. Run translation.
4. Verify:
   - local translation is attempted first,
   - cloud rescue occurs only if needed,
   - final log reports rescued cue count.

## Test 5 — YouTube Cloud

1. Select YouTube URL.
2. Choose Cloud Translation.
3. Verify cloud fields are active.
4. Verify local ASR fields are hidden/disabled.
5. Run translation.

## Test 6 — YouTube Local

1. Select YouTube URL.
2. Choose Local Translation.
3. Verify API key fields are hidden/disabled or marked unused.
4. Verify local model status is shown.
5. Run translation.

## Test 7 — Frozen build

1. Build with `build_exe.bat`.
2. Run `TranslationAgent.exe`.
3. Verify all flow controls work.
4. Verify logs appear.
5. Verify output folder button works.

---

# 17. Forbidden Changes

Do not:

1. Make Hybrid the default local flow.
2. Make Fully Offline depend on cloud credentials.
3. Use cloud rescue for the whole file by default.
4. Hide the fact that cloud was used.
5. Mix YouTube and local ASR controls into one ambiguous panel.
6. Introduce Whisper.cpp.
7. Modify timestamps where prohibited.
8. Break cue-count alignment.
9. Persist API keys.
10. Block the QML thread.

---

# 18. Final Implementation Guidance

Prefer clear, explicit flow states over clever automatic detection.

The user should never wonder:

- “Am I using the internet?”
- “Is this fully offline?”
- “Will cloud be used?”
- “Which models are required?”
- “Why is this setting disabled?”

The interface should answer those questions immediately.

The local video experience should feel like this:

```text
Choose file
Choose pipeline: Fully Offline or Hybrid
See required model status
See pipeline summary
Run
See clear log and final rescue report
```

Implement carefully. Preserve existing invariants. Make the flows obvious, safe, and honest.
