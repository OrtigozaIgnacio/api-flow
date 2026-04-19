import httpx
import os

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")

async def send_message(to: str, text: str, phone_number_id: str):
    url = f"https://graph.facebook.com/v20.0/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }

    numbers_to_try = [to]
    if to.startswith("549") and len(to) == 13:
        numbers_to_try.append("54" + to[3:])

    async with httpx.AsyncClient() as client:
        for number in numbers_to_try:
            payload = {
                "messaging_product": "whatsapp",
                "to": number,
                "type": "text",
                "text": {"body": text},
            }
            try:
                response = await client.post(url, json=payload, headers=headers)
                if response.status_code == 200:
                    return
                data = response.json()
                if data.get("error", {}).get("code") == 131030 and len(numbers_to_try) > 1:
                    continue
                response.raise_for_status()
            except Exception as e:
                print(f"[SEND] ERROR: {e}")
                if number == numbers_to_try[-1]:
                    raise