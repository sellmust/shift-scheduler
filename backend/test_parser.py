import os, requests
from dotenv import load_dotenv
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL     = "https://api.groq.com/openai/v1/chat/completions"

payload = {
    "model": "llama-3.1-8b-instant",
    "messages": [
        {"role": "user", "content": 'Ekstrak jadwal dari teks ini ke JSON format {"nama": null, "availability": [{"hari": "Senin", "sesi": "Pagi"}]}. Teks: senin pagi, rabu sore'}
    ],
    "temperature": 0,
    "max_tokens": 400,
}

resp = requests.post(GROQ_URL,
    headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
    json=payload)

print(resp.json())