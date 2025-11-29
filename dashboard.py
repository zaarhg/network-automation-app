import streamlit as st
import pandas as pd
import time
import os
import git
from datetime import datetime, timedelta
# Import semua fungsi dari backend
from backend import (
    load_inventory, 
    run_backup_task, 
    run_restore_task, 
    get_router_history, 
    add_router_to_inventory,
    find_smart_stable_commit
)

# --- KONFIGURASI HALAMAN ---
st.set_page_config(
    page_title="NetAuto Pro",
    page_icon="🛡️",
    layout="wide"
)

st.title("🛡️ Network Disaster Recovery Center")
st.markdown("Sistem Otomasi Backup & Restore Hybrid (Lokal + Git Cloud)")

# Load Inventory (Data Router)
try:
    inventory = load_inventory()
    routers = inventory['routers']
    router_names = [r['hostname'] for r in routers]
except Exception as e:
    st.error(f"Gagal memuat inventory.yaml: {e}")
    st.stop()

# --- SIDEBAR MENU ---
menu = st.sidebar.radio(
    "Menu Navigasi", 
    [
        "📊 Dashboard", 
        "⚙️ Backup Manager", 
        "🚑 Disaster Recovery", 
        "📜 Audit Logs", 
        "➕ Add Device", 
        "🖥️ System Logs",
	"ℹ️ Tentang Aplikasi"
    ]
)

# === TAB 1: DASHBOARD UTAMA ===
if menu == "📊 Dashboard":
    st.subheader("Ringkasan Kesehatan Jaringan")
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Router", len(routers))
    col2.metric("Backup Schedule", "Every 1 Minute")
    col3.metric("Cloud Sync", "Active (GitHub) ☁️")
    
    st.markdown("---")
    st.write("### 📋 Daftar Perangkat Terdaftar")
    
    # Tampilkan tabel inventory
    if routers:
        df = pd.DataFrame(routers)
        # Rapikan nama kolom
        df.columns = [c.replace('_', ' ').title() for c in df.columns]
        st.dataframe(df, use_container_width=True)
    else:
        st.info("Belum ada router terdaftar. Gunakan menu 'Add Device'.")

# === TAB 2: BACKUP MANAGER (MANUAL) ===
elif menu == "⚙️ Backup Manager":
    st.subheader("Manajemen Backup Manual")
    st.info("Gunakan menu ini untuk memicu backup di luar jadwal otomatis.")
    
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
            st.write("1. Menghubungkan ke router via SSH...")
            time.sleep(0.5)
            
            # Panggil Fungsi Backend
            success, state, msg = run_backup_task(selected['hostname'], selected['ip'], selected['device_type'])
            
            if success:
                st.write("2. Membandingkan konfigurasi dengan Git...")
                if state == "Changed":
                    status.update(label="Backup Selesai: Ada Perubahan!", state="complete")
                    st.success(f"✅ {msg}")
                    st.toast('Backup Berhasil Disimpan & Uploaded!', icon='☁️')
                else:
                    status.update(label="Selesai: Tidak Ada Perubahan.", state="complete")
                    st.info(f"ℹ️ {msg}")
            else:
                status.update(label="Backup Gagal!", state="error")
                st.error(f"❌ Error: {msg}")

# === TAB 3: DISASTER RECOVERY (SMART RESTORE) ===
elif menu == "🚑 Disaster Recovery":
    st.subheader("⚠️ Pemulihan Bencana (Restore)")
    
    # Pilihan Mode Restore
    mode_restore = st.radio(
        "Mode Pemulihan", 
        ["🛠️ Manual (Single Router)", "🤖 Otomatis (Smart Batch Restore)"], 
        horizontal=True
    )
    st.markdown("---")

    # --- MODE 1: MANUAL ---
    if mode_restore == "🛠️ Manual (Single Router)":
        st.info("Mode ini untuk memulihkan 1 router spesifik ke versi pilihan Anda.")
        
        target_restore = st.selectbox("Pilih Router Bermasalah", router_names)
        history = get_router_history(target_restore)
        
        if not history:
            st.error("❌ Belum ada data backup untuk router ini.")
        else:
            options = {f"{item['time']} - {item['message']} ({item['short_hash']})": item['hash'] for item in history}
            selected_option = st.selectbox("Pilih Versi Backup", list(options.keys()))
            commit_hash = options[selected_option]
            
            if st.button("🚨 EKSEKUSI RESTORE", type="primary"):
                with st.status("Memulai prosedur pemulihan...", expanded=True) as status:
                    st.write("1. Mengambil file dari Git Archive...")
                    time.sleep(1)
                    st.write("2. Uploading config ke Router Flash...")
                    
                    r_data = next(r for r in routers if r['hostname'] == target_restore)
                    success, msg = run_restore_task(r_data['hostname'], r_data['ip'], r_data['device_type'], commit_hash)
                    
                    if success:
                        st.write("3. Applying Configuration (Atomic Replace)...")
                        status.update(label="Restore Berhasil!", state="complete")
                        st.success(f"✅ SUKSES: {msg}")
                        st.balloons()
                    else:
                        status.update(label="Restore Gagal", state="error")
                        st.error(f"❌ GAGAL: {msg}")

    # --- MODE 2: OTOMATIS (BATCH) ---
    elif mode_restore == "🤖 Otomatis (Smart Batch Restore)":
        st.warning("Mode ini memindai jaringan, mencari router dengan config 'mencurigakan' (baru berubah < 1 jam), dan mengembalikannya ke versi stabil (> 24 jam).")
        
        st.write("### 🔍 Hasil Analisis Jaringan")
        suspects = []
        
        with st.spinner("Sedang memindai anomali konfigurasi..."):
            try:
                repo = git.Repo("backups")
                for r in routers:
                    hostname = r['hostname']
                    filename = f"{hostname}.cfg"
                    
                    # Cek kapan terakhir berubah
                    try:
                        commit = next(repo.iter_commits(paths=filename, max_count=1))
                        last_change = datetime.fromtimestamp(commit.committed_date)
                        diff = datetime.now() - last_change
                        
                        # LOGIKA SUSPECT: Berubah < 60 menit lalu
                        is_suspect = diff < timedelta(minutes=60)
                        
                        if is_suspect:
                            suspects.append(r)
                            st.error(f"**{hostname}**: ⚠️ Konfigurasi berubah {diff.seconds//60} menit lalu (Unstable/Pantau)")
                        else:
                            st.success(f"**{hostname}**: ✅ Stabil sejak {diff.days} hari lalu")
                    except:
                        st.info(f"**{hostname}**: Belum ada backup.")
            except Exception as e:
                st.error(f"Gagal akses Git: {e}")

        # EKSEKUSI MASSAL
        if not suspects:
            st.info("✅ Semua router terlihat stabil. Tidak ada tindakan diperlukan.")
        else:
            st.divider()
            st.write(f"Ditemukan **{len(suspects)} Router** mencurigakan.")
            
            if st.button(f"🚑 PULIHKAN {len(suspects)} ROUTER SEKALIGUS", type="primary"):
                progress_bar = st.progress(0)
                
                for idx, r in enumerate(suspects):
                    hostname = r['hostname']
                    
                    # Cari versi stabil pakai fungsi backend
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

# === TAB 4: AUDIT LOGS ===
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
                "Hash": c.hexsha[:7],
                "Author": c.author.name
            })
        st.table(pd.DataFrame(log_data))
    except:
        st.warning("Folder backup belum di-init Git atau masih kosong.")

# === TAB 5: ADD DEVICE (BARU) ===
elif menu == "➕ Add Device":
    st.subheader("Tambah Perangkat Baru")
    st.info("Gunakan formulir ini untuk mendaftarkan router baru ke dalam sistem monitoring.")
    
    with st.form("form_add_router"):
        col1, col2 = st.columns(2)
        with col1:
            new_hostname = st.text_input("Hostname", placeholder="Contoh: csr1000v-03")
        with col2:
            new_ip = st.text_input("IP Address", placeholder="Contoh: 192.168.177.10")
            
        new_type = st.selectbox("Device Type", ["cisco_ios", "mikrotik_routeros", "juniper_junos"])
        
        submitted = st.form_submit_button("Simpan ke Inventory")
        
        if submitted:
            if not new_hostname or not new_ip:
                st.error("Hostname dan IP tidak boleh kosong!")
            else:
                success, msg = add_router_to_inventory(new_hostname, new_ip, new_type)
                
                if success:
                    st.success(f"✅ {msg}")
                    st.balloons()
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(f"❌ {msg}")

# ... (kode sebelumnya tetap sama) ...

# === TAB 7: TENTANG APLIKASI (UPDATED) ===
elif menu == "ℹ️ Tentang Aplikasi":
    
    # --- HEADER DENGAN LOGO UGM ---
    col_logo, col_text = st.columns([0.1, 0.9])
    with col_logo:
        # Coba URL logo alternatif resmi. 
        # Jika gambar masih pecah/tidak muncul, hapus baris st.image ini.
        st.image("https://upload.wikimedia.org/wikipedia/commons/6/6a/UNIVERSITAS_GADJAH_MADA%2C_YOGYAKARTA.png", width=100)
    with col_text:
        st.subheader("Universitas Gadjah Mada")
        st.markdown("**Program Studi Sarjana Terapan (D4) Teknologi Rekayasa Internet**")

    st.markdown("---")

    # --- TIM PENGEMBANG ---
    st.write("### 👨‍💻 Tim Pengembang")
    
    # Data sudah disederhanakan (Tanpa Peran)
    team_data = [
        {"NIM": "22/494433/SV/20820", "Nama": "Ahmad Zainul"},
        {"NIM": "22/505174/SV/21778", "Nama": "Bramunsya Derawan"},
        {"NIM": "22/505584/SV/21822", "Nama": "Ramdan irawan"},
    ]
    
    # Tampilkan tabel (otomatis menyesuaikan kolom)
    # Buat DataFrame
    df_team = pd.DataFrame(team_data)
    
    # Trik: Ubah Index agar mulai dari 1, bukan 0
    df_team.index = df_team.index + 1
    
    # Tampilkan
    st.table(df_team)

    # --- TAUTAN PENTING ---
    st.write("### 🔗 Tautan & Sumber Daya")
    
    col1, col2 = st.columns(2)
    with col1:
        st.info("📂 **Source Code & Repository**")
        st.link_button("Buka GitHub Repository", "https://github.com/zaarhg/network-automation-app")
        
    with col2:
        st.success("📢 **Grup Notifikasi**")
        st.link_button("Gabung Grup Telegram", "https://t.me/+sUapJDiDSmJhZjM1")

    st.markdown("---")

    # --- DESKRIPSI SISTEM (ABSTRAK) - POSISI DI BAWAH ---
    st.write("### 📝 Deskripsi Sistem (Abstrak Singkat)")
    
    st.markdown("""
    Sistem ini adalah platform **Network Configuration Management & Automation** yang dirancang 
    untuk meningkatkan ketersediaan (*availability*) dan keamanan konfigurasi perangkat jaringan.
    """)
    
    with st.container():
        st.write("**Fitur Unggulan:**")
        
        st.markdown("""
        * 🛡️ **Hybrid Backup Strategy:** Mengamankan konfigurasi router secara otomatis ke penyimpanan Lokal dan Cloud (GitHub Private) menggunakan protokol SSH yang aman.
            
        * 📜 **Smart Versioning:** Memanfaatkan teknologi Git untuk melacak setiap perubahan baris kode (*Audit Trail*) dan mencegah duplikasi data.
            
        * 🚑 **Intelligent Disaster Recovery:** Fitur pemulihan bencana yang mampu mendeteksi anomali konfigurasi (*router suspect*) dan melakukan *Auto-Remediation* (pemulihan otomatis) ke versi stabil terakhir secara massal.
            
        * 📊 **Real-time Monitoring:** Visualisasi status kesehatan jaringan dan log aktivitas sistem berbasis Web Dashboard.
        """)

# === TAB SYSTEM LOGS ===
elif menu == "🖥️ System Logs":
    st.subheader("System Logs (Real-time Cron)")
    st.caption("Menampilkan log aktivitas background (Cron Job).")
    
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
        st.warning("⚠️ File log belum terbentuk. Pastikan Cron Job sudah berjalan.")

