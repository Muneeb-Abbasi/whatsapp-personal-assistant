# WhatsApp Personal Assistant

A production-ready WhatsApp reminder assistant built with FastAPI, Twilio, OpenAI, SQLite, and APScheduler.

## Features

- ✅ **Create reminders** - Natural language reminder creation
- ✅ **Update reminders** - Modify existing reminders
- ✅ **Delete reminders** - Remove unwanted reminders
- ✅ **Pause/Resume reminders** - Temporarily disable reminders
- ✅ **List reminders** - View all active reminders
- ✅ **Voice messages** - Transcribe and process voice notes
- ✅ **Conditional phone calls** - Call if user doesn't respond
- ✅ **User opt-out** - Disable phone calls globally

## Architecture

```
WhatsApp Message → Twilio → FastAPI Webhook
                                  ↓
                    Audio? → OpenAI Whisper → Text
                                  ↓
                         OpenAI GPT-4o-mini
                         (Intent & Entity Extraction)
                                  ↓
                          Reminder Service
                              ↓        ↓
                          SQLite    APScheduler
                                       ↓
                              Scheduled Notification
                                       ↓
                              Follow-up Check
                                       ↓
                         No Response? → Twilio Voice Call
```

## Prerequisites

- Python 3.10+
- Twilio account with:
  - WhatsApp Sandbox or Business API
  - Phone number for voice calls (optional)
- OpenAI API key
- ngrok (for local development)

## Installation

1. **Clone and navigate to the project:**
   ```bash
   cd whatsapp_assistant
   ```

2. **Create a virtual environment:**
   ```bash
   python -m venv venv
   
   # Windows
   venv\Scripts\activate
   
   # Linux/Mac
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables:**
   ```bash
   # Copy the example file
   copy .env.example .env  # Windows
   cp .env.example .env    # Linux/Mac
   
   # Edit .env with your credentials
   ```

5. **Configure your `.env` file:**
   ```env
   # Twilio Configuration
   TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   TWILIO_AUTH_TOKEN=your_auth_token
   TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886
   TWILIO_PHONE_NUMBER=+1234567890
   
   # OpenAI Configuration
   OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
   
   # User Configuration (Your WhatsApp number)
   USER_WHATSAPP_NUMBER=whatsapp:+923001234567
   USER_PHONE_NUMBER=+923001234567
   
   # Application Settings
   DEBUG=false
   VALIDATE_TWILIO_SIGNATURE=true
   ```

## Running the Application

### Local Development

1. **Start the server:**
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

2. **Start ngrok tunnel:**
   ```bash
   ngrok http 8000
   ```

3. **Configure Twilio Webhook:**
   - Go to [Twilio Console](https://console.twilio.com)
   - Navigate to: Messaging → Try it out → Send a WhatsApp message
   - Set webhook URL to: `https://your-ngrok-url.ngrok.io/webhook/whatsapp`

### Production

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

> **Note:** Use only 1 worker due to APScheduler's in-memory job management.

## Usage Examples

### Text Messages

| Message | Action |
|---------|--------|
| `Remind me to pay electricity bill tomorrow at 9am` | Creates reminder for 9:00 AM tomorrow |
| `Remind me to call Mark before 7pm. If I don't respond, call me.` | Creates reminder with phone call follow-up |
| `Pause my wifi reminder` | Pauses the WiFi reminder |
| `Resume wifi reminder` | Resumes the paused WiFi reminder |
| `Delete Mark reminder` | Deletes the Mark reminder |
| `List my reminders` | Shows all active reminders |
| `Do not call me if I don't respond` | Disables phone calls for all reminders |

### Voice Messages

Send a voice note saying any of the above commands. The assistant will:
1. Download the audio from Twilio
2. Transcribe using OpenAI Whisper
3. Process the transcribed text
4. Reply with a text message

## Example Conversations

### Creating a Reminder

```
📱 You: Remind me to pay electricity bill tomorrow at 9am

🤖 Assistant: ✅ *Reminder created!*

📌 *Pay electricity bill*
⏰ January 02, 2026 at 09:00 AM PKT
📅 (tomorrow at 09:00 AM)
```

### Creating a Reminder with Call

```
📱 You: Remind me to schedule a call with Mark before 7pm. 
        If I don't respond, call me after 10 minutes.

🤖 Assistant: ✅ *Reminder created!*

📌 *Schedule a call with Mark*
⏰ January 01, 2026 at 07:00 PM PKT
📅 (in 3 hours)
⏳ Follow-up: 10 minutes after
📞 Will call if no response
```

### Reminder Notification

```
🤖 Assistant: ⏰ *Reminder*: Pay electricity bill

Reply to acknowledge this reminder.

📱 You: done

🤖 Assistant: 👍 Got it! Marked *Pay electricity bill* as completed.
```

### Listing Reminders

```
📱 You: List my reminders

🤖 Assistant: 📋 *Your Reminders* (2)

1. ✅ *Pay electricity bill*
   ⏰ January 02, 2026 at 09:00 AM PKT
   📅 tomorrow at 09:00 AM

2. ⏸️ *Renew WiFi subscription*
   ⏰ January 05, 2026 at 10:00 AM PKT
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | API information |
| `/health` | GET | Health check |
| `/webhook/whatsapp` | POST | Twilio WhatsApp webhook |
| `/scheduler/status` | GET | Scheduler status and pending jobs |

## Project Structure

```
app/
├── main.py                    # FastAPI application entry point
├── api/
│   └── whatsapp_webhook.py    # Twilio webhook handler
├── domain/
│   └── reminder.py            # Reminder model and schemas
├── usecases/
│   └── reminder_service.py    # Business logic
├── infrastructure/
│   ├── database.py            # SQLite setup
│   ├── scheduler.py           # APScheduler setup
│   ├── twilio_whatsapp.py     # WhatsApp messaging
│   ├── twilio_calls.py        # Voice calls
│   └── audio_handler.py       # Audio processing
├── ai/
│   ├── nlp_parser.py          # Intent detection
│   └── speech_to_text.py      # Audio transcription
├── config/
│   └── settings.py            # Environment configuration
└── utils/
    └── time.py                # PKT timezone utilities
```

## Security

- **Twilio Signature Validation**: All webhooks are validated using X-Twilio-Signature
- **Environment Variables**: Secrets stored in `.env` (never committed)
- **Idempotent Processing**: Message SID tracking prevents duplicates

## Troubleshooting

### Webhook not receiving messages
1. Verify ngrok is running and URL is correct
2. Check Twilio console for webhook errors
3. Ensure `VALIDATE_TWILIO_SIGNATURE=false` for local testing without HTTPS

### Audio transcription failing
1. Check OpenAI API key is valid
2. Verify audio format is supported (ogg, mp3, m4a, wav)
3. Check Twilio auth for media downloads

### Reminders not triggering
1. Check `/scheduler/status` endpoint for pending jobs
2. Verify timezone is correctly set to Asia/Karachi
3. Check logs for scheduler errors

## License

MIT
