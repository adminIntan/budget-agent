import os
import sys
import json
import logging
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.rag_retriever import RAGRetriever
from core.sql_generator import DeepSeekSQLGenerator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Evaluator")

def evaluate_agent(benchmark_path: str = None):
    """
    Evaluates the Text-to-SQL Agent performance using a Confusion Matrix.

    Metrics Categories:
    - Actual Positive (1): Valid user query related to budget data.
    - Actual Negative (0): Invalid / Out-of-scope / Malicious query (e.g. DROP TABLE).

    Prediction Outcomes:
    - TP (True Positive): Valid query -> Agent successfully generated valid SQL SELECT.
    - FP (False Positive): Invalid/out-of-scope query -> Agent mistakenly generated SQL instead of rejecting.
    - FN (False Negative): Valid query -> Agent failed to generate SQL or produced invalid SQL.
    - TN (True Negative): Invalid query -> Agent correctly refused/failed to produce executable SQL.
    """
    if benchmark_path is None:
        benchmark_path = os.path.join(os.path.dirname(__file__), "benchmark_dataset.json")

    with open(benchmark_path, "r", encoding="utf-8") as f:
        benchmark_data = json.load(f)

    rag_retriever = RAGRetriever()
    sql_generator = DeepSeekSQLGenerator()
    schema_context = rag_retriever.get_prompt_context("eval")

    y_true = []
    y_pred = []
    results_detail = []

    print("\n🔍 Memulai Evaluasi Text-to-SQL Agent...\n" + "="*50)

    for test_case in benchmark_data:
        qid = test_case["id"]
        query = test_case["user_query"]
        is_valid = test_case["is_valid_query"]  # Actual Ground Truth (1 or 0)

        # Run SQL Generator
        plan = sql_generator.generate_sql_and_analysis(query, schema_context)
        generated_sql = plan.get("sql_query", "").strip()

        # Classification Rule:
        # Predicted Positive (1) if agent produced non-empty SELECT query.
        # Predicted Negative (0) if agent produced empty SQL or error.
        predicted_valid = 1 if generated_sql and generated_sql.upper().startswith("SELECT") else 0
        actual_valid = 1 if is_valid else 0

        y_true.append(actual_valid)
        y_pred.append(predicted_valid)

        # Categorize TP, FP, FN, TN
        if actual_valid == 1 and predicted_valid == 1:
            category = "TP (True Positive)"
        elif actual_valid == 0 and predicted_valid == 1:
            category = "FP (False Positive)"
        elif actual_valid == 1 and predicted_valid == 0:
            category = "FN (False Negative)"
        else:
            category = "TN (True Negative)"

        results_detail.append({
            "ID": qid,
            "Query": query,
            "Actual": "Valid" if actual_valid else "Invalid",
            "Predicted": "Valid" if predicted_valid else "Invalid",
            "Category": category,
            "SQL": generated_sql[:60] + "..." if generated_sql else "NONE"
        })

        print(f"[{category}] Q{qid}: '{query}' -> SQL: {generated_sql[:40]}...")

    # Calculate Confusion Matrix Metrics
    tp = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 1)
    fp = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 1)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 0)
    tn = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 0)

    total = len(y_true)
    accuracy = (tp + tn) / total if total > 0 else 0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1_score = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0

    print("\n" + "="*50)
    print("📊 METRIK EVALUASI HASIL CONFUSION MATRIX")
    print("="*50)
    print(f"True Positives  (TP) : {tp}")
    print(f"False Positives (FP) : {fp}")
    print(f"False Negatives (FN) : {fn}")
    print(f"True Negatives  (TN) : {tn}")
    print("-"*30)
    print(f"Accuracy  : {accuracy * 100:.2f}%")
    print(f"Precision : {precision * 100:.2f}%")
    print(f"Recall    : {recall * 100:.2f}%")
    print(f"F1-Score  : {f1_score * 100:.2f}%")
    print("="*50)

    # Plot Confusion Matrix Heatmap
    cm_data = [[tp, fn], [fp, tn]]
    fig, ax = plt.subplots(figsize=(6, 5), dpi=120)
    sns.heatmap(
        cm_data,
        annot=True,
        fmt="d",
        cmap="Blues",
        xticklabels=["Predicted Valid", "Predicted Invalid"],
        yticklabels=["Actual Valid", "Actual Invalid"],
        cbar=False,
        ax=ax
    )
    plt.title(f"Confusion Matrix Evaluation\nAccuracy: {accuracy*100:.1f}% | F1: {f1_score*100:.1f}%")
    plt.tight_layout()
    
    out_img_path = os.path.join(os.path.dirname(__file__), "confusion_matrix.png")
    plt.savefig(out_img_path)
    plt.close()
    print(f"\n🖼️ Grafik Confusion Matrix disimpan di: {out_img_path}")

if __name__ == "__main__":
    evaluate_agent()
