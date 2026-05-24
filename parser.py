import anthropic
import base64
import json
import re
from datetime import datetime

RECEIPT_PROMPT = """Analizza questo scontrino italiano ed estrai tutte le informazioni in formato JSON.
Restituisci SOLO il JSON valido, senza testo aggiuntivo, senza markdown, senza backtick.

Formato richiesto:
{{
  "store": "nome del negozio",
  "date": "YYYY-MM-DD",
  "total": 0.00,
  "items": [
    {{
      "name": "nome prodotto",
      "quantity": 1,
      "unit_price": 0.00,
      "total_price": 0.00,
      "category": "categoria"
    }}
  ]
}}

Categorie possibili: Alimentari, Bevande, Latticini, Carne/Pesce, Frutta/Verdura, Pulizia, Igiene, Altro

Regole:
- Se la data non è leggibile, usa oggi: {today}
- Se un prezzo non è chiaro, metti null
- La quantity è il numero di pezzi (default 1)
- Includi TUTTI gli articoli visibili sullo scontrino
- Il total è il totale finale pagato"""


def parse_receipt(image_bytes: bytes, api_key: str) -> dict | None:
    client = anthropic.Anthropic(api_key=api_key)
    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    today = datetime.now().strftime("%Y-%m-%d")

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": image_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": RECEIPT_PROMPT.format(today=today),
                    },
                ],
            }
        ],
    )

    text = message.content[0].text.strip()
    json_match = re.search(r"\{.*\}", text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            return None
    return None


def answer_query(question: str, context_data: dict, api_key: str) -> str:
    client = anthropic.Anthropic(api_key=api_key)

    system = """Sei un assistente per la gestione delle spese familiari.
Rispondi in italiano, in modo conciso e amichevole.
Usa i dati forniti per rispondere alla domanda dell'utente.
Formatta gli importi in euro con 2 decimali (es: €12,50).
Se i dati non sono sufficienti per rispondere, dillo chiaramente."""

    data_str = json.dumps(context_data, ensure_ascii=False, indent=2)

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        system=system,
        messages=[
            {
                "role": "user",
                "content": f"Dati disponibili:\n{data_str}\n\nDomanda: {question}",
            }
        ],
    )

    return message.content[0].text.strip()
