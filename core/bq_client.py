import os
import logging
import pandas as pd
from google.cloud import bigquery
from google.api_core.exceptions import GoogleAPIError

logger = logging.getLogger(__name__)

class BigQueryClientManager:
    """Manages connection and query execution to Google BigQuery."""

    def __init__(self, project_id: str = None, dataset_id: str = None):
        self.project_id = project_id or os.getenv("GCP_PROJECT_ID")
        raw_ds = dataset_id or os.getenv("BIGQUERY_DATASETS") or os.getenv("BIGQUERY_DATASET", "")
        self.dataset_id = raw_ds
        self.datasets = [d.strip() for d in raw_ds.split(",") if d.strip()]
        
        try:
            # Client automatically retrieves credentials from environment/ADC (Cloud Run SA or GOOGLE_APPLICATION_CREDENTIALS)
            self.client = bigquery.Client(project=self.project_id)
            logger.info(f"BigQuery Client initialized for project: {self.project_id}")
        except Exception as e:
            logger.warning(f"Could not initialize live BigQuery client: {e}. Falling back to dry-run/mock mode.")
            self.client = None

    def execute_query(self, sql_query: str) -> tuple[pd.DataFrame | None, str | None]:
        """
        Executes a SQL query against BigQuery and returns (DataFrame, error_message).
        Includes safety validation to ensure read-only query execution.
        """
        if not sql_query or not sql_query.strip():
            return None, "Query SQL kosong."

        # Safety check: block non-SELECT statements
        clean_query = sql_query.strip().upper()
        forbidden_keywords = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE", "CREATE", "GRANT"]
        for kw in forbidden_keywords:
            if f" {kw} " in f" {clean_query} " or clean_query.startswith(kw):
                return None, f"Eksekusi ditolak: Perintah SQL '{kw}' tidak diizinkan."

        if not self.client:
            return None, "Koneksi BigQuery belum terkonfigurasi. Pastikan GCP_PROJECT_ID & kredensial valid."

        try:
            logger.info(f"Running BigQuery SQL: {sql_query}")
            query_job = self.client.query(sql_query)
            df = query_job.to_dataframe()
            return df, None
        except GoogleAPIError as e:
            logger.error(f"BigQuery API Error: {e}")
            return None, f"Error BigQuery SQL: {str(e)}"
        except Exception as e:
            logger.error(f"Execution Error: {e}")
            return None, f"Gagal mengeksekusi query: {str(e)}"

    def fetch_schema(self) -> str:
        """Fetches schema information from configured BigQuery dataset(s) if accessible."""
        if not self.client or not self.datasets:
            return ""

        schema_outputs = []
        try:
            for ds in self.datasets:
                query = f"""
                SELECT table_schema, table_name, column_name, data_type
                FROM `{self.project_id}.{ds}.INFORMATION_SCHEMA.COLUMNS`
                ORDER BY table_name, ordinal_position
                """
                df, err = self.execute_query(query)
                if df is not None and not df.empty:
                    schema_outputs.append(f"--- Dataset: {ds} ---\n" + df.to_string(index=False))
            if schema_outputs:
                return "\n\n".join(schema_outputs)
        except Exception as e:
            logger.warning(f"Failed to fetch live schema from BigQuery: {e}")
        return ""
