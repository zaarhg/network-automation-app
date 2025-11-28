import os
import requests
from dotenv import load_dotenv

# Load token dan ID dari file .env yang sudah kamu edit tadi
load_dotenv()
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_alert(title, message, status="info"):
    """
    Mengirim notifikasi ke Telegram.
    Status: info, warning, error, success
    """
    # Cek apakah token sudah diisi. Jika kosong, fungsi berhenti.
    if not TG_TOKEN or not TG_CHAT_ID:
        print("⚠️ Warning: Token/Chat ID belum diset di .env")
        return 

    # Pilih Ikon berdasarkan status
    icons = {
        "info": "ℹ️",
        "warning": "⚠️",
        "error": "❌",
        "success": "✅"
    }
    icon = icons.get(status, "📢")
    
    # Format Pesan (Markdown)
    full_msg = f"{icon} *{title}*\n\n{message}"
    
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    data = {
        "chat_id": TG_CHAT_ID,
        "text": full_msg,
        "parse_mode": "Markdown"
    }
    
    try:
        response = requests.post(url, data=data, timeout=5)
        # Debugging: Jika gagal kirim, print errornya di terminal
        if response.status_code != 200:
            print(f"Gagal kirim ke Telegram: {response.text}")
    except Exception as e:
        print(f"Error Koneksi Telegram: {e}")
