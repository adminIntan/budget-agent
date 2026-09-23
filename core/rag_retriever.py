import json
import os
import logging

logger = logging.getLogger(__name__)

class RAGRetriever:
    """Retrieves relevant table schemas and business context for LLM prompt context."""

    def __init__(self, schema_file_path: str = None):
        if schema_file_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            schema_file_path = os.path.join(base_dir, "sample_data", "schema_definition.json")
        
        self.schema_file_path = schema_file_path
        self.schema_data = self._load_schema()

    def _load_schema(self) -> dict:
        if os.path.exists(self.schema_file_path):
            try:
                with open(self.schema_file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error reading schema file {self.schema_file_path}: {e}")
        return {"tables": [], "business_rules": []}

    def _get_datasets(self, dataset_id: str = None) -> list[str]:
        """Parses dataset IDs from parameter or BIGQUERY_DATASETS/BIGQUERY_DATASET env vars."""
        raw_ds = dataset_id or os.getenv("BIGQUERY_DATASETS") or os.getenv("BIGQUERY_DATASET", "budget_dataset")
        datasets = [d.strip() for d in raw_ds.split(",") if d.strip()]
        return datasets if datasets else ["budget_dataset"]

    def _get_allowed_tables(self) -> set[str] | None:
        """Reads BIGQUERY_ALLOWED_TABLES from environment variables if defined."""
        allowed_env = os.getenv("BIGQUERY_ALLOWED_TABLES", "").strip()
        if allowed_env:
            return {t.strip().lower() for t in allowed_env.split(",") if t.strip()}
        return None  # None means all tables in schema are allowed

    def _is_table_allowed(self, table_name: str, table_dataset: str, proj: str, allowed_tables: set[str] | None) -> bool:
        """Checks if a table is allowed based on table name, dataset.table, or project.dataset.table."""
        if allowed_tables is None:
            return True
        t_name_lower = table_name.lower()
        t_ds_lower = table_dataset.lower()
        proj_lower = proj.lower()
        
        return (
            t_name_lower in allowed_tables
            or f"{t_ds_lower}.{t_name_lower}" in allowed_tables
            or f"{proj_lower}.{t_ds_lower}.{t_name_lower}" in allowed_tables
        )

    def get_prompt_context(self, user_query: str, project_id: str = None, dataset_id: str = None) -> str:
        """
        Formats schema tables, column types, descriptions, and business rules into a markdown string.
        Supports single or multiple datasets and filters tables based on BIGQUERY_ALLOWED_TABLES.
        """
        proj = project_id or os.getenv("GCP_PROJECT_ID", "your_project_id")
        datasets = self._get_datasets(dataset_id)
        default_ds = datasets[0] if datasets else "budget_dataset"
        allowed_tables = self._get_allowed_tables()

        context_lines = [
            "=== TARGET BIGQUERY PROJECT & DATASETS ===",
            f"Project ID: `{proj}`",
            f"Dataset(s): {', '.join([f'`{d}`' for d in datasets])}",
            f"Format Nama Tabel: `{proj}.<dataset>.<nama_tabel>`",
            "Catatan: Anda dapat melakukan query SELECT atau JOIN antar tabel/dataset yang terdaftar di bawah ini.",
            "",
            "=== DEFINISI SKEMA TABEL BIGQUERY ==="
        ]

        included_count = 0
        for table in self.schema_data.get("tables", []):
            t_name = table.get("table_name", "").strip()
            # If table specifies its own dataset, use it; otherwise fallback to default dataset
            t_dataset = table.get("dataset") or default_ds
            
            # Filter tables if BIGQUERY_ALLOWED_TABLES is set
            if not self._is_table_allowed(t_name, t_dataset, proj, allowed_tables):
                continue

            included_count += 1
            table_full_name = f"`{proj}.{t_dataset}.{t_name}`"
            context_lines.append(f"\nTabel: {table_full_name}")
            if table.get("dataset"):
                context_lines.append(f"Dataset: `{t_dataset}`")
            context_lines.append(f"Deskripsi: {table.get('description', '')}")
            context_lines.append("Kolom-kolom:")
            for col in table.get("columns", []):
                context_lines.append(f"  - `{col['name']}` ({col['type']}): {col.get('description', '')}")

        if included_count == 0:
            context_lines.append("\n(Catatan: Tidak ada tabel yang lolos filter BIGQUERY_ALLOWED_TABLES atau schema_definition.json kosong)")

        context_lines.append("\n=== ATURAN METRIK & BISNIS ===")
        for rule in self.schema_data.get("business_rules", []):
            context_lines.append(f"- {rule}")

        return "\n".join(context_lines)
