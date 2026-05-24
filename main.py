import os
import httpx
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from contextlib import asynccontextmanager

from database import init_db, save_receipt, get_monthly_summary, get_all_months_summary, get_recent_receipts, get_receipt_items, get_category_summary_year
from parser import parse_receipt, answer_query

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")  # e.g. https://your-app.railway.app

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if WEBHOOK_URL:
        async with httpx.AsyncClient() as client:
            await client.post(f"{TELEGRAM_API}/setWebhook", json={"url": f"{WEBHOOK_URL}/webhook"})
    yield


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")


async def send_message(chat_id: int, text: str):
    async with httpx.AsyncClient() as client:
        await client.post(f"{TELEGRAM_API}/sendMessage", json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
        })


async def get_file_bytes(file_id: str) -> bytes:
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{TELEGRAM_API}/getFile", params={"file_id": file_id})
        file_path = r.json()["result"]["file_path"]
        r2 = await client.get(f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}")
        return r2.content


@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    message = data.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    if not chat_id:
        return {"ok": True}

    if "photo" in message:
        await send_message(chat_id, "📷 Scontrino ricevuto, lo sto analizzando...")
        photo = message["photo"][-1]
        image_bytes = await get_file_bytes(photo["file_id"])
        result = parse_receipt(image_bytes, ANTHROPIC_API_KEY)
        if not result:
            await send_message(chat_id, "❌ Non sono riuscito a leggere lo scontrino. Prova con una foto più nitida.")
            return {"ok": True}
        receipt_id = save_receipt(
            store=result.get("store", "Negozio sconosciuto"),
            date=result.get("date", datetime.now().strftime("%Y-%m-%d")),
            total=result.get("total") or 0,
            items=result.get("items", []),
            chat_id=chat_id,
        )
        store = result.get("store", "Negozio sconosciuto")
        total = result.get("total") or 0
        n_items = len(result.get("items", []))
        date = result.get("date", "")
        await send_message(
            chat_id,
            f"✅ <b>Scontrino salvato!</b>\n\n"
            f"🏪 <b>Negozio:</b> {store}\n"
            f"📅 <b>Data:</b> {date}\n"
            f"🛒 <b>Articoli:</b> {n_items}\n"
            f"💰 <b>Totale:</b> €{total:.2f}\n\n"
            f"ID: #{receipt_id}",
        )
        return {"ok": True}

    if "text" in message:
        text = message["text"].strip()
        if text.startswith("/start"):
            await send_message(
                chat_id,
                "👋 <b>Benvenuto nel bot delle spese familiari!</b>\n\n"
                "📸 Inviami la foto di uno scontrino e lo analizzo automaticamente.\n\n"
                "💬 Oppure chiedimi:\n"
                "• <i>Quanto ho speso questo mese?</i>\n"
                "• <i>Quanto ho speso questa settimana?</i>\n"
                "• <i>Mostrami le spese di maggio</i>\n"
                "• <i>Quanto ho speso in alimentari?</i>",
            )
            return {"ok": True}

        now = datetime.now()
        month_data = get_monthly_summary(now.year, now.month)
        months_data = get_all_months_summary()
        recent = get_recent_receipts(10)
        context = {
            "mese_corrente": {
                "anno": now.year,
                "mese": now.month,
                "nome_mese": now.strftime("%B %Y"),
                "totale": month_data["total"],
                "numero_scontrini": month_data["count"],
                "per_categoria": month_data["categories"],
            },
            "ultimi_12_mesi": months_data,
            "ultimi_scontrini": recent,
            "data_oggi": now.strftime("%Y-%m-%d"),
        }
        response = answer_query(text, context, ANTHROPIC_API_KEY)
        await send_message(chat_id, response)

    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()


@app.get("/api/summary")
async def api_summary():
    now = datetime.now()
    month = get_monthly_summary(now.year, now.month)
    months = get_all_months_summary()
    year_categories = get_category_summary_year(now.year)
    return {
        "current_month": month,
        "months": months,
        "year_categories": year_categories,
        "current_date": now.strftime("%Y-%m-%d"),
    }


@app.get("/api/receipts")
async def api_receipts():
    return get_recent_receipts(50)


@app.get("/api/receipts/{receipt_id}/items")
async def api_receipt_items(receipt_id: int):
    return get_receipt_items(receipt_id)


@app.get("/setup")
async def setup_webhook():
    if not WEBHOOK_URL:
        raise HTTPException(400, "WEBHOOK_URL non configurato")
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{TELEGRAM_API}/setWebhook", json={"url": f"{WEBHOOK_URL}/webhook"})
    return r.json()
