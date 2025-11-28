import streamlit as st
import pandas as pd
import time
import os
import git
from datetime import datetime
from backend import load_inventory, run_backup_task, run_restore_task, get_router_history

# --- KONFIGURASI HALAMAN ---
st.set_page_config(page_title="NetAuto Pro", page_icon="🛡️", layout="wide")

st.title("🛡️ Network Disaster Recovery Center")
st.markdown("Sistem Otomasi Backup & Restore Hybrid (Lokal + Git Cloud)")

# Load Inventory
try:
    inventory = load_inventory()
    routers = inventory['routers']
    router_names = [r['hostname'] for r in routers]
except Exception as e:
    st.error(f"Gagal memuat inventory.yaml: {e}")
    st.stop()

# --- SIDEBAR MENU (UPDATE: Ada menu System Logs) ---
menu = st.sidebar.radio(
    "Menu Navigasi", 
    ["📊 Dashboard", "⚙️ Backup Manager", "🚑 Disaster Recovery", "📜 Audit Logs", "🖥️ System Logs"]
)

# === TAB 1: DASHBOARD ===
if menu == "📊 Dashboard":
    st.subheader("Ringkasan Kesehatan Jaringan")
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Router", len(routers))
    col2.metric("Backup Schedule", "Every 1 Minute")
    col3.metric("Cloud Sync", "Active (GitHub) ☁️")
    
    st.markdown("---")
    st.write("### 📋 Daftar Perangkat")
    df = pd.DataFrame(routers)
    df.columns = [c.replace('_', ' ').title() for c in df.columns]
    st.dataframe(df, use_container_width=True)

# === TAB 2: BACKUP MANUAL ===
elif menu == "⚙️ Backup Manager":
    st.subheader("Manajemen Backup Manual")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        target_router = st.selectbox("Pilih Router", router_names)
    with col2:
        st.write("")
        st.write("")
        btn_backup = st.button("🚀 Jalankan Backup", type="primary")
    
    if btn_backup:
        selected = next(r for r in routers if r['hostname'] == target_router)
        with st.status(f"Memproses {target_router}...", expanded=True) as status:
            st.write("Connecting via SSH...")
            time.sleep(0.5)
            success, state, msg = run_backup_task(selected['hostname'], selected['ip'], selected['device_type'])
            
            if success:
                if state == "Changed":
                    status.update(label="Backup Selesai: Ada Perubahan!", state="complete")
                    st.success(f"✅ {msg}")
                    st.toast('Backup Tersimpan & Uploaded!', icon='☁️')
                else:
                    status.update(label="Selesai: Tidak Ada Perubahan.", state="complete")
                    st.info(f"ℹ️ {msg}")
            else:
                status.update(label="Gagal!", state="error")
                st.error(f"❌ Error: {msg}")

# === TAB 3: RESTORE (RECOVERY) ===

# ... (Kode atas sama)

# === TAB 3: DISASTER RECOVERY (UPDATED) ===
elif menu == "🚑 Disaster Recovery":
    st.subheader("⚠️ Pemulihan Bencana (Restore)")
    
    # Pilihan Mode Restore
    mode_restore = st.radio("Mode Pemulihan", ["🛠️ Manual (Single Router)", "🤖 Otomatis (Smart Batch Restore)"], horizontal=True)
    st.markdown("---")

    # --- MODE 1: MANUAL (YANG LAMA) ---
    if mode_restore == "🛠️ Manual (Single Router)":
        st.info("Mode ini untuk memulihkan 1 router spesifik ke versi pilihan Anda.")
        
        target_restore = st.selectbox("Pilih Router Bermasalah", router_names)
        history = get_router_history(target_restore)
        
        if not history:
            st.error("❌ Belum ada data backup.")
        else:
            options = {f"{item['time']} - {item['message']} ({item['short_hash']})": item['hash'] for item in history}
            selected_option = st.selectbox("Pilih Versi Backup", list(options.keys()))
            commit_hash = options[selected_option]
            
            if st.button("🚨 EKSEKUSI RESTORE", type="primary"):
                with st.status("Memproses...", expanded=True) as status:
                    st.write("Processing...")
                    # Panggil fungsi dari backend (impor dulu find_smart_stable_commit di atas jika perlu, tapi disini kita pakai hash manual)
                    r_data = next(r for r in routers if r['hostname'] == target_restore)
                    success, msg = run_restore_task(r_data['hostname'], r_data['ip'], r_data['device_type'], commit_hash)
                    
                    if success:
                        status.update(label="Sukses!", state="complete")
                        st.success(f"✅ {msg}")
                    else:
                        status.update(label="Gagal!", state="error")
                        st.error(f"❌ {msg}")

    # --- MODE 2: OTOMATIS (YANG KAMU CARI) ---
    elif mode_restore == "🤖 Otomatis (Smart Batch Restore)":
        st.warning("Mode ini akan memindai seluruh jaringan, mencari router yang config-nya 'mencurigakan' (baru berubah < 1 jam), dan mengembalikannya ke versi stabil.")
        
        # 1. SCANNING (Analisis Router)
        st.write("### 🔍 Hasil Analisis Jaringan")
        
        suspects = []
        
        # Kita pakai container biar rapi
        with st.spinner("Sedang memindai anomali konfigurasi..."):
            import git
            from datetime import timedelta
            repo = git.Repo("backups")
            
            for r in routers:
                hostname = r['hostname']
                filename = f"{hostname}.cfg"
                
                # Cek kapan terakhir berubah
                try:
                    commit = next(repo.iter_commits(paths=filename, max_count=1))
                    last_change = datetime.fromtimestamp(commit.committed_date)
                    diff = datetime.now() - last_change
                    
                    # LOGIKA SUSPECT: Jika berubah kurang dari 60 menit lalu
                    is_suspect = diff < timedelta(minutes=60)
                    
                    if is_suspect:
                        status_icon = "⚠️ SUSPECT"
                        suspects.append(r)
                        st.error(f"**{hostname}**: Berubah {diff.seconds//60} menit lalu (Perlu Restore)")
                    else:
                        st.success(f"**{hostname}**: Stabil sejak {diff.days} hari lalu (Aman)")
                        
                except:
                    st.info(f"**{hostname}**: Belum ada backup.")

        # 2. EKSEKUSI MASSAL
        if not suspects:
            st.info("✅ Semua router terlihat stabil. Tidak ada tindakan yang diperlukan.")
        else:
            st.divider()
            st.write(f"Ditemukan **{len(suspects)} Router** yang mencurigakan.")
            
            if st.button(f"🚑 PULIHKAN {len(suspects)} ROUTER SEKALIGUS", type="primary"):
                
                # Import fungsi baru dari backend
                from backend import find_smart_stable_commit
                
                progress_bar = st.progress(0)
                
                for idx, r in enumerate(suspects):
                    hostname = r['hostname']
                    
                    # Cari versi stabil
                    stable_commit = find_smart_stable_commit(hostname)
                    
                    if stable_commit:
                        with st.spinner(f"Memulihkan {hostname} ke versi stabil..."):
                            success, msg = run_restore_task(r['hostname'], r['ip'], r['device_type'], stable_commit.hexsha)
                            if success:
                                st.toast(f"{hostname} Pulih!", icon="✅")
                            else:
                                st.toast(f"{hostname} Gagal: {msg}", icon="❌")
                    else:
                        st.warning(f"{hostname}: Tidak ditemukan versi stabil sebelumnya.")
                    
                    progress_bar.progress((idx + 1) / len(suspects))
                
                st.success("Proses Auto-Restore Selesai.")
                time.sleep(2)
                st.rerun()

# ... (Tab Audit Logs sama)

# === TAB 4: AUDIT LOGS (GIT) ===
elif menu == "📜 Audit Logs":
    st.subheader("Riwayat Perubahan Config (Git)")
    try:
        repo = git.Repo("backups")
        commits = list(repo.iter_commits(max_count=20))
        log_data = []
        for c in commits:
            log_data.append({
                "Waktu": datetime.fromtimestamp(c.committed_date).strftime('%Y-%m-%d %H:%M:%S'),
                "Pesan": c.message.strip(),
                "Hash": c.hexsha[:7]
            })
        st.table(pd.DataFrame(log_data))
    except:
        st.warning("Log Git kosong.")

# === TAB 5: SYSTEM LOGS (BARU!) ===
elif menu == "🖥️ System Logs":
    st.subheader("System Logs (Real-time Cron)")
    st.caption("Menampilkan log aktivitas background (Cron Job). Berguna untuk melihat error atau backup yang di-skip.")
    
    col1, col2 = st.columns([4,1])
    with col2:
        if st.button("🔄 Refresh Log"):
            st.rerun()

    log_file = "logs/cron.log"
    if os.path.exists(log_file):
        with open(log_file, "r") as f:
            lines = f.readlines()
            # Trik: Balik urutan agar log terbaru ada di PALING ATAS
            lines.reverse()
            # Ambil 100 baris terakhir saja biar tidak berat
            recent_logs = "".join(lines[:100])
            
            st.code(recent_logs, language="text")
    else:
        st.warning("⚠️ File log belum terbentuk. Tunggu Cron Job berjalan beberapa menit lagi.")
