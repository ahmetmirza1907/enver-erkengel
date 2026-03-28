import time
import statistics
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from groq import Groq
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

load_dotenv()

groq = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Her kullanıcının sohbet geçmişini tut
sohbet_gecmisi = {}

def obilet_ara(nereden, nereye):
    url = f"https://www.obilet.com/otobus-bileti/{nereden}-{nereye}"

    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )

    driver.get(url)
    time.sleep(5)

    seferler_ham = []
    seferler = driver.find_elements(By.CSS_SELECTOR, ".journeys ul li")

    for sefer in seferler[:15]:
        try:
            firma = sefer.find_element(By.CSS_SELECTOR, "[itemprop='name']").get_attribute("content")
            kalkis = sefer.find_element(By.CSS_SELECTOR, "[itemprop='departureTime']").text.strip()
            varis = sefer.find_element(By.CSS_SELECTOR, "[itemprop='arrivalTime']").text.strip()
            fiyat_str = sefer.find_element(By.CSS_SELECTOR, "[itemprop='lowPrice']").text.strip()
            fiyat_sayi = int(fiyat_str.replace("₺","").replace(".","").replace(",","").strip())
            seferler_ham.append({
                "firma": firma,
                "kalkis": kalkis,
                "varis": varis,
                "fiyat_str": fiyat_str,
                "fiyat": fiyat_sayi
            })
        except:
            continue

    driver.quit()
    return seferler_ham

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

    # Kullanıcının sohbet geçmişini başlat
    if kullanici_id not in sohbet_gecmisi:
        sohbet_gecmisi[kullanici_id] = [
            {
                "role": "system",
                "content": """Sen Türkiye'nin en iyi seyahat asistanısın. 
                Kullanıcıya seyahat önerileri yaparsın, rotalar önerirsin, 
                gezilecek yerleri anlatırsın ve otobüs bileti tavsiyesi verirsin.
                Türkçe konuş, samimi ve yardımsever ol.
                Kullanıcı bir tur veya gezi isterse önce güzel bir rota öner,
                sonra hangi şehirden başlamaları gerektiğini söyle.
                Eğer kullanıcı bilet sormadan önce rota öneriyorsan,
                sohbetin sonunda 'İstanbul-Erzurum bileti aramak ister misin?' gibi bir öneri yap."""
            }
        ]

    # Kullanıcı mesajını geçmişe ekle
    sohbet_gecmisi[kullanici_id].append({
        "role": "user",
        "content": soru
    })

    # Bilet araması var mı kontrol et
    nereden, nereye = bilet_ara_mi(soru)

    if nereden and nereye:
        await update.message.reply_text(f"🔍 {nereden.title()} → {nereye.title()} seferleri aranıyor...")
        seferler = obilet_ara(nereden, nereye)
        bilet_mesaji = formatla(seferler, nereden, nereye)
        await update.message.reply_text(bilet_mesaji, parse_mode="Markdown")

        # Asistana da bildir
        sohbet_gecmisi[kullanici_id].append({
            "role": "assistant",
            "content": f"{nereden} → {nereye} seferlerini listeledim."
        })
    else:
        # Normal sohbet — Groq'a gönder
        response = groq.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=sohbet_gecmisi[kullanici_id],
            max_tokens=800
        )

        asistan_cevabi = response.choices[0].message.content

        # Cevabı geçmişe ekle
        sohbet_gecmisi[kullanici_id].append({
            "role": "assistant",
            "content": asistan_cevabi
        })

        await update.message.reply_text(asistan_cevabi)

app = ApplicationBuilder().token(os.getenv("TELEGRAM_TOKEN")).build()
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mesaj_isle))

print("🤖 Seyahat Asistanı Botu Başlatıldı!")
app.run_polling()