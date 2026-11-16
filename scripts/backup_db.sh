#!/usr/bin/env bash
set -e

echo "========================================================"
echo "AI-Agent-ChatBot: PostgreSQL + pgvector Database Backup"
echo "========================================================"

mkdir -p backups
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="backups/backup_agent_chatbot_${TIMESTAMP}.sql"

echo "Exporting database from Docker container 'agent_chatbot_db'..."
docker exec -t agent_chatbot_db pg_dump -U postgres agent_chatbot > "${BACKUP_FILE}"

echo ""
echo "========================================================"
echo "[SUCCESS] Database backup created successfully!"
echo "Location: ${BACKUP_FILE}"
echo "========================================================"
