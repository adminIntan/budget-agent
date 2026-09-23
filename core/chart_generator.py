import io
import logging
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend for server rendering
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import seaborn as sns

logger = logging.getLogger(__name__)

class ChartGenerator:
    """Generates styled charts from pandas DataFrames formatted for Discord attachments."""

    def __init__(self):
        # Configure sleek modern dark theme fitting Discord UI
        plt.style.use("dark_background")
        sns.set_theme(style="darkgrid", palette="deep")

    def _format_val(self, val: float) -> str:
        """Formats numbers into compact K/M/B representation."""
        if pd.isnull(val):
            return ""
        abs_val = abs(val)
        if abs_val >= 1_000_000_000:
            return f"{val/1_000_000_000:.1f}B"
        elif abs_val >= 1_000_000:
            return f"{val/1_000_000:.1f}M" if abs_val >= 10_000_000 else f"{val/1_000_000:.2f}M"
        elif abs_val >= 1_000:
            return f"{val/1_000:.0f}K" if abs_val >= 10_000 else f"{val/1_000:.1f}K"
        elif abs_val == 0:
            return "0"
        return f"{val:.1f}"

    def generate_chart(
        self,
        df: pd.DataFrame,
        chart_type: str,
        title: str,
        x_col: str,
        y_col: str
    ) -> io.BytesIO | None:
        """
        Renders a chart (grouped bar, single bar, line, pie) into an in-memory BytesIO image buffer.
        Automatically detects multi-period comparisons for side-by-side grouped bars.
        """
        if df is None or df.empty:
            return None

        # Detect text/category columns and numeric columns
        text_cols = [c for c in df.columns if df[c].dtype == "object" or df[c].dtype == "string"]
        num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) and "tahun" not in c.lower() and "bulan" not in c.lower() and "id" not in c.lower()]

        if not text_cols and not num_cols:
            return None

        # Choose primary X column
        if x_col not in df.columns:
            x_col = text_cols[0] if text_cols else df.columns[0]

        # Identify numeric comparison columns (exclude diff/selisih columns from bar height comparison)
        comp_cols = [c for c in num_cols if "selisih" not in c.lower() and "diff" not in c.lower() and "persen" not in c.lower() and "%" not in c]
        if not comp_cols:
            comp_cols = num_cols

        # Limit to top 10 items for readability
        plot_df = df.head(10).copy()

        fig, ax = plt.subplots(figsize=(11, 6), dpi=130)
        fig.patch.set_facecolor("#1e1f22")  # Discord dark background tone
        ax.set_facecolor("#2b2d31")

        try:
            chart_type = (chart_type or "bar").lower()

            if chart_type == "pie":
                target_y = y_col if y_col in df.columns else (comp_cols[0] if comp_cols else num_cols[0])
                pie_data = plot_df.groupby(x_col)[target_y].sum().head(7)
                colors = sns.color_palette("viridis", len(pie_data))
                ax.pie(
                    pie_data.values,
                    labels=pie_data.index,
                    autopct="%1.1f%%",
                    startangle=140,
                    colors=colors,
                    textprops={"color": "white", "fontsize": 10, "weight": "bold"}
                )
                ax.set_title(title or "Distribusi Data Budget", color="#00d26a", fontsize=14, pad=15, weight="bold")

            elif chart_type == "line":
                target_y = y_col if y_col in df.columns else (comp_cols[0] if comp_cols else num_cols[0])
                sns.lineplot(data=plot_df, x=x_col, y=target_y, ax=ax, marker="o", color="#5865f2", linewidth=2.5, markersize=8)
                ax.set_title(title or f"Tren {target_y}", color="#5865f2", fontsize=14, pad=15, weight="bold")
                plt.xticks(rotation=25, ha="right", color="white")
                plt.yticks(color="white")
                ax.set_xlabel(x_col.replace("_", " ").title(), color="#b5bac1", fontsize=11)
                ax.set_ylabel(target_y.replace("_", " ").title(), color="#b5bac1", fontsize=11)

            else:  # Bar Chart (Grouped Bar or Single Bar)
                # Check if this is a Multi-Series / Multi-Quarter comparison (>= 2 comparison numeric columns)
                if len(comp_cols) >= 2:
                    melted = plot_df.melt(
                        id_vars=[x_col],
                        value_vars=comp_cols,
                        var_name="Kategori / Periode",
                        value_name="Nominal"
                    )
                    # Clean up period names (e.g. Total_Q2 -> Q2)
                    melted["Kategori / Periode"] = melted["Kategori / Periode"].str.replace("Total_", "").str.replace("_", " ")

                    palette = ["#5865f2", "#00d26a", "#f38630", "#a855f7"][:len(comp_cols)]
                    sns.barplot(
                        data=melted,
                        x=x_col,
                        y="Nominal",
                        hue="Kategori / Periode",
                        ax=ax,
                        palette=palette
                    )
                    ax.legend(title="Periode", facecolor="#1e1f22", edgecolor="#3f4147", labelcolor="white")
                else:
                    target_y = y_col if y_col in df.columns else (comp_cols[0] if comp_cols else num_cols[0])
                    sns.barplot(data=plot_df, x=x_col, y=target_y, ax=ax, palette="Blues_r", hue=x_col, legend=False)

                ax.set_title(title or "Perbandingan Data", color="#00a8fc", fontsize=14, pad=15, weight="bold")
                plt.xticks(rotation=25, ha="right", color="white", fontsize=10)
                plt.yticks(color="white", fontsize=10)
                ax.set_xlabel(x_col.replace("_", " ").title(), color="#b5bac1", fontsize=11, labelpad=10)
                ax.set_ylabel("Nominal (IDR)", color="#b5bac1", fontsize=11)

                # Format Y-Axis with clean M / K / B instead of scientific 1e6 notation
                ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, pos: self._format_val(x)))

                # Add value labels on top of each bar
                for p in ax.patches:
                    height = p.get_height()
                    if pd.notnull(height) and height > 0:
                        formatted_lbl = self._format_val(height)
                        ax.annotate(
                            formatted_lbl,
                            (p.get_x() + p.get_width() / 2., height),
                            ha="center", va="bottom",
                            fontsize=8.5, color="white", weight="bold",
                            xytext=(0, 3),
                            textcoords="offset points"
                        )

            plt.tight_layout()

            buffer = io.BytesIO()
            plt.savefig(buffer, format="png", bbox_inches="tight", facecolor=fig.get_facecolor())
            buffer.seek(0)
            plt.close(fig)
            return buffer

        except Exception as e:
            logger.error(f"Error generating chart: {e}")
            plt.close(fig)
            return None
