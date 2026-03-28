import os
import time
import statistics
import httpx
from groq import Groq
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

load_dotenv()

groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])
sohbet_gecmisi = {}

def obilet_ara(nereden, nereye):
    bugun = time.strftime("%Y-%m-%d")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": "https://www.obilet.com",
        "Referer": "https://www.obilet.com/"
    }

    # Önce oturum al
    session_url = "https://service.obilet.com/v2/Client/GetSession"
    session_body = {
        "DeviceSession": None,
        "Application": 1,
        "UserId": None,
        "ShowGridOffers": True
    }

    with httpx.Client(timeout=30) as client:
        try:
            session_res = client.post(session_url, json=session_body, headers=headers)
            session_data = session_res.json()
            session_id = session_data["Data"]["SessionId"]
        except:
            return []

        # Lokasyon ID bul
        loc_url = "https://service.obilet.com/v2/Location/GetLocations"
        
        nereden_res = client.post(loc_url, json={
            "DeviceSession": {"SessionId": session_id},
            "Application": 1,
            "Query": nereden
        }, headers=headers)
        
        nereye_res = client.post(loc_url, json={
            "DeviceSession": {"SessionId": session_id},
            "Application": 1,
            "Query": nereye
        }, headers=headers)

        try:
            nereden_id = nereden_res.json()["Data"][0]["Id"]
            nereye_id = nereye_res.json()["Data"][0]["Id"]
        except:
            return []

        # Sefer ara
        journey_url = "https://service.obilet.com/v2/Journey/GetBusJourneys"
        journey_body = {
            "DeviceSession": {"SessionId": session_id},
            "Application": 1,
            "DepartureId": nereden_id,
            "ArrivalId": nereye_id,
            "DepartureDate": bugun,
            "PassengerCount": 1
        }

        journey_res = client.post(journey_url, json=journey_body, headers=headers)
        
        try:
            seferler_raw = journey_res.json()["Data"]
        except:
            return []

        seferler = []
        for s in seferler_raw[:15]:
            try:
                firma = s.get("PartnerName", "?")
                kalkis = s.get("DepartureTime", "?")[:5]
                varis = s.get("ArrivalTime", "?")[:5]
                fiyat = int(s.get("OriginalPrice", 0))
                seferler.append({
                    "firma": firma,
                    "kalkis": kalkis,
                    "varis": varis,
                    "fiyat_str": f"{fiyat}₺",
                    "fiyat": fiyat
                })
            except:
                continue

        return seferler

def formatla(seferler, nereden, nereye):
    if not seferler:
        return f"❌ {nereden} → {nereye} seferi bulunamadı."

    fiyatlar = [s["fiyat"] for s in seferler]
    ortalama = statistics.mean(fiyatlar)

    mesaj = f"🚌 *{nereden.title()} → {nereye.title()} Seferleri*\n"
    mesaj += f"💡 Ortalama fiyat: {int(ortalama)}₺\n\n"

    for s in seferler:
        yildiz = "⭐ *UYGUN FİYAT* " if s["fiyat"] < ortalama else ""
        mesaj += f"{yildiz}*{s['firma']}*\n"
        mesaj += f"   🕐 {s['kalkis']} → {s['varis']} | 💰 {s['fiyat_str']}\n\n"

    return mesaj

def bilet_ara_mi(soru):
    response = groq.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "system",
                "content": """Kullanıcının mesajında bilet veya sefer araması var mı?
                Varsa şu formatta yanıt ver: EVET nereden=istanbul nereye=ankara
                Yoksa sadece şunu yaz: HAYIR
                Başka hiçbir şey yazma."""
            },
            {"role": "user", "content": soru}
        ],
        max_tokens=50
    )
    cevap = response.choices[0].message.content.strip()

    if cevap.startswith("EVET"):
        try:
            nereden = cevap.split("nereden=")[1].split()[0]
            nereye = cevap.split("nereye=")[1].split()[0]
            return nereden, nereye
        except:
            return None, None
    return None, None

async def mesaj_isle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kullanici_id = update.effective_user.id
    soru = update.message.text

    if kullanici_id not in sohbet_gecmisi:
        sohbet_gecmisi[kullanici_id] = [
            {
                "role": "system",
                "content": """Sen Türkiye'nin en iyi seyahat asistanısın. 
                Kullanıcıya seyahat önerileri yaparsın, rotalar önerirsin, 
                gezilecek yerleri anlatırsın ve otobüs bileti tavsiyesi verirsin.
                Türkçe konuş, samimi ve yardımsever ol."""
            }
        ]

    sohbet_gecmisi[kullanici_id].append({"role": "user", "content": soru})

    nereden, nereye = bilet_ara_mi(soru)

    if nereden and nereye:
        await update.message.reply_text(f"🔍 {nereden.title()} → {nereye.title()} seferleri aranıyor...")
        seferler = obilet_ara(nereden, nereye)
        bilet_mesaji = formatla(seferler, nereden, nereye)
        await update.message.reply_text(bilet_mesaji, parse_mode="Markdown")
        sohbet_gecmisi[kullanici_id].append({
            "role": "assistant",
            "content": f"{nereden} → {nereye} seferlerini listeledim."
        })
    else:
        response = groq.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=sohbet_gecmisi[kullanici_id],
            max_tokens=800
        )
        asistan_cevabi = response.choices[0].message.content
        sohbet_gecmisi[kullanici_id].append({"role": "assistant", "content": asistan_cevabi})
        await update.message.reply_text(asistan_cevabi)

app = ApplicationBuilder().token(os.getenv("TELEGRAM_TOKEN")).build()
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mesaj_isle))

print("🤖 Seyahat Asistanı Botu Başlatıldı!")
app.run_polling()