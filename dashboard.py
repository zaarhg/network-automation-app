import streamlit as st
import pandas as pd
import time
import git
from datetime import datetime
# Import fungsi dari file backend.py yang baru saja kita buat
from backend import load_inventory, run_backup_task, run_restore_task, get_router_history

# --- KONFIGURASI HALAMAN ---
st.set_page_config(
    page_title="NetAuto Pro",
    page_icon="🛡️",
    layout="wide"
)

# --- JUDUL & SIDEBAR ---
st.title("🛡️ Network Disaster Recovery Center")
st.markdown("Sistem Otomasi Backup & Restore Hybrid (Lokal + Git)")

# Load data router saat awal buka
try:
    inventory = load_inventory()
    routers = inventory['routers']
    router_names = [r['hostname'] for r in routers]
except Exception as e:
    st.error(f"Gagal memuat inventory.yaml: {e}")
    st.stop()

# Menu Navigasi di Kiri
menu = st.sidebar.radio(
    "Menu Navigasi", 
    ["📊 Dashboard", "⚙️ Backup Manager", "🚑 Disaster Recovery", "📜 Audit Logs"]
)

# === TAB 1: DASHBOARD UTAMA ===
if menu == "📊 Dashboard":
    st.subheader("Ringkasan Kesehatan Jaringan")
    
    # Statistik Dummy (Bisa dikembangkan real-time)
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Router", len(routers))
    col2.metric("Backup Frequency", "Setiap 1 Menit")
    col3.metric("System Status", "Online ✅")
    
    st.markdown("---")
    st.write("### 📋 Daftar Perangkat Terdaftar")
    
    # Tampilkan tabel router yang lebih rapi
    df = pd.DataFrame(routers)
    # Rapikan nama kolom agar enak dibaca
    df.columns = [c.replace('_', ' ').title() for c in df.columns]
    st.dataframe(df, use_container_width=True)

# === TAB 2: BACKUP MANAGER ===
elif menu == "⚙️ Backup Manager":
    st.subheader("Manajemen Backup Manual")
    st.info("Gunakan menu ini jika ingin memicu backup sekarang juga tanpa menunggu jadwal otomatis.")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        target_router = st.selectbox("Pilih Router", router_names)
    with col2:
        st.write("") # Spasi kosong biar tombol sejajar
        st.write("")
        btn_backup = st.button("🚀 Jalankan Backup", type="primary")
    
    if btn_backup:
        # Cari detail IP dan tipe device dari inventory berdasarkan nama hostname
        selected = next(r for r in routers if r['hostname'] == target_router)
        
        # Tampilkan status loading yang keren
        with st.status(f"Sedang memproses {target_router}...", expanded=True) as status:
            st.write("1. Menghubungkan ke router via SSH...")
            time.sleep(0.5)
            
            # Panggil Fungsi Backend
            success, state, msg = run_backup_task(selected['hostname'], selected['ip'], selected['device_type'])
            
            if success:
                st.write("2. Mengambil konfigurasi & Membandingkan Git...")
                time.sleep(0.5)
                
                if state == "Changed":
                    status.update(label="Backup Selesai: Ada Perubahan!", state="complete", expanded=False)
                    st.success(f"✅ {msg}")
                    # Munculkan notifikasi pop-up (Toast)
                    st.toast('Backup Berhasil Disimpan!', icon='💾')
                else:
                    status.update(label="Backup Selesai: Tidak Ada Perubahan.", state="complete", expanded=False)
                    st.info(f"ℹ️ {msg}")
            else:
                status.update(label="Backup Gagal!", state="error")
                st.error(f"❌ Error: {msg}")

# === TAB 3: DISASTER RECOVERY ===
elif menu == "🚑 Disaster Recovery":
    st.subheader("⚠️ Pemulihan Bencana (Restore)")
    st.warning("Halaman ini digunakan untuk mengembalikan konfigurasi router ke versi masa lalu (Time Travel).")
    
    # 1. Pilih Router
    target_restore = st.selectbox("Pilih Router yang Bermasalah", router_names)
    
    # 2. Ambil History dari Git Backend
    history = get_router_history(target_restore)
    
    if not history:
        st.error("❌ Belum ada data backup untuk router ini. Lakukan backup minimal sekali.")
    else:
        # Siapkan data dropdown: Format "Waktu - Pesan (Hash)"
        # Dictionary comprehension: {Label Tampilan : Value Hash}
        options = {f"{item['time']} - {item['message']} ({item['short_hash']})": item['hash'] for item in history}
        
        selected_option = st.selectbox("Pilih Versi Backup (Checkpoint)", list(options.keys()))
        commit_hash = options[selected_option]
        
        st.info(f"Anda akan me-restore **{target_restore}** ke kondisi: **{selected_option}**")
        
        # Tombol Eksekusi
        if st.button("🚨 MULAI PROSES RESTORE", type="primary"):
            
            # Konfirmasi visual loading
            with st.status("Memulai prosedur pemulihan...", expanded=True) as status:
                st.write("1. Checkout file dari Git History...")
                time.sleep(1)
                st.write("2. Uploading config ke Router Flash...")
                
                # Panggil Fungsi Backend
                r_data = next(r for r in routers if r['hostname'] == target_restore)
                success, msg = run_restore_task(r_data['hostname'], r_data['ip'], r_data['device_type'], commit_hash)
                
                if success:
                    st.write("3. Applying Configuration (Atomic Replace)...")
                    status.update(label="Restore Berhasil!", state="complete")
                    st.success(f"✅ SUKSES: {msg}")
                    st.balloons() # Efek Hore keluar balon
                else:
                    status.update(label="Restore Gagal", state="error")
                    st.error(f"❌ GAGAL: {msg}")

# === TAB 4: LOGS ===
elif menu == "📜 Audit Logs":
    st.subheader("Catatan Aktivitas Git (Global)")
    
    try:
        repo = git.Repo("backups")
        # Ambil 15 commit terakhir dari semua router
        commits = list(repo.iter_commits(max_count=15))
        
        log_data = []
        for c in commits:
            log_data.append({
                "Waktu": datetime.fromtimestamp(c.committed_date).strftime('%Y-%m-%d %H:%M:%S'),
                "Pesan": c.message.strip(),
                "Hash": c.hexsha[:7],
                "Author": c.author.name
            })
        
        st.table(pd.DataFrame(log_data))
    except Exception as e:
        st.warning("Folder backup belum di-init Git atau masih kosong.")
