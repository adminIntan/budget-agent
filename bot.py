import os
import sys
import logging
import asyncio
import discord
from dotenv import load_dotenv
from threading import Thread
from flask import Flask

# Load environment variables
load_dotenv()

from core.bq_client import BigQueryClientManager
from core.rag_retriever import RAGRetriever
from core.sql_generator import DeepSeekSQLGenerator
from core.chart_generator import ChartGenerator
from core.memory_manager import FirestoreMemoryManager

# --- 1. FLASK HEALTH CHECK SERVER (untuk Cloud Run) ---
flask_app = Flask(__name__)

@flask_app.route('/')
def health_check():
    return "OK", 200

def run_health_check_server():
    # Cloud Run menyuntikkan PORT=8080, lokal fallback ke 8080 juga
    port = int(os.environ.get('PORT', 8080))
    flask_app.run(host='0.0.0.0', port=port)


# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("BudgetBot")

# Initialize Discord Intents
intents = discord.Intents.default()
intents.message_content = True  # Required to read mention text

client = discord.Client(intents=intents)

# Initialize Core Services
bq_manager = BigQueryClientManager()
rag_retriever = RAGRetriever()
sql_generator = DeepSeekSQLGenerator()
chart_generator = ChartGenerator()
memory_manager = FirestoreMemoryManager()

def _get_allowed_channels() -> set[str] | None:
    """Reads DISCORD_ALLOWED_CHANNELS from env. If set, restricts guild messages to these channels."""
    env_channels = os.getenv("DISCORD_ALLOWED_CHANNELS", "").strip()
    if env_channels:
        return {c.strip() for c in env_channels.split(",") if c.strip()}
    return None

def _get_allowed_users() -> set[str] | None:
    """Reads DISCORD_ALLOWED_USERS from env (comma-separated user IDs)."""
    env_val = os.getenv("DISCORD_ALLOWED_USERS", "").strip()
    if env_val:
        return {u.strip() for u in env_val.split(",") if u.strip()}
    return None

def _get_allowed_roles() -> set[str] | None:
    """Reads DISCORD_ALLOWED_ROLES from env (comma-separated role IDs or role names, case-insensitive)."""
    env_val = os.getenv("DISCORD_ALLOWED_ROLES", "").strip()
    if env_val:
        return {r.strip().lower() for r in env_val.split(",") if r.strip()}
    return None

def _is_user_authorized(message: discord.Message) -> bool:
    """
    Checks if message author is authorized via User ID whitelist or Role whitelist.
    If both whitelists are empty, access is open to all.
    """
    allowed_users = _get_allowed_users()
    allowed_roles = _get_allowed_roles()

    # If neither user nor role restrictions are configured, allow access
    if not allowed_users and not allowed_roles:
        return True

    # Check 1: Whitelisted User ID
    user_id_str = str(message.author.id)
    if allowed_users and user_id_str in allowed_users:
        return True

    # Check 2: Server Role (applicable in guild channels)
    if allowed_roles and hasattr(message.author, "roles"):
        for role in message.author.roles:
            if str(role.id) in allowed_roles or role.name.lower() in allowed_roles:
                return True

    return False

@client.event
async def on_ready():
    logger.info(f"Bot connected as: {client.user.name} (ID: {client.user.id})")
    allowed = _get_allowed_channels()
    if allowed:
        logger.info(f"Channel filter active: Allowed guild channels = {allowed} (Direct Messages are also allowed)")
    else:
        logger.info("Channel filter: All channels allowed.")

    users = _get_allowed_users()
    roles = _get_allowed_roles()
    if users or roles:
        logger.info(f"Hybrid Auth active -> Allowed Users: {users or 'None'}, Allowed Roles: {roles or 'None'}")
    else:
        logger.info("Hybrid Auth: Open access (no user/role restrictions configured).")

    logger.info("Ready to answer budget questions on Discord channel mentions & DMs!")

@client.event
async def on_message(message: discord.Message):
    # Ignore self messages
    if message.author == client.user:
        return

    is_dm = isinstance(message.channel, discord.DMChannel) or message.guild is None

    # Channel check for server/guild channels
    if not is_dm:
        allowed_channels = _get_allowed_channels()
        if allowed_channels and str(message.channel.id) not in allowed_channels:
            return  # Silently ignore messages outside allowed channels

        # In server channels, require bot mention
        if client.user not in message.mentions:
            return

    # Check User & Role Authorization
    if not _is_user_authorized(message):
        await message.reply("⛔ **Akses Ditolak:** Anda belum memiliki izin untuk mengakses data budget.")
        return

    # Clean the query string (remove @mention if present)
    clean_query = message.content.replace(f"<@{client.user.id}>", "").replace(f"<@!{client.user.id}>", "").strip()

    if not clean_query:
        prefix = "" if is_dm else "@BudgetBot "
        await message.reply(
            "Halo! Ada yang bisa saya bantu terkait data budget?\n"
            "Contoh pertanyaan:\n"
            f"- *{prefix}Berapa total realisasi pengeluaran departemen IT tahun 2026?*\n"
            f"- *{prefix}Tampilkan grafik perbandingan budget vs aktual per divisi*"
        )
        return

    location_desc = f"DM ({message.author})" if is_dm else f"channel {message.channel.id} (guild: {message.guild.name})"
    logger.info(f"Received query from {message.author} in {location_desc}: {clean_query}")

    # Use channel ID or user DM ID as session_id to maintain conversation memory
    session_id = f"dm_{message.author.id}" if is_dm else f"channel_{message.channel.id}"

    # Trigger typing indicator in Discord channel
    async with message.channel.typing():
        try:
            # Step 1: Fetch recent 10 conversation turns from Firestore
            history = await asyncio.to_thread(memory_manager.get_recent_history, session_id, limit=10)

            # Step 2: Retrieve RAG Schema & Context
            schema_context = rag_retriever.get_prompt_context(
                user_query=clean_query,
                project_id=bq_manager.project_id,
                dataset_id=bq_manager.dataset_id
            )

            # Step 3: Generate SQL & Analytics plan via DeepSeek API with memory
            sql_plan = await asyncio.to_thread(
                sql_generator.generate_sql_and_analysis,
                user_query=clean_query,
                schema_context=schema_context,
                history=history
            )

            sql_query = sql_plan.get("sql_query", "")
            explanation = sql_plan.get("explanation", "")
            should_chart = sql_plan.get("generate_chart", False)

            if not sql_query:
                embed_help = discord.Embed(
                    title="💬 Budget Analytics Assistant",
                    description=explanation,
                    color=discord.Color.blue()
                )
                embed_help.set_footer(text=f"Diminta oleh {message.author.display_name} • Powered by DeepSeek & BigQuery")
                await message.reply(embed=embed_help)
                return

            # Step 4: Execute SQL in BigQuery
            df, bq_error = await asyncio.to_thread(bq_manager.execute_query, sql_query)

            if bq_error:
                embed_err = discord.Embed(
                    title="⚠️ Kendala Pengambilan Data",
                    description="Terjadi kendala teknis saat memproses data di BigQuery. Silakan coba kembali atau formulasikan pertanyaan Anda.",
                    color=discord.Color.red()
                )
                await message.reply(embed=embed_err)
                return

            if df is None or df.empty:
                await message.reply(
                    f"ℹ️ **Hasil Data Kosong**\n"
                    f"Tanya: *{clean_query}*\n\n"
                    f"Tidak ditemukan data yang sesuai dengan kriteria pertanyaan Anda."
                )
                return

            # Step 5: Summarize Data Results into Natural Language
            summary_text = await asyncio.to_thread(
                sql_generator.summarize_results,
                user_query=clean_query,
                sql_query=sql_query,
                df=df,
                history=history
            )

            # Save interaction turn to Firestore / In-Memory cache
            await asyncio.to_thread(
                memory_manager.add_interaction,
                session_id=session_id,
                user_query=clean_query,
                bot_response=summary_text,
                sql_query=sql_query,
                limit=10
            )

            # Build Embed Message for Discord (Answers and Charts only)
            embed = discord.Embed(
                title="📊 Budget Analytics & Insights",
                description=summary_text,
                color=discord.Color.blue()
            )
            embed.set_footer(text=f"Diminta oleh {message.author.display_name} • Powered by DeepSeek & BigQuery")

            # Step 6: Generate Chart if requested/applicable
            chart_file = None
            if should_chart or any(k in clean_query.lower() for k in ["chart", "grafik", "visual", "tren"]):
                chart_type = sql_plan.get("chart_type", "bar")
                chart_title = sql_plan.get("chart_title", "Visualisasi Data Budget")
                x_col = sql_plan.get("x_column", "")
                y_col = sql_plan.get("y_column", "")

                buf = await asyncio.to_thread(
                    chart_generator.generate_chart,
                    df=df,
                    chart_type=chart_type,
                    title=chart_title,
                    x_col=x_col,
                    y_col=y_col
                )

                if buf:
                    chart_file = discord.File(fp=buf, filename="budget_chart.png")
                    embed.set_image(url="attachment://budget_chart.png")

            # Step 7: Reply to User in Discord
            if chart_file:
                await message.reply(embed=embed, file=chart_file)
            else:
                await message.reply(embed=embed)

        except Exception as e:
            logger.error(f"Unexpected error handling message: {e}", exc_info=True)
            await message.reply(f"💥 **Terjadi kesalahan sistem:** `{str(e)}`")

def main():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        logger.critical("DISCORD_TOKEN env var is missing! Exiting...")
        sys.exit(1)

    # Jalankan Flask health check server di background thread (WAJIB untuk Cloud Run)
    flask_thread = Thread(target=run_health_check_server, daemon=True)
    flask_thread.start()
    logger.info(f"Flask health check server started on PORT={os.environ.get('PORT', 8080)}")

    # Jalankan Discord bot di main thread (blocking)
    logger.info("Starting Discord bot...")
    client.run(token)

if __name__ == "__main__":
    main()

