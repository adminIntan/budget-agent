import os
import json
import logging
from openai import OpenAI

logger = logging.getLogger(__name__)

class DeepSeekSQLGenerator:
    """Generates BigQuery standard SQL, natural language response, and chart recommendations using DeepSeek API with conversation memory."""

    def __init__(self, api_key: str = None, model: str = None, base_url: str = None):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        self.model = model or os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        self.base_url = base_url or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

        if not self.api_key:
            logger.warning("DEEPSEEK_API_KEY is missing!")

        self.client = OpenAI(
            api_key=self.api_key or "placeholder_key",
            base_url=self.base_url
        )

    def _format_history_context(self, history: list[dict]) -> str:
        """Formats the last N conversation turns into a string for LLM context."""
        if not history:
            return ""

        lines = ["=== RIWAYAT PERCAKAPAN SEBELUMNYA (MEMORI) ==="]
        for idx, turn in enumerate(history, 1):
            lines.append(f"Turn {idx}:")
            lines.append(f"  User: {turn.get('user', '')}")
            if turn.get('sql'):
                lines.append(f"  SQL Sebelumnya: `{turn.get('sql')}`")
            lines.append(f"  Asisten: {turn.get('assistant', '')[:200]}...")
        lines.append("Gunakan riwayat percakapan di atas jika pertanyaan pengguna merujuk ke topik/divisi/periode sebelumnya.")
        return "\n".join(lines)

    def generate_sql_and_analysis(self, user_query: str, schema_context: str, history: list[dict] = None) -> dict:
        """
        Calls DeepSeek API to generate JSON containing SQL query, explanation, and chart decision.
        Considers schema context and up to 10 recent conversation turns.
        """
        history_str = self._format_history_context(history or [])

        system_prompt = f"""Anda adalah pakar Data Analytics & SQL BigQuery untuk manajemen budget perusahaan.
Tugas Anda adalah mengonversi pertanyaan pengguna menjadi query BigQuery Standard SQL yang valid, efisien, dan aman.

{schema_context}

{history_str}

PETUNJUK KETAT:
1. Hasilkan HANYA query SELECT (read-only). Dilarang keras menggunakan DROP, DELETE, INSERT, UPDATE, ALTER.
2. Gunakan nama tabel lengkap dalam format SQL BigQuery sesuai skema yang diberikan (misal `{{project_id}}.{{dataset_id}}.{{table_name}}`). Jika terdapat lebih dari 1 dataset, pastikan mengacu ke dataset yang sesuai untuk tiap tabel. Anda diizinkan melakukan JOIN antar tabel/dataset jika diperlukan.
3. Jika pertanyaan pengguna bergantung pada konteks riwayat percakapan sebelumnya (misal "bagaimana dengan sisa anggarannya?"), manfaatkan informasi dari riwayat untuk melengkapi query SQL.
4. Selalu format jawaban Anda dalam struktur JSON valid tanpa sintaks markdown tambahan di luar JSON.
5. Jika pengguna menyapa, bertanya tentang kemampuan Anda, atau membuat percakapan umum:
       Jawablah dengan ramah dan jelaskan secara singkat analisis data apa saja yang bisa Anda lakukan berdasarkan tabel BigQuery yang tersedia.

FORMAT JSON OUTPUT YANG WAJIB DIKEMBALIKAN:
{{
  "sql_query": "SELECT Departemen, SUM(Jumlah_Budget) as total_budget FROM ... GROUP BY 1",
  "explanation": "Penjelasan singkat pendekatan analisis dan logika SQL dalam bahasa Indonesia.",
  "generate_chart": true,
  "chart_type": "bar",
  "chart_title": "Perbandingan Total Budget per Departemen",
  "x_column": "Departemen",
  "y_column": "total_budget"
}}

Jika user meminta chart/grafik secara eksplisit (misal ada kata 'grafik', 'chart', 'tampilkan visual', 'tren'), set `generate_chart`: true dan tentukan type (`bar`, `line`, `pie`).
Jika data tidak cocok untuk chart (misal hanya 1 angka single KPI), set `generate_chart`: false.
"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_query}
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )

            raw_content = response.choices[0].message.content.strip()
            result = json.loads(raw_content)
            return result

        except Exception as e:
            logger.error(f"DeepSeek API Error: {e}")
            return {
                "sql_query": "",
                "explanation": f"Gagal menghasilkan SQL dari DeepSeek API: {str(e)}",
                "generate_chart": False,
                "chart_type": "none",
                "chart_title": "",
                "x_column": "",
                "y_column": ""
            }

    def summarize_results(self, user_query: str, sql_query: str, df: "pd.DataFrame | str", history: list[dict] = None) -> str:
        """Summarizes query results in conversational Indonesian with exact mathematical totals and context."""
        import pandas as pd
        history_str = self._format_history_context(history or [])

        stats_lines = []
        if isinstance(df, pd.DataFrame) and not df.empty:
            total_rows = len(df)
            stats_lines.append(f"Total Baris / Transaksi Keseluruhan: {total_rows} baris")
            
            # Compute exact sums for any numeric columns
            num_cols = df.select_dtypes(include=["number"]).columns
            for col in num_cols:
                col_sum = df[col].sum()
                if "tahun" not in col.lower() and "bulan" not in col.lower() and "id" not in col.lower() and "quantity" not in col.lower():
                    stats_lines.append(f"Total {col}: Rp {col_sum:,.2f} ({col_sum:,.0f})")
                elif "quantity" in col.lower() or "qty" in col.lower():
                    stats_lines.append(f"Total {col}: {col_sum:,.2f}")

            # Prepare table snippet
            if len(df) <= 50:
                table_str = df.to_string(index=False)
            else:
                table_str = df.head(50).to_string(index=False) + f"\n\n(Catatan: Menampilkan 50 dari total {total_rows} baris data lengkap)"
        else:
            table_str = str(df)

        stats_summary = "\n".join(stats_lines) if stats_lines else ""

        prompt = f"""{history_str}

Pertanyaan Pengguna Saat Ini: "{user_query}"
SQL yang Dieksekusi: `{sql_query}`

=== RINGKASAN STATISTIK AKURAT HASIL QUERY (DIHITUNG DARI SELURUH DATA) ===
{stats_summary}

=== DATA TABEL HASIL QUERY ===
{table_str}

PETUNJUK ANALISIS & FORMATTING DISCORD (SANGAT PENTING):
1. WAJIB gunakan angka 'Total Baris / Transaksi Keseluruhan' dan 'Total Nominal' yang tertera pada RINGKASAN STATISTIK AKURAT di atas sebagai angka acuan utama. Dilarang keras mengurangi atau menghitung ulang secara parsial.
2. ATURAN TABEL DISCORD (BATAS LEBAR MAKSIMAL 42 KARAKTER):
   - Layar Discord Embed SANGAT SEMPIT (maksimal ~45 karakter). Jika tabel terlalu lebar, Discord akan memotong teks ke baris baru dan membuat tabel berantakan!
   - JANGAN menulis kata 'Rp' atau '(IDR)' berulang-ulang di setiap kolom tabel. Gunakan singkatan nominal ringkas (M = Juta, K = Ribu) atau tulis satuan di header saja.
   - JANGAN PERNAH membuat garis tabel lebih lebar dari 42 karakter.
   
   Contoh Tabel Perbandingan (LEBAR PAS 40-42 KARAKTER):
```text
Item               Q2       Q1    Selisih
─────────────────────────────────────────
Oli Vacuum      4.64M    1.00M    +3.64M
Carbon Active   1.78M        0    +1.78M
Kawat Heater     600K        0     +600K
Resin Softener   575K        0     +575K
Vanbelt          348K     285K      +63K
Bearing          210K     212K       -2K
─────────────────────────────────────────
TOTAL           9.18M    1.72M    +7.46M
```
   - Alternatif: Untuk data yang panjang, gunakan Format List/Card berstruktur:
     1. 🔹 **Oli Vacuum** — Q2: `Rp 4.640.000` | Q1: `Rp 1.000.000` (Selisih: `+Rp 3.640.000`)
     2. 🔹 **Carbon Active** — Q2: `Rp 1.778.519` | Q1: `Rp 0` (Selisih: `+Rp 1.778.519`)
3. Sebutkan rincian item-item pembelian utama atau pengeluaran terbesar, serta total nominal yang tepat (format Rupiah IDR).
4. Jika ada insight penting atau anomali (misal dominasi item tertentu), sampaikan secara ringkas dan konstruktif."""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Anda adalah asisten keuangan Discord yang membantu menganalisis data budget dan transaksi perusahaan secara akurat."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            return f"Data berhasil diambil ({len(df) if isinstance(df, pd.DataFrame) else ''} baris), namun analisis teks mengalami kendala: {e}"
