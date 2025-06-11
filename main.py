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
    "You are a warm, friendly, and supportive virtual assistant specializing in general healthcare information. "
    "Your role is to provide non-diagnostic, easy-to-understand guidance related to healthcare services, common procedures, wellness tips, and navigating medical systems. "
    "You are not a medical professional, and you must never offer medical diagnoses, treatment advice, or comment on symptoms. "

    "Your tone should always be human-like, conversational, and empathetic — similar to how a kind clinic receptionist or nurse might speak. "
    "Use casual, everyday language. It's okay to include natural human elements such as verbal fillers ('uh', 'you know', 'so'), slight run-on sentences, or rephrased thoughts. "

    "If a user asks something too specific, sensitive, or medical, kindly redirect them by reminding that you're just here to help with general information and that they should consult a licensed medical provider. "

    "Always keep responses short, natural, and emotionally aware. Avoid robotic, overly polished language. Focus on connection, clarity, and helpfulness. "

    "Example tone:"
    "- 'So, uh, if you're just checking how to schedule something — I can totally help with that.'\n"
    "- 'Hmm, you know, I’m not a doctor or anything, but I can definitely explain how that usually works.'\n"

    "Do not use clinical or technical jargon unless you’re explaining it in a friendly, simple way. "
    "Above all, be kind, approachable, and present in the conversation."
)

chat_history: dict[int, list[dict[str, str]]] = {}

async def get_gpt_reply(chat_id: int, user_text: str) -> str:
    history = chat_history.setdefault(chat_id, [])
    history.append({"role": "user", "content": user_text})
    messages = build_prompt_with_system(chat_id, SYSTEM_PROMPT)
    try:
        logging.info("Requesting GPT-4 for chat_id %s", chat_id)
        response = await aclient.chat.completions.create(
        model="gpt-4.1-mini",
        messages=messages,
        max_tokens=500,
        temperature=0.7)
        answer = response.choices[0].message.content.strip()
        history.append({"role": "assistant", "content": answer})
        return answer
    except Exception as e:
        logging.error("OpenAI API error: %s", e)
        return (
            "Uh, I'm having a little trouble thinking right now. "
            "Could you, you know, try again in a bit?"
        )

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command."""
    text = (
        "Hey there! Me name is Nik! I'm here to chat about our clinic and to provide neeeded information. "
        "I can't give medical advice or diagnoses, but I'll do my best to help out!"
    )
    await update.message.reply_text(text)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming user messages."""
    if not update.message:
        return
    chat_id = update.effective_chat.id
    user_text = update.message.text
    logging.info("Message from %s: %s", chat_id, user_text)
    # medical_words = ["diagnose", "prescribe", "treatment", "medication", "symptom"]
    """if any(w in user_text.lower() for w in medical_words):
        warning = (
            "Just so you know, I can't offer medical advice or diagnoses. "
            "Let's keep things general, okay?"
        )
        await update.message.reply_text(warning)"""
    save_message(chat_id, "user", user_text)
    save_message_history(chat_id, "user", user_text)
    reply = await get_gpt_reply(chat_id, user_text)
    save_message(chat_id, "assistant", reply)
    save_message_history(chat_id, "assistant", reply)
    await update.message.reply_text(reply)


def run_fastapi() -> None:
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")


def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set")

    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start_cmd))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    thread = threading.Thread(target=run_fastapi, daemon=True)
    thread.start()

    logging.info("Bot started")
    application.run_polling()

def build_prompt_with_system(chat_id: int, system_prompt: str, limit: int = 10) -> list[dict[str, str]]:
    user_messages = load_chat_history(chat_id, limit)
    return [{"role": "system", "content": system_prompt}] + user_messages

if __name__ == "__main__":
    main()