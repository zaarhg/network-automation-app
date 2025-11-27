# Script ini dipanggil oleh Cron Job Linux
from backend import run_backup_task, load_inventory
import datetime

# Ambil waktu sekarang untuk log
now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
print(f"--- [CRON START] {now} ---")

try:
    inventory = load_inventory()
    for r in inventory['routers']:
        # Panggil fungsi backup dari backend
        success, status, msg = run_backup_task(r['hostname'], r['ip'], r['device_type'])
        
        # Print hasil agar terekam di file log (logs/cron.log)
        if status == "Changed":
            print(f"[CHANGE] {r['hostname']}: Config berubah! Backup disimpan.")
        elif status == "No Change":
            print(f"[SKIP]   {r['hostname']}: Tidak ada perubahan.")
        else:
            print(f"[ERROR]  {r['hostname']}: {msg}")

except Exception as e:
    print(f"[FATAL ERROR] {e}")

print("--- [CRON END] ---\n")
