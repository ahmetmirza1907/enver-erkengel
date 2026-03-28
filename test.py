import requests
import os
from dotenv import load_dotenv

load_dotenv()

url = "https://google.serper.dev/search"

payload = {
    "q": "Istanbul to London flights 2026-05-01",
    "gl": "tr",
    "hl": "tr"
}

headers = {
    "X-API-KEY": os.getenv("SERPER_API_KEY"),
    "Content-Type": "application/json"
}

response = requests.post(url, headers=headers, json=payload)
print(response.json())