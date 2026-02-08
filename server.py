"""
HR AI Assistant - FastAPI Server with GPT-4o Realtime API
This server handles incoming Twilio calls and connects them to OpenAI Realtime API
"""

import os
import json
import base64
import asyncio
import websockets
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, Form
from fastapi.responses import Response
from dotenv import load_dotenv
from twilio.twiml.voice_response import VoiceResponse, Connect

# Load environment variables
load_dotenv()

# Create FastAPI app
app = FastAPI()

# OpenAI Realtime API configuration
OPENAI_REALTIME_API_KEY = os.getenv('OPENAI_REALTIME_API_KEY')
OPENAI_REALTIME_ENDPOINT = os.getenv('OPENAI_REALTIME_ENDPOINT', 'wss://api.openai.com/v1/realtime')
OPENAI_REALTIME_MODEL = os.getenv('OPENAI_REALTIME_MODEL', 'gpt-4o-realtime-preview')

# Detect if using Azure or OpenAI
IS_AZURE = 'azure' in OPENAI_REALTIME_ENDPOINT.lower() or 'cognitiveservices' in OPENAI_REALTIME_ENDPOINT.lower()

# System instructions for the AI
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

@app.post('/voice')
async def voice(request: Request):
    """
    This endpoint is called when Twilio connects the call
    It sets up the AI voice stream
    """
    print("📞 Incoming call received!")
    print(f"🔍 Request host: {request.url.hostname}")
    print(f"🔍 Request headers: {dict(request.headers)}")
    
    # Get the correct host from request (works with ngrok)
    host = request.headers.get('host', request.url.hostname)
    websocket_url = f"wss://{host}/media-stream"
    
    print(f"🔗 WebSocket URL: {websocket_url}")
    
    # Create TwiML response
    response = VoiceResponse()
    
    # Add a brief greeting (helps with trial account connection)
    # response.say(
    #     "Hello! Connecting you to the AI assistant.",
    #     voice='Polly.Joanna'
    # )
    
    # Small pause to ensure connection is stable
    # response.pause(length=2)
    
    # Connect to WebSocket for real-time conversation
    connect = Connect()
    connect.stream(url=websocket_url)
    response.append(connect)
    
    print(f"📤 Sending TwiML response:\n{str(response)}")
    
    return Response(content=str(response), media_type='text/xml')

@app.post('/call-status')
async def call_status(CallStatus: str = Form(None), CallSid: str = Form(None)):
    """
    This endpoint receives call status updates from Twilio
    """
    print(f"📊 Call Status Update: {CallStatus} (SID: {CallSid})")
    
    if CallStatus == 'completed':
        print("✅ Call ended successfully!")
    
    return {'status': 'ok'}

@app.websocket('/media-stream')
async def media_stream(websocket: WebSocket):
    """
    WebSocket endpoint that bridges Twilio and OpenAI Realtime API
    """
    await websocket.accept()
    print("🔌 Twilio WebSocket connected!")
    
    # Check if OpenAI credentials are configured
    if not OPENAI_REALTIME_API_KEY or OPENAI_REALTIME_API_KEY == "your-openai-realtime-api-key-here":
        print("❌ ERROR: OPENAI_REALTIME_API_KEY not configured in .env!")
        print("⚠️  Please update .env with your OpenAI Realtime API key")
        await websocket.close(code=1008, reason="OpenAI API key not configured")
        return
    
    stream_sid = None
    openai_ws = None

    interview_completed = False
    extraction_requested = False
    
    try:
        # Connect to OpenAI Realtime API
        print("🔗 Connecting to OpenAI Realtime API...")
        print(f"🔍 Endpoint: {OPENAI_REALTIME_ENDPOINT}")
        print(f"🔍 Model: {OPENAI_REALTIME_MODEL}")
        print(f"🔍 Using: {'Azure' if IS_AZURE else 'OpenAI'}")
        
        # Build WebSocket URL and headers based on provider
        if IS_AZURE:
            # Azure OpenAI - endpoint already includes full URL with params
            realtime_url = OPENAI_REALTIME_ENDPOINT.replace('https://', 'wss://')
            headers = {
                "api-key": OPENAI_REALTIME_API_KEY
            }
        else:
            # OpenAI direct
            realtime_url = f"{OPENAI_REALTIME_ENDPOINT}?model={OPENAI_REALTIME_MODEL}"
            headers = {
                "Authorization": f"Bearer {OPENAI_REALTIME_API_KEY}",
                "OpenAI-Beta": "realtime=v1"
            }
        
        print(f"🔗 Connecting to: {realtime_url}")
        
        openai_ws = await websockets.connect(
            realtime_url,
            extra_headers=headers,
            ping_interval=None,  # Disable automatic ping
            ping_timeout=None
        )
        print("✅ Connected to OpenAI Realtime API!")
        
        # Configure the session
        session_config = {
            "type": "session.update",
            "session": {
                "modalities": ["text", "audio"],
                "instructions": SYSTEM_INSTRUCTIONS,
                "voice": "alloy",
                "input_audio_format": "g711_ulaw",  # Changed to match Twilio's format
                "output_audio_format": "g711_ulaw",  # Changed to match Twilio's format
                "input_audio_transcription": {
                    "model": "whisper-1"
                },
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 700
                },
                "temperature": 0.8
            }
        }
        await openai_ws.send(json.dumps(session_config))
        print("⚙️ Session configured with g711_ulaw audio format")
        
        # Send initial greeting
        greeting_message = {
            "type": "response.create",
            "response": {
                "modalities": ["text", "audio"],
                "instructions": ("Hello, I am AIRA from Kainskep Solutions. "
            "Are you currently looking for a job or considering a job change?")
            }
        }

        

        await openai_ws.send(json.dumps(greeting_message))
        print("👋 Sent greeting request to AI") 
        
        # Create tasks for bidirectional communication
        async def twilio_to_openai():
            """Forward audio from Twilio to OpenAI"""
            nonlocal stream_sid
            audio_count = 0
            try:
                while True:
                    try:
                        message = await websocket.receive_text()
                        data = json.loads(message)
                        
                        if data['event'] == 'start':
                            stream_sid = data['start']['streamSid']
                            print(f"📡 Stream started: {stream_sid}")
                        
                        elif data['event'] == 'media':
                            # Get audio from Twilio (mulaw, base64)
                            audio_payload = data['media']['payload']
                            
                            # Send directly to OpenAI (no conversion needed with g711_ulaw)
                            audio_message = {
                                "type": "input_audio_buffer.append",
                                "audio": audio_payload  # Send as-is
                            }
                            await openai_ws.send(json.dumps(audio_message))
                            
                            audio_count += 1
                            if audio_count % 100 == 0:
                                print(f"🎤 Received {audio_count} audio packets from caller")
                        
                        elif data['event'] == 'stop':
                            print("🛑 Stream stopped by Twilio")

                            await openai_ws.send(json.dumps({
                                "type": "input_audio_buffer.commit"
                            }))

                            break
                    
                    except WebSocketDisconnect:
                        print("🔌 Twilio disconnected")
                        break
                    except Exception as e:
                        print(f"⚠️ Error receiving from Twilio: {str(e)}")
                        break
                        
            except Exception as e:
                print(f"❌ Error in Twilio→OpenAI: {str(e)}")
        
        async def openai_to_twilio():
            nonlocal interview_completed, extraction_requested
            extraction_triggered = False
            try:
                while True:
                    try:
                        message = await openai_ws.recv()
                        response = json.loads(message)
                        
                        # Handle different OpenAI event types
                        if response['type'] == 'session.created':
                            print("✅ OpenAI session created")
                        
                        elif response['type'] == 'session.updated':
                            print("✅ OpenAI session updated")
                        
                        elif response['type'] == 'input_audio_buffer.speech_started':
                            print("🎤 User started speaking")
                        
                        elif response['type'] == 'input_audio_buffer.speech_stopped':
                            print("🎤 User stopped speaking")
                        
                        elif response['type'] == 'input_audio_buffer.committed':
                            print("✅ Audio buffer committed")
                        
                        elif response['type'] == 'response.created':
                            print("🤖 AI is generating response...")
                        
                        elif response['type'] == 'response.audio.delta':
                            # Audio response from OpenAI (already in g711_ulaw format)
                            if stream_sid:
                                audio_delta = response['delta']
                                
                                # Send directly to Twilio (no conversion needed)
                                media_message = {
                                    "event": "media",
                                    "streamSid": stream_sid,
                                    "media": {
                                        "payload": audio_delta
                                    }
                                }
                                await websocket.send_text(json.dumps(media_message))
                        
                        elif response['type'] == 'response.audio.done':
                            print("✅ AI finished speaking")
                            
                        
                        elif response['type'] == 'response.audio_transcript.done':
                            transcript = response.get('transcript', '')
                            print(f"🤖 AI said: {transcript}")

                            if (
                                    not extraction_requested
                                    and any(phrase in transcript.lower() for phrase in [
                                        "interview is complete",
                                        "interview is done",
                                        "thank you for your time"
                                    ])
                                ):
                                    print("🧠 Interview completion detected — starting extraction")

                                    extraction_requested = True
                                    interview_completed = True

                                    final_extraction = {
                                        "type": "response.create",
                                        "response": {
                                            "modalities": ["text"],
                                            "instructions": (
                                                "Extract candidate information from the full conversation so far. "
                                                "Return STRICT JSON ONLY with the following keys:\n"
                                                "{"
                                                "\"full_name\": string or null, "
                                                "\"email\": string or null, "
                                                "\"role\": string or null, "
                                                "\"last_company_name\": string or null, "
                                                "\"experience\": string or null, "
                                                "\"previous_salary\": string or null, "
                                                "\"expected_salary\": string or null"
                                                "}"
                                            )
                                        }
                                    }

                                    await openai_ws.send(json.dumps(final_extraction))

                        
                        elif response['type'] == 'conversation.item.input_audio_transcription.completed':
                            transcript = response.get('transcript', '')
                            print(f"👤 User said: {transcript}")
                        
                        elif response['type'] == 'error':
                            error_info = response.get('error', {})
                            print(f"❌ OpenAI error: {error_info}")

                        elif response['type'] == 'response.output_text.delta':
                            print("📄 Extraction chunk:", response['delta'])

                        elif response['type'] == 'response.output_text.done':
                            extracted_json = response.get('text', '')
                            print("✅ FINAL CANDIDATE DATA:", extracted_json)
                    
                    except websockets.exceptions.ConnectionClosed:
                        print("🔌 OpenAI connection closed")
                        break
                    except Exception as e:
                        print(f"⚠️ Error receiving from OpenAI: {str(e)}")
                        break
                        
            except Exception as e:
                print(f"❌ Error in OpenAI→Twilio: {str(e)}")
        
        # Run both tasks concurrently
        await asyncio.gather(
            twilio_to_openai(),
            openai_to_twilio()
        )
        
    except Exception as e:
        print(f"❌ WebSocket error: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        if openai_ws:
            await openai_ws.close()
        print("🔌 Connections closed")


@app.get('/health')
async def health():
    """
    Health check endpoint
    """
    return {'status': 'healthy', 'service': 'HR AI Assistant'}

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
