import os
import yaml
import git
import re
from netmiko import ConnectHandler, file_transfer
from datetime import datetime
from dotenv import load_dotenv
from notifications import send_alert  # <--- INI TAMBAHAN BARU

# --- KONFIGURASI ---
load_dotenv()
USER = os.getenv("ROUTER_USERNAME")
PASS = os.getenv("ROUTER_PASSWORD")
BACKUP_DIR = "backups"
INVENTORY_FILE = "inventory.yaml"

# Init Git jika belum ada
if not os.path.exists(BACKUP_DIR):
    os.makedirs(BACKUP_DIR)
try:
    REPO = git.Repo(BACKUP_DIR)
except:
    REPO = git.Repo.init(BACKUP_DIR)

def load_inventory():
    with open(INVENTORY_FILE, 'r') as f:
        return yaml.safe_load(f)

# --- FUNGSI 1: BACKUP CORE ---
def run_backup_task(hostname, ip, device_type):
    device = {
        'device_type': device_type, 'host': ip,
        'username': USER, 'password': PASS, 'port': 22
    }
    
    try:
        # 1. Koneksi SSH
        net_connect = ConnectHandler(**device)
        net_connect.enable()
        
        # 2. Ambil Config
        raw = net_connect.send_command("show running-config")
        
        # 3. Bersihkan Regex
        clean = re.sub(r"^! Last configuration.*", "", raw, flags=re.MULTILINE)
        clean = re.sub(r"^! NVRAM config.*", "", clean, flags=re.MULTILINE)
        clean = clean.strip()
        
        # 4. Simpan File ke Lokal
        filename = f"{hostname}.cfg"
        filepath = os.path.join(BACKUP_DIR, filename)
        
        with open(filepath, 'w') as f:
            f.write(clean)
            
        # 5. Git Logic
        REPO.index.add([filename])
        has_changes = False
        
        if REPO.head.is_valid():
            if len(REPO.index.diff("HEAD")) > 0: has_changes = True
        else:
            has_changes = True 
            
        status = "No Change"
        msg = "Config identik."

        if has_changes:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            REPO.index.commit(f"Backup {hostname} at {ts}")
            
            # --- AUTO PUSH KE GITHUB ---
            push_msg = ""
            try:
                if 'origin' in REPO.remotes:
                    REPO.remote('origin').push()
                    push_msg = " & Cloud Uploaded ☁️"
            except Exception as e:
                push_msg = " (Cloud Error)"
            
            status = "Changed"
            msg = f"Perubahan disimpan{push_msg}"

            # === KIRIM NOTIFIKASI TELEGRAM (SUCCESS) ===
            send_alert(
                title="CONFIG CHANGE DETECTED",
                message=f"Router: `{hostname}`\nWaktu: {ts}\nStatus: {msg}",
                status="warning"
            )
            
        net_connect.disconnect()
        return True, status, msg

    except Exception as e:
        # === KIRIM NOTIFIKASI TELEGRAM (ERROR) ===
        send_alert(
            title="BACKUP FAILED",
            message=f"Router: `{hostname}`\nError: {str(e)}",
            status="error"
        )
        return False, "Error", str(e)

# --- FUNGSI 2: RESTORE CORE ---
def run_restore_task(hostname, ip, device_type, commit_hex):
    device = {
        'device_type': device_type, 'host': ip,
        'username': USER, 'password': PASS, 'port': 22
    }
    
    filename = f"{hostname}.cfg"
    
    try:
        REPO.git.checkout(commit_hex, "--", filename)
        local_file = os.path.join(BACKUP_DIR, filename)
        
        net_connect = ConnectHandler(**device)
        net_connect.enable()
        
        file_transfer(
            net_connect, source_file=local_file, dest_file='restore_candidate.cfg',
            file_system='flash:', direction='put', overwrite_file=True
        )
        
        cmd = "configure replace flash:/restore_candidate.cfg force"
        output = net_connect.send_command(cmd, expect_string=r"#", read_timeout=90)
        net_connect.disconnect()
        
        REPO.git.checkout("HEAD", "--", filename)
        
        if "Rollback Done" in output:
            return False, "Router menolak config (Rollback terjadi)."
        
        # === NOTIFIKASI RESTORE SUKSES ===
        send_alert(
            title="SYSTEM RESTORED",
            message=f"Router `{hostname}` berhasil dipulihkan ke versi `{commit_hex[:7]}`.",
            status="success"
        )
        
        return True, "Restore Berhasil!"
        
    except Exception as e:
        try: REPO.git.checkout("HEAD", "--", filename) 
        except: pass
        
        # Notifikasi Error Restore
        send_alert(
            title="RESTORE ERROR",
            message=f"Gagal restore `{hostname}`.\nError: {str(e)}",
            status="error"
        )
        return False, str(e)

# --- FUNGSI 3: UTILITY (SMART STABLE SEARCH) ---
def get_router_history(hostname):
    filename = f"{hostname}.cfg"
    try:
        commits = list(REPO.iter_commits(paths=filename, max_count=15))
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

def find_smart_stable_commit(hostname):
    from datetime import timedelta
    filename = f"{hostname}.cfg"
    try:
        commits = list(REPO.iter_commits(paths=filename, max_count=10))
    except:
        return None

    if len(commits) < 2:
        return None 

    best_candidate = commits[1]
    
    for i in range(1, len(commits)-1):
        current = commits[i]
        newer = commits[i-1]
        
        duration = datetime.fromtimestamp(newer.committed_date) - datetime.fromtimestamp(current.committed_date)
        if duration > timedelta(hours=24):
            return current
            
    return best_candidate

# ... (Kode di atas biarkan saja) ...

# --- FUNGSI 5: TAMBAH ROUTER BARU (ADD DEVICE) ---
def add_router_to_inventory(hostname, ip, device_type="cisco_ios"):
    """Menambahkan router baru ke file YAML dengan validasi duplikasi"""
    
    # 1. Load data lama
    try:
        data = load_inventory()
    except:
        data = {'routers': []} # Buat baru jika file kosong
        
    # 2. Validasi: Cek apakah Hostname atau IP sudah ada?
    for r in data['routers']:
        if r['hostname'] == hostname:
            return False, f"Hostname '{hostname}' sudah terdaftar!"
        if r['ip'] == ip:
            return False, f"IP Address '{ip}' sudah digunakan oleh {r['hostname']}!"

    # 3. Tambahkan data baru
    new_router = {
        'hostname': hostname,
        'ip': ip,
        'device_type': device_type
    }
    data['routers'].append(new_router)
    
    # 4. Tulis ulang ke file YAML
    try:
        with open(INVENTORY_FILE, 'w') as f:
            # default_flow_style=False agar formatnya rapi (block style)
            yaml.dump(data, f, default_flow_style=False)
        return True, f"Router {hostname} berhasil ditambahkan ke inventory."
    except Exception as e:
        return False, f"Gagal menulis file: {str(e)}"
