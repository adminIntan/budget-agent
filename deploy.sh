#!/bin/bash
set -e

# ==============================================================================
# Google Cloud Run 1-Click Deployment Script for Budget Agent Discord Bot
# ==============================================================================

SERVICE_NAME="budget-discord-bot"
REGION="asia-east1" # Taiwan region (low latency)

echo "🚀 Memulai Deployment Budget Discord Bot ke Google Cloud Run..."

# Ensure gcloud CLI is authenticated and project is set
if [ -z "$GCP_PROJECT_ID" ]; then
    echo "⚠️ VAR GCP_PROJECT_ID belum di-set di environment lokal."
    read -p "Masukkan GCP Project ID Anda: " GCP_PROJECT_ID
fi

gcloud config set project "$GCP_PROJECT_ID"

echo "📦 Building container image & Deploying to Cloud Run..."
gcloud run deploy "$SERVICE_NAME" \
  --source . \
  --region "$REGION" \
  --no-cpu-throttling \
  --min-instances 1 \
  --max-instances 2 \
  --allow-unauthenticated \
  --set-env-vars GCP_PROJECT_ID="$GCP_PROJECT_ID"

echo "✅ Deployment Selesai!"
echo "📌 Catatan: Pastikan Environment Variables DISCORD_TOKEN & DEEPSEEK_API_KEY telah di-set di Cloud Run Console atau via flag --set-env-vars!"
