"""
HR AI Assistant – Cleaned FastAPI Server
Twilio ↔ OpenAI Realtime API (GPT-4o)
"""

import os
import json
import asyncio
import websockets
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, Form
from fastapi.responses import Response
from dotenv import load_dotenv
from twilio.twiml.voice_response import VoiceResponse, Connect

# -------------------------------------------------------------------
# ENV & APP SETUP
# -------------------------------------------------------------------

load_dotenv()
app = FastAPI()

OPENAI_REALTIME_API_KEY = os.getenv("OPENAI_REALTIME_API_KEY")
OPENAI_REALTIME_ENDPOINT = os.getenv(
    "OPENAI_REALTIME_ENDPOINT", "wss://api.openai.com/v1/realtime"
)
OPENAI_REALTIME_MODEL = os.getenv(
    "OPENAI_REALTIME_MODEL", "gpt-4o-realtime-preview"
)

IS_AZURE = "azure" in OPENAI_REALTIME_ENDPOINT.lower()

# -------------------------------------------------------------------
# SYSTEM PROMPT
# -------------------------------------------------------------------

SYSTEM_INSTRUCTIONS = """
You are SAVIRA, a professional HR interviewer from Kainskep Solutions.
You are conducting a live outbound telephonic screening interview.

STRICT BEHAVIOR RULES:
- Stay focused ONLY on job and interview-related conversation.
- Ask a maximum of 8 to 10 interview questions in total.
- Do NOT ask additional questions beyond these 8–10 under any condition.
- Ask ONE question at a time and wait for the candidate’s response.
- Keep responses short, clear, and professional (1–2 sentences).
- Do NOT engage in casual conversation or unrelated topics.
- If the candidate goes off-topic, politely redirect them back to the interview.
- Do NOT explain evaluation, scoring, or internal decisions.

INTERVIEW FLOW (FOLLOW STRICTLY):

STEP 1 – GREETING:
Say exactly:
"Hello, I am SAVIRA from Kainskep Solutions. Are you currently looking for a job or considering a job change?"

Wait for a clear response.

If NO:
- Say:
"Thank you for your time. Have a great day. Goodbye."
- End the conversation.

If YES:
- Proceed to STEP 2.

STEP 2 – ROLE CONFIRMATION:
Ask:
"Which role or position are you currently looking for?"

Do not proceed until the role is clearly stated.

STEP 3 – INTERVIEW QUESTIONS (8–10 TOTAL):
- Ask 8 to 10 job-relevant interview questions based on the stated role.
- These questions must naturally gather the following information where possible:
  - Full name
  - Email address
  - Current or last company name
  - Total years of experience
  - Previous salary
  - Expected salary
  - Desired role
- Do NOT ask separate questions only for data collection.
- Embed required details naturally within interview-style questions.
- If a detail is not provided, do NOT ask extra questions to collect it.
- If a candidate refuses to share any detail, mark it internally as "Not disclosed".
- Do NOT guess, assume, or overwrite previously provided information.

DATA HANDLING RULES:
- Maintain an internal structured record of the candidate’s responses.
- Preserve the first confirmed value for each field.
- Do NOT read collected data aloud during the interview.
- Do NOT summarize candidate data during the call.

STEP 4 – CLOSING:
After completing the 8–10 interview questions, say:
"Thank you for your time. Your telephonic interview is complete. Based on your responses and our scoring system, shortlisted candidates will be contacted for the next round. Take care and goodbye."

POST-CLOSING BEHAVIOR:
- After the closing statement, do not continue the conversation.
- If the candidate speaks again, repeat the closing message once and stop responding.

VOICE STYLE:
- Calm, confident, human, and professional.
- Speak like a real HR interviewer, not a chatbot.
"""

# -------------------------------------------------------------------
# TWILIO VOICE ENDPOINT
# -------------------------------------------------------------------

@app.post("/voice")
async def voice(request: Request):
    print("📞 Incoming call")

    host = request.headers.get("host", request.url.hostname)
    ws_url = f"wss://{host}/media-stream"

    response = VoiceResponse()
    connect = Connect()
    connect.stream(url=ws_url)
    response.append(connect)

    return Response(str(response), media_type="text/xml")

      
@app.post("/call-status")
async def call_status(CallStatus: str = Form(None), CallSid: str = Form(None)):
    print(f"📊 Call Status: {CallStatus} | SID: {CallSid}")
    return {"status": "ok"}


# -------------------------------------------------------------------
# OPENAI SESSION HELPERS
# -------------------------------------------------------------------

def build_openai_connection():
    if IS_AZURE:
        return (
            OPENAI_REALTIME_ENDPOINT.replace("https://", "wss://"),
            {"api-key": OPENAI_REALTIME_API_KEY},
        )

    return (
        f"{OPENAI_REALTIME_ENDPOINT}?model={OPENAI_REALTIME_MODEL}",
        {
            "Authorization": f"Bearer {OPENAI_REALTIME_API_KEY}",
            "OpenAI-Beta": "realtime=v1",
        },
    )


def session_config():
    return {
        "type": "session.update",
        "session": {
            "modalities": ["text", "audio"],
            "instructions": SYSTEM_INSTRUCTIONS,
            "voice": "alloy",
            "input_audio_format": "g711_ulaw",
            "output_audio_format": "g711_ulaw",
            "input_audio_transcription": {"model": "whisper-1"},
            "turn_detection": {
                "type": "server_vad",
                "threshold": 0.5,
                "prefix_padding_ms": 300,
                "silence_duration_ms": 700,
            },
        },
    }


def greeting_message():
    return {
        "type": "response.create",
        "response": {
            "modalities": ["text", "audio"],
            "instructions": (
                "Hello, I am SAVIRA from Kainskep Solutions. "
                "Are you currently looking for a job or considering a job change?"
            ),
        },
    }


def extraction_prompt():
    return {
        "type": "response.create",
        "response": {
            "modalities": ["text"],
            "instructions": (
                "Extract candidate information from the conversation. "
                "Return STRICT JSON only:\n"
                "{"
                "\"full_name\": string|null, "
                "\"email\": string|null, "
                "\"role\": string|null, "
                "\"last_company_name\": string|null, "
                "\"experience\": string|null, "
                "\"previous_salary\": string|null, "
                "\"expected_salary\": string|null"
                "}"
            ),
        },
    }


# -------------------------------------------------------------------
# MEDIA STREAM (CORE LOGIC)
# -------------------------------------------------------------------

@app.websocket("/media-stream")
async def media_stream(websocket: WebSocket):
    await websocket.accept()
    print("🔌 Twilio WebSocket connected")

    if not OPENAI_REALTIME_API_KEY:
        await websocket.close(code=1008, reason="Missing OpenAI API key")
        return

    stream_sid = None
    extraction_done = False

    url, headers = build_openai_connection()
    openai_ws = await websockets.connect(url, extra_headers=headers, ping_interval=None)

    await openai_ws.send(json.dumps(session_config()))
    await openai_ws.send(json.dumps(greeting_message()))

    # ---------------- Twilio → OpenAI ----------------

    async def twilio_to_openai():
        nonlocal stream_sid
        try:
            while True:
                msg = json.loads(await websocket.receive_text())

                if msg["event"] == "start":
                    stream_sid = msg["start"]["streamSid"]
                    print(f"📡 Stream started: {stream_sid}")

                elif msg["event"] == "media":
                    await openai_ws.send(
                        json.dumps(
                            {
                                "type": "input_audio_buffer.append",
                                "audio": msg["media"]["payload"],
                            }
                        )
                    )

                elif msg["event"] == "stop":
                    await openai_ws.send(
                        json.dumps({"type": "input_audio_buffer.commit"})
                    )
                    break

        except WebSocketDisconnect:
            print("🔌 Twilio disconnected")

    # ---------------- OpenAI → Twilio ----------------

    async def openai_to_twilio():
        nonlocal extraction_done
        conversation_turns = 0

        while True:
            event = json.loads(await openai_ws.recv())
            etype = event.get("type")

            if etype == "response.audio.delta" and stream_sid:
                await websocket.send_text(
                    json.dumps(
                        {
                            "event": "media",
                            "streamSid": stream_sid,
                            "media": {"payload": event["delta"]},
                        }
                    )
                )

            elif etype == "conversation.item.input_audio_transcription.completed":
                user_text = event.get("transcript", "")
                print("👤 User:", user_text)
                conversation_turns += 1
                
                # Trigger extraction after many turns (fallback)
                if not extraction_done and conversation_turns > 15:
                    print("🔍 Auto-triggering extraction after 15+ turns...")
                    extraction_done = True
                    await openai_ws.send(json.dumps(extraction_prompt()))

            elif etype == "response.audio_transcript.done":
                text = event.get("transcript", "")
                print("🤖 AI:", text)

                # Trigger extraction on multiple closing phrases
                closing_phrases = [
                    "interview is complete",
                    "thank you for your time", 
                    "take care and goodbye",
                    "goodbye",
                    "telephonic interview is complete"
                ]
                
                if not extraction_done and any(phrase in text.lower() for phrase in closing_phrases):
                    print("🔍 Triggering data extraction...")
                    extraction_done = True
                    await openai_ws.send(json.dumps(extraction_prompt()))

            elif etype == "response.output_text.done":
                extracted_text = event.get("text", "")
                if extraction_done and extracted_text:
                    print("✅ EXTRACTION RESPONSE:", extracted_text)
                    
                    # Try to parse as JSON and display formatted
                    try:
                        import re
                        json_match = re.search(r'\{.*\}', extracted_text, re.DOTALL)
                        if json_match:
                            candidate_data = json.loads(json_match.group())
                            print("\n" + "="*50)
                            print("📋 EXTRACTED CANDIDATE DATA:")
                            print("="*50)
                            for key, value in candidate_data.items():
                                print(f"{key.replace('_', ' ').title()}: {value}")
                            print("="*50 + "\n")
                        else:
                            print("⚠️ No JSON found in extraction response")
                    except json.JSONDecodeError as e:
                        print(f"⚠️ Failed to parse extraction JSON: {e}")
                    except Exception as e:
                        print(f"⚠️ Error processing extraction: {e}")

            elif etype == "response.text.done":
                # Additional handler for text responses
                text_content = event.get("text", "")
                if extraction_done and text_content:
                    print("� TEXT EXTRACTION:", text_content)

    await asyncio.gather(twilio_to_openai(), openai_to_twilio())


# -------------------------------------------------------------------
# MANUAL EXTRACTION ENDPOINT (FOR TESTING)
# -------------------------------------------------------------------

@app.post("/extract-data")
async def manual_extract():
    """Manual endpoint to trigger data extraction for testing"""
    print("🔍 Manual extraction triggered via API")
    return {"message": "Extraction trigger sent (if call is active)"}


# -------------------------------------------------------------------
# HEALTH
# -------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == '__main__':
    import uvicorn
    
    port = int(os.getenv('SERVER_PORT', 5000))
    print("\n" + "=" * 60)
    print("   HR AI ASSISTANT - GPT-4o REALTIME API")
    print("=" * 60)
    print(f"\n🚀 Server running on port {port}")
    print(f"🤖 Using: {'Azure OpenAI' if IS_AZURE else 'OpenAI'} Realtime")
    print(f"📦 Model: {OPENAI_REALTIME_MODEL}")
    print("⚠️  Remember to expose this server using ngrok")
    print("   Example: ngrok http 5000")
    print("\n" + "=" * 60 + "\n")
    
    uvicorn.run(app, host='0.0.0.0', port=port)