import os
import yaml
import git
import re
from netmiko import ConnectHandler, file_transfer
from datetime import datetime
from dotenv import load_dotenv

# --- KONFIGURASI ---
load_dotenv()
USER = os.getenv("ROUTER_USERNAME")
PASS = os.getenv("ROUTER_PASSWORD")
BACKUP_DIR = "backups"
INVENTORY_FILE = "inventory.yaml"

# Init Git jika belum ada (Auto-Create)
if not os.path.exists(BACKUP_DIR):
    os.makedirs(BACKUP_DIR)
try:
    REPO = git.Repo(BACKUP_DIR)
except:
    REPO = git.Repo.init(BACKUP_DIR)

def load_inventory():
    """Membaca daftar router dari YAML"""
    with open(INVENTORY_FILE, 'r') as f:
        return yaml.safe_load(f)

# --- FUNGSI 1: BACKUP ---
def run_backup_task(hostname, ip, device_type):
    """Melakukan SSH, ambil config, simpan, dan commit git"""
    device = {
        'device_type': device_type, 'host': ip,
        'username': USER, 'password': PASS, 'port': 22
    }
    
    try:
        # 1. Koneksi
        net_connect = ConnectHandler(**device)
        net_connect.enable()
        
        # 2. Ambil Config
        raw = net_connect.send_command("show running-config")
        
        # 3. Bersihkan Regex (Timestamp)
        clean = re.sub(r"^! Last configuration.*", "", raw, flags=re.MULTILINE)
        clean = re.sub(r"^! NVRAM config.*", "", clean, flags=re.MULTILINE)
        clean = clean.strip()
        
        # 4. Simpan File
        filename = f"{hostname}.cfg"
        filepath = os.path.join(BACKUP_DIR, filename)
        
        with open(filepath, 'w') as f:
            f.write(clean)
            
        # 5. Git Logic
        REPO.index.add([filename])
        has_changes = False
        
        # Cek apakah ada perubahan dibanding commit sebelumnya
        if REPO.head.is_valid():
            if len(REPO.index.diff("HEAD")) > 0: has_changes = True
        else:
            has_changes = True # Commit pertama
            
        status = "No Change"
        msg = "Config identik."

        if has_changes:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            REPO.index.commit(f"Backup {hostname} at {ts}")
            status = "Changed"
            msg = "Perubahan terdeteksi & disimpan."
            
        net_connect.disconnect()
        return True, status, msg

    except Exception as e:
        return False, "Error", str(e)

# --- FUNGSI 2: RESTORE ---
def run_restore_task(hostname, ip, device_type, commit_hex):
    """Time Travel: Checkout Git masa lalu -> Upload ke Router -> Restore"""
    device = {
        'device_type': device_type, 'host': ip,
        'username': USER, 'password': PASS, 'port': 22
    }
    
    filename = f"{hostname}.cfg"
    
    try:
        # A. Checkout file lokal ke versi masa lalu (Git)
        REPO.git.checkout(commit_hex, "--", filename)
        local_file = os.path.join(BACKUP_DIR, filename)
        
        # B. Upload file ke Router (SCP/Netmiko)
        net_connect = ConnectHandler(**device)
        net_connect.enable()
        
        file_transfer(
            net_connect, source_file=local_file, dest_file='restore_candidate.cfg',
            file_system='flash:', direction='put', overwrite_file=True
        )
        
        # C. Eksekusi Restore (Configure Replace)
        cmd = "configure replace flash:/restore_candidate.cfg force"
        # Timeout lama karena router butuh waktu loading
        output = net_connect.send_command(cmd, expect_string=r"#", read_timeout=90)
        net_connect.disconnect()
        
        # D. Kembalikan file lokal ke masa depan (HEAD) agar folder tetap update
        REPO.git.checkout("HEAD", "--", filename)
        
        # Cek jika router rollback (gagal)
        if "Rollback Done" in output:
            return False, "Router menolak config (Rollback terjadi)."
        
        return True, "Restore Berhasil!"
        
    except Exception as e:
        # Safety: Reset git jika crash di tengah jalan
        try: REPO.git.checkout("HEAD", "--", filename) 
        except: pass
        return False, str(e)

# --- FUNGSI 3: UTILITY (Untuk Dashboard) ---
def get_router_history(hostname):
    """Mengambil daftar riwayat commit untuk router tertentu"""
    filename = f"{hostname}.cfg"
    # Cek apakah file ada di git history
    try:
        commits = list(REPO.iter_commits(paths=filename, max_count=10))
    except:
        return []

    data = []
    for c in commits:
        dt = datetime.fromtimestamp(c.committed_date)
        data.append({
            "hash": c.hexsha,
            "short_hash": c.hexsha[:7],
            "time": dt.strftime('%Y-%m-%d %H:%M'),
            "message": c.message.strip()
        })
    return data
