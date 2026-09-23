# 📊 Budget Agent: Discord RAG Text-to-SQL & Conversational Analytics

Bot Discord cerdas berbasis **RAG Text-to-SQL** yang terhubung langsung ke **Google BigQuery** menggunakan **DeepSeek API** dan **Google Cloud Firestore Memory**. Bot ini memproses pertanyaan pengguna terkait data budget/keuangan dalam Bahasa Indonesia, mengingat hingga 10 riwayat percakapan terakhir, mengeksekusi query SQL secara aman, memberikan penjelasan analisis, dan membuat grafik/chart visual secara otomatis.

---

## 🌟 Fitur Utama

1. **RAG Text-to-SQL dengan DeepSeek API**: Menterjemahkan pertanyaan bahasa alami ke BigQuery Standard SQL secara akurat & cepat.
2. **Multi-turn Memory via Firestore (10 Percakapan Terakhir)**: Menyimpan dan memanfaatkan riwayat percakapan hingga 10 pesan terakhir per channel di Google Cloud Firestore, memungkinkan pertanyaan lanjutan seperti *"bagaimana dengan divisi Marketing?"* atau *"berapa sisa anggarannya?"*.
3. **Mention Handler (`@BudgetBot`)**: Cukup mention bot di channel Discord mana saja untuk menanyakan data budget.
4. **Autogenerasi Chart Visual**: Membuat grafik (Bar Chart, Line Chart, Pie Chart) dari hasil query BigQuery menggunakan `matplotlib` & `seaborn` dan melampirkannya sebagai gambar PNG di Discord.
5. **Keamanan SQL (Read-Only)**: Mencegah eksekusi query berbahaya (memblokir `DROP`, `DELETE`, `UPDATE`, `INSERT`).
6. **Siap Deploy ke Google Cloud Run (Serverless)**: Di-deploy tanpa perlu sewa VM. Menggunakan koneksi WebSocket persisten di Cloud Run dengan autentikasi otomatis (Service Account GCP).

---

## 📁 Struktur Project

```text
Budget Agent/
├── bot.py                      # Main entrypoint Discord Bot (@mention handler & Firestore memory)
├── core/
│   ├── bq_client.py            # BigQuery Client execution & safety validation
│   ├── memory_manager.py       # Firestore multi-turn memory manager (10 recent turns)
│   ├── rag_retriever.py        # RAG metadata schema retriever
│   ├── sql_generator.py        # DeepSeek API integration (Text-to-SQL with memory context)
│   └── chart_generator.py      # Matplotlib chart renderer (Discord dark theme)
├── sample_data/
│   └── schema_definition.json  # Metadata skema tabel budget & aturan bisnis
├── Dockerfile                  # Container definition untuk Cloud Run
├── deploy.sh                   # Script deployment ke Cloud Run
├── requirements.txt            # Library Python dependencies
└── .env.example                # Template environment variables
```

---

## 🚀 Panduan Setup & Penggunaan

### 1. Persiapan Kredensial

1. **Discord Bot Token**:
   - Buat Bot di [Discord Developer Portal](https://discord.com/developers/applications).
   - Di tab **Bot**, aktifkan **Message Content Intent** (Wajib agar bot bisa membaca teks mention).
   - Copy Bot Token.

2. **DeepSeek API Key**:
   - Dapatkan API Key di [DeepSeek Platform](https://platform.deepseek.com/).

3. **Google Cloud (BigQuery & Firestore)**:
   - Buat Dataset di BigQuery (misal `budget_dataset`).
   - Aktifkan Firestore di GCP Console (pilih Native mode).
   - Saat berjalan di Cloud Run, Service Account bawaan Cloud Run secara otomatis memiliki akses ke BigQuery & Firestore.

---

### 2. Jalankan Lokal (Testing)

```bash
# 1. Clone / Masuk ke direktori
cd "Budget Agent"

# 2. Install dependencies
pip install -r requirements.txt

# 3. Salin & konfigurasi file .env
cp .env.example .env
```

Isi file `.env`:
```env
DISCORD_TOKEN=your_discord_bot_token
DEEPSEEK_API_KEY=your_deepseek_api_key
GCP_PROJECT_ID=your_gcp_project_id

# Dapat menggunakan 1 atau 2 dataset (atau lebih) dipisahkan koma
BIGQUERY_DATASET=mrt_procurement,dataset_keuangan

# Minimal 1 tabel, atau tambah tabel lain dengan koma (misal: stg_monthly_budget,mrt_compile_v04,tabel_baru)
BIGQUERY_ALLOWED_TABLES=stg_monthly_budget,mrt_compile_v04

GOOGLE_APPLICATION_CREDENTIALS=path/to/service_account.json
```

Jalankan bot:
```bash
python bot.py
```

---

### 3. Deploy ke Google Cloud Run (Tanpa Sewa Server)

Deploy bot ke **Google Cloud Run** agar dapat berjalan 24/7 secara serverless dan hemat biaya:

#### Langkah Deployment via gcloud CLI:

```bash
# Pastikan gcloud CLI sudah terinstall dan login
gcloud auth login
gcloud config set project ID_PROJECT_GCP_ANDA

# Jalankan command deploy
gcloud run deploy budget-discord-bot \
  --source . \
  --region asia-east1 \
  --allow-unauthenticated \
  --env-vars-file env.yaml
```

---

## 💬 Contoh Penggunaan di Discord (Multi-turn Conversation)

- **Turn 1 (Pertanyaan Awal)**:
  > `@BudgetBot Berapa total alokasi budget divisi IT tahun 2026?`

- **Turn 2 (Pertanyaan Lanjutan - Memperhitungkan Memori Firestore)**:
  > `@BudgetBot Bagaimana dengan realisasi pengeluarannya dan sisa anggarannya?`

- **Turn 3 (Visualisasi Lanjutan)**:
  > `@BudgetBot Tampilkan grafik perbandingan budget divisi IT vs Marketing.`
