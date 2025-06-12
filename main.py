import json
import os
import uvicorn
import logging
import threading
from load_history import load_chat_history
from massage_saver import save_message
from massage_history import save_message_history
from fastapi import FastAPI
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

aclient = AsyncOpenAI(api_key=OPENAI_API_KEY)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

app = FastAPI()

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}

SYSTEM_PROMPT = (
   """
   You are a highly skilled AI assistant specialized in extracting structured information and business insights from unstructured company descriptions. Your task is to analyze a block of free-form text about a potential B2B lead (from LinkedIn, websites, or news snippets) and output a structured JSON object with clearly defined fields. 

Follow these rules carefully:

1. Always return the full JSON with all fields present, even if some values are null.
2. Extract factual data where possible and infer insights when not explicitly stated.
3. Do not hallucinate names, emails, or facts if they’re not directly mentioned or logically derivable.
4. Output only the JSON. No explanations or surrounding text.

Your output JSON should include the following fields:

###  Core Extracted Fields (direct from text):
- company_name: string | null
- location: string | null
- industry: string | null
- year_founded: integer | null
- company_age: integer | null
- contact_name: string | null
- contact_position: string | null
- contact_email: string | null
- website: string | null

###  Inferred/Generated Insight Fields:
- business_fit_score: integer [0–10] — how aligned is this company with a modern AI/automation service provider?
- summary: string — 1–2 sentences summarizing what this company does.
- is_healthcare_related: boolean — true if text suggests involvement in healthcare/healthtech.
- key_tech_focus: string | null — main technical/domain focus (e.g., “IoT logistics”, “FinTech trading”, “AI analytics”)
- recommended_outreach_tone: enum('formal', 'casual', 'friendly')

Use null where no data can be extracted or inferred. Base all inferences strictly on the input content and common business logic.

Example output:

{
  "company_name": "Acme Innovations",
  "location": "Austin, TX",
  "industry": "Cloud and IoT",
  "year_founded": 2018,
  "company_age": 6,
  "contact_name": "John Doe",
  "contact_position": "Head of Business Development",
  "contact_email": "john.doe@acmeinnovations.com",
  "website": null,
  "business_fit_score": 9,
  "summary": "Acme Innovations develops cloud-native applications and IoT solutions for logistics.",
  "is_healthcare_related": false,
  "key_tech_focus": "IoT for logistics",
  "recommended_outreach_tone": "friendly"
}  
"""
)

TONAL_SYSTEM_PROMPT = """
You are a helpful, friendly assistant for a healthcare chatbot. Your task is to respond to user questions about general healthcare topics in a way that sounds natural and human-like.

Guidelines:
- Use everyday spoken English.
- Use natural fillers like "you know", "um", "so" (but not too often).
- Minor imperfections are okay – you can rephrase yourself or use run-on sentences occasionally.
- Be warm, empathetic, and helpful.
- Never offer medical diagnosis or advice.
- Keep the tone suitable for healthcare – reassuring, calm, and conversational.
"""

TONAL_TEMPLATE = """
You are a friendly outreach assistant. Your job is to craft a short, warm, human-like message to initiate contact with a potential client company, based on the structured data below. 
Use the contact's name and summary to personalize the message. Keep the tone {recommended_outreach_tone}, sound human and natural. Don't be too formal unless tone requires it. Avoid medical advice.

DATA:
company_name: {company_name}
summary: {summary}
contact_name: {contact_name}
recommended_outreach_tone: {recommended_outreach_tone}
"""

chat_history: dict[int, list[dict[str, str]]] = {}

def build_prompt_with_system(chat_id: int, system_prompt: str, limit: int = 10) -> list[dict[str, str]]:
    user_messages = load_chat_history(chat_id, limit)
    return [{"role": "system", "content": system_prompt}] + user_messages

async def get_gpt_structured_json(user_text: str) -> dict:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_text}]
    try:
        response = await aclient.chat.completions.create(
            model="gpt-4.1-mini",
            messages=messages,
            max_tokens=700,
            temperature=0.7,
        )
        content = response.choices[0].message.content.strip()
        return json.loads(content)
    except Exception as e:
        logging.error("Error extracting structured JSON: %s", e)
        return {}

async def get_personalized_message(data: dict) -> str:
    prompt = TONAL_TEMPLATE.format(**data)
    try:
        response = await aclient.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "system", "content": prompt}],
            max_tokens=200,
            temperature=0.8,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logging.error("Error generating personalized message: %s", e)
        return "Oops, couldn't create a message. Try again later."

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = "Hey there! My name is Nik! I'm here to chat about smthng. You can type examples from Test task p.1 and get answers after JSON+tone or type /extract in start message just to get json file from ur message(PART 1) or /message to get a perdonalized medical warm message (part 2)"
    await update.message.reply_text(text)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    chat_id = update.effective_chat.id
    user_text = update.message.text
    logging.info("Message from %s: %s", chat_id, user_text)

    save_message(chat_id, "user", user_text)
    save_message_history(chat_id, "user", user_text)

    structured_data = await get_gpt_structured_json(user_text)
    if not structured_data:
        reply = "Sorry, I couldn't extract useful information. Try rewriting your message."
    else:
        reply = await get_personalized_message(structured_data)
    save_message(chat_id, "assistant", structured_data)
    save_message(chat_id, "assistant", reply)
    save_message_history(chat_id, "assistant", reply)
    await update.message.reply_text(reply)

def run_fastapi() -> None:
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")

async def extract_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    chat_id = update.effective_chat.id
    args = context.args
    if not args:
        await update.message.reply_text("Please provide a company description after /extract.")
        return

    user_text = " ".join(args)
    logging.info("Extracting from /extract: %s", user_text)

    save_message(chat_id, "user", user_text)
    save_message_history(chat_id, "user", user_text)

    extracted = await get_gpt_structured_json(user_text)

    save_message_history(chat_id, "assistant", extracted)
    if not extracted:
        await update.message.reply_text("Sorry, I couldn't extract structured data.")
    else:
        import json
        await update.message.reply_text(f"```json\n{json.dumps(extracted, indent=2)}\n```", parse_mode="Markdown")
        save_message(chat_id, "assistant", extracted)
        save_message_history(chat_id, "assistant", extracted)


async def get_personalized_message_raw(text: str) -> str:
    messages = [
        {"role": "system", "content": TONAL_SYSTEM_PROMPT},
        {"role": "user", "content": text},
    ]
    try:
        response = await aclient.chat.completions.create(
            model="gpt-4.1-mini",
            messages=messages,
            max_tokens=400,
            temperature=0.8,
        )

        return response.choices[0].message.content.strip()
    except Exception as e:
        logging.error("Error in tone reply: %s", e)
        return "Oops, I had a little hiccup – mind trying again?"

async def message_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    chat_id = update.effective_chat.id
    user_text = update.message.text.replace("/message", "").strip()
    save_message(chat_id, "user", user_text)
    save_message_history(chat_id, "user", user_text)

    logging.info("/message input from %s: %s", chat_id, user_text)

    reply = await get_personalized_message_raw(user_text)

    save_message(chat_id, "assistant", reply)
    await update.message.reply_text(reply)

def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set")

    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start_cmd))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CommandHandler("extract", extract_cmd))
    application.add_handler(CommandHandler("message", message_cmd))

    thread = threading.Thread(target=run_fastapi, daemon=True)
    thread.start()

    logging.info("Bot started")
    application.run_polling()

if __name__ == "__main__":
    main()
