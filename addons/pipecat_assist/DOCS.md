# Pipecat Assist Documentation

## Requirements

- Home Assistant with the Model Context Protocol Server integration enabled.
- An API key for the realtime model provider.
- A reachable LAN IP for Home Assistant if ESP32 satellites will connect.

## Configuration

Most settings live in the Pipecat Assist web UI, not in Home Assistant add-on
options.

`runner_port`
: Pipecat runner port. Keep the default unless you also know how Home
Assistant ingress and direct clients reach the add-on.

`log_level`
: Application log level.

## Web UI

`Assistant`
: Start or stop the browser voice test for the active pipeline. The same active
pipeline is used by browser tests, ESP32 satellites, and the add-on runner.

`Pipelines`
: Add, duplicate, delete, and open complete Pipecat runtime profiles. Opening a
pipeline does not make it active; use **Set active** in the pipeline detail view
and save. After opening a pipeline, edit its colored steps from the canvas.
Pipecat Flow can be added only to composed realtime pipelines; speech-to-speech
profiles show it as unavailable.

`Pipecat Flow`
: For composed realtime pipelines, open the nested Flow view to edit a visual
Pipecat Flow stored in the same schema as the Pipecat Flows Editor. The view
includes filtered examples such as Minimal, Food Ordering, and Home Pizza via
MCP. The default Flow remains pass-through until enabled.

`Integrations`
: Configure cloud providers and local AI endpoints, including Gemini, OpenAI,
Soniox, Deepgram, Cartesia, Gradium, Speechmatics, AWS, ElevenLabs, Google
Cloud TTS, Azure/OpenAI-compatible APIs, Ollama, local runtimes, and Home
Assistant MCP. Home Assistant MCP shows Automatic, Manual, or Error state and
contains the MCP test/reset controls.

`Runtime`
: Enable audio debug captures and inspect recent Home Assistant MCP calls made
by the assistant.

### Home Assistant MCP

In a normal Home Assistant add-on install, Pipecat Assist uses the Supervisor
token provided by Home Assistant (`homeassistant_api: true`) to reach
`/api/mcp`. Open **Integrations > Home Assistant MCP** and select **Test MCP**.

Select **Automatic defaults** to clear a custom MCP URL or saved access token
and return to the Supervisor-backed defaults. The manual access-token field is
only for custom deployments where the Supervisor token is not available or a
custom MCP URL is used.

### Audio debug captures

Open **Runtime**, enable **Record audio in/out**, save, and run a
voice test or satellite session. The add-on stores separate input and output
WAV files under `/data/audio-debug` and shows download links in the Runtime
panel. Clear the captures after troubleshooting if they include private audio.

### Home Assistant MCP call history

Open **Runtime > Home Assistant actions** to inspect the recent MCP tools called
by the assistant. The history is in-memory, capped to recent calls, and intended
for debugging what the assistant attempted to do in Home Assistant.

## Default Gemini Live setup

Gemini Live is the first-run speech-to-speech pipeline. It receives audio from
SmallWebRTC and returns audio directly, while Home Assistant device control is
handled through MCP tools.

1. In Home Assistant, enable **Model Context Protocol Server**.
2. Start Pipecat Assist and open the web UI.
3. Open **Integrations > Home Assistant MCP** and select **Test MCP**. A
   healthy result shows the number of available tools. In a normal add-on
   install this uses the Supervisor token automatically.
4. Open **Integrations > Google Gemini**:
   - Paste a Google AI Studio API key.
   - Keep `models/gemini-3.1-flash-live-preview` as the realtime model.
   - Keep `gemini-3.5-flash` as the text model for Home Assistant Assist text
     tests.
   - Use a Gemini Live voice such as `Charon` or `Puck`.
5. Open **Pipelines**, then open **Gemini Live Home Assistant**.
6. Set `Language` if needed, for example `en-US` or `pl-PL`.
7. Keep the default instructions or adapt them to the household.
8. Save the pipeline.

### Browser voice test

Open **Assistant**, select the Gemini Live pipeline, and choose **Start voice
test**. Allow microphone access, wait for **Connected**, then try:

- `What devices are available in the living room?`
- `Turn on the living room lamp.`
- `Set the living room lamp brightness to 30 percent.`

If the browser cannot access the microphone, open Home Assistant over HTTPS or
from a trusted local origin. If WebRTC connects but the assistant hears the
wrong text, use **Runtime > Record audio in/out** and inspect the captured WAV
files.

### Home Assistant Assist text test

This verifies the custom conversation entity, selected pipeline, and MCP tools.
It is not a streaming Gemini Live audio test.

1. Copy or install `custom_components/pipecat_assist` into Home Assistant.
2. Restart Home Assistant if the integration is not already available.
3. Add **Pipecat Assist** from **Settings > Devices & services**.
4. Set the add-on URL to `http://127.0.0.1:7860`, or use the Home Assistant LAN
   URL if Core cannot reach loopback.
5. Leave the bearer token empty unless you add your own endpoint protection.
6. In **Settings > Voice assistants**, select **Pipecat Realtime** as the
   conversation agent.
7. Type a Home Assistant request in Assist and check the add-on logs for MCP
   tool calls and model errors.

### Gemini troubleshooting

- `Missing module: google.genai`: the add-on image is too old.
- `model not found`: check Gemini Live access in Google AI Studio and the
  realtime model value in **Integrations > Google Gemini**.
- MCP or `401`: open **Integrations > Home Assistant MCP**, select
  **Automatic defaults**, restart the add-on, then select **Test MCP**.
- Voice `marin` does not work with Gemini: set the Gemini voice to `Charon` or
  another Gemini Live voice.
- Browser voice test has no microphone: use HTTPS or a trusted local origin.

## Pipecat ESP32

Build the ESP32 firmware with:

```bash
export PIPECAT_SMALLWEBRTC_URL="http://<ha-lan-ip>:7860/api/offer?token=<satellite-secret>"
```

Pipecat Assist starts the SmallWebRTC runner with ESP32 compatibility enabled.
The ESP32 satellite uses the active pipeline selected in **Pipelines**, so the
same model, instructions, greeting, MCP tools, and Pipecat Flow settings apply
to browser tests and satellites. The direct ESP32 authentication path will move
to the standard Home Assistant token flow as the ESPHome integration work lands.

## Home Assistant Conversation entity

Copy or install `custom_components/pipecat_assist` from this repository, then
add the integration in Home Assistant. Set the add-on URL to
`http://127.0.0.1:7860` or the Home Assistant LAN URL if the integration cannot
reach loopback in your installation.

## Branding assets

Home Assistant uses `icon.png` and `logo.png` from this add-on directory in the
Supervisor app listing. Home Assistant 2026.3 and newer also read the local
integration brand files from `custom_components/pipecat_assist/brand`.
