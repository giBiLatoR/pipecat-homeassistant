# Gemini Live w Home Assistant

Ta instrukcja pokazuje konfigurację Pipecat Assist z Google Gemini Live oraz
test w Home Assistant Assist. W praktyce są dwa tory testu:

- Home Assistant Assist / Conversation: tekstowy agent HA wysyła prompt do
  Pipecat Assist. Dla Gemini używany jest tekstowy model Gemini przez endpoint
  OpenAI-compatible Google, a narzędzia domu idą przez HA MCP.
- Realtime audio: Gemini Live działa przez Pipecat SmallWebRTC, czyli przez
  Pipecat ESP32 albo innego klienta SmallWebRTC. To jest właściwy test
  speech-to-speech.

## Wymagania

- Pipecat Assist w wersji 0.1.3 lub nowszej.
- Home Assistant z włączoną integracją Model Context Protocol Server.
- Klucz API z Google AI Studio z dostępem do Live API.
- Zainstalowana custom integration `custom_components/pipecat_assist`, jeśli
  chcesz testować przez standardowego agenta Home Assistant Assist.

Google opisuje Live API jako niskolatencyjny interfejs voice/vision działający
przez WebSocket. Pipecat udostępnia do tego `GeminiLiveLLMService`, a wymagany
pakiet to `pipecat-ai[google]`.

## Konfiguracja dodatku

1. Zaktualizuj i uruchom dodatek **Pipecat Assist**.
2. W Home Assistant włącz integrację **Model Context Protocol Server**.
3. Otwórz panel dodatku Pipecat Assist.
4. W zakładce **Runtime** sprawdź sekcję **Home Assistant**:
   - `MCP URL`: zostaw domyślne `http://supervisor/core/api/mcp`, o ile nie
     używasz niestandardowej instalacji.
   - `Access token`: zostaw puste, jeśli działa token Supervisora. Jeśli
     `Check MCP` zwraca błąd autoryzacji, wklej long-lived access token HA.
   - Kliknij **Check MCP**. Poprawny wynik powinien pokazać liczbę narzędzi.
5. W zakładce **Integrations** wybierz **Google Gemini**:
   - `API key`: klucz z Google AI Studio.
   - `Default model`: `gemini-3.5-flash` dla testów tekstowych HA Assist.
   - `Realtime model`: `models/gemini-3.1-flash-live-preview`.
   - `Voice`: `Charon` albo inny głos Gemini Live, np. `Puck`.
6. W zakładce **Pipelines** wybierz szablon **Gemini Live**.
7. Ustaw:
   - `Language`: `pl-PL`, jeśli asystent ma mówić po polsku.
   - `MCP tools`: włączone.
   - `Instructions`: krótka instrukcja roli, np. żeby sterować domem tylko po
     jednoznacznym poleceniu i nie zmyślać stanu urządzeń.
8. Kliknij **Save**.

## Test w Home Assistant Assist

Ten test sprawdza integrację z HA Assist, wybór flow i sterowanie domem przez
MCP. Nie jest to test strumieniowego Gemini Live audio.

1. Skopiuj `custom_components/pipecat_assist` do
   `/config/custom_components/pipecat_assist` i zrestartuj Home Assistant, jeśli
   integracja nie jest jeszcze zainstalowana.
2. Wejdź w **Settings > Devices & services > Add integration** i dodaj
   **Pipecat Assist**.
3. Ustaw:
   - `Add-on URL`: zwykle `http://127.0.0.1:7860`. Jeśli HA Core nie widzi
     loopback dodatku, użyj adresu LAN Home Assistanta.
   - `Bearer token`: zostaw puste, chyba że dodasz własną ochronę endpointów.
   - `Flow ID`: zostaw puste, żeby używać aktualnie wybranego flow z panelu,
     albo wpisz ID flow z inspektora pipeline.
4. Wejdź w **Settings > Voice assistants**, wybierz swojego asystenta i ustaw
   conversation agent na **Pipecat Realtime**.
5. W panelu Assist wpisz testy:
   - `Jakie urządzenia są dostępne w salonie?`
   - `Włącz lampę w salonie.`
   - `Ustaw jasność lampy w salonie na 30 procent.`
6. W logach dodatku sprawdź, czy pojawia się połączenie z HA MCP i czy Gemini
   odpowiada bez błędu modelu lub autoryzacji.

## Test Gemini Live audio

1. W panelu Pipecat Assist przejdź do **Runtime > Satellite**.
2. Ustaw `Public host` na adres LAN Home Assistanta, np. `192.168.1.20`.
3. Skopiuj `Offer URL`.
4. Skonfiguruj Pipecat ESP32 albo innego klienta SmallWebRTC:

```bash
export PIPECAT_SMALLWEBRTC_URL="http://<ha-lan-ip>:7860/api/offer?token=<satellite-secret>"
```

5. Uruchom satelitę i powiedz:
   - `Włącz lampę w salonie.`
   - `Czy brama garażowa jest otwarta?`

Jeśli MCP działa, Gemini Live powinien wykonać polecenia przez narzędzia Home
Assistant i odpowiedzieć głosem.

## Najczęstsze problemy

- `Missing module: google.genai`: obraz dodatku jest starszy niż 0.1.3.
- Błąd `model not found`: sprawdź dostęp Live API w Google AI Studio. Możesz też
  przetestować model `models/gemini-2.5-flash-native-audio-preview-12-2025`.
- Błąd MCP/401: wklej long-lived access token w **Runtime > Access token**.
- Brak odpowiedzi w HA Assist: upewnij się, że custom integration wskazuje na
  `http://127.0.0.1:7860` albo poprawny adres LAN.
- Głos `marin` nie działa z Gemini: ustaw voice integracji Gemini na `Charon`
  lub `Puck`.

## Źródła

- Pipecat Gemini Live: https://docs.pipecat.ai/api-reference/server/services/s2s/gemini-live
- Google Gemini Live API: https://ai.google.dev/gemini-api/docs/live-api
- Gemini 3.1 Flash Live model: https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-live-preview
- Gemini OpenAI-compatible API: https://ai.google.dev/gemini-api/docs/openai
- Home Assistant MCP Server: https://www.home-assistant.io/integrations/mcp_server/
