# Script ini dipanggil oleh Cron Job Linux tiap menit
from backend import run_backup_task, load_inventory
import datetime

# Timestamp untuk log file
now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
print(f"--- [CRON RUN] {now} ---")

try:
    inventory = load_inventory()
    for r in inventory['routers']:
        # Panggil fungsi backup dari backend.py
        success, status, msg = run_backup_task(r['hostname'], r['ip'], r['device_type'])
        
        if status == "Changed":
            print(f"[CHANGE] {r['hostname']}: Config Berubah -> {msg}")
        elif status == "No Change":
            print(f"[SKIP]   {r['hostname']}: Tidak ada perubahan.")
        else:
            print(f"[ERROR]  {r['hostname']}: {msg}")

except Exception as e:
    print(f"[FATAL ERROR] {e}")

print("--------------------------\n")
