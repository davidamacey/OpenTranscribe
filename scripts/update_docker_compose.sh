#!/bin/bash
# This script adds WhisperX configuration to the celery-worker service in docker-compose.yml

# Position to insert new variables after USE_GPU=true
INSERT_LINE=$(grep -n 'USE_GPU=true' /mnt/nvm/repos/transcribe-app/docker-compose.yml | head -1 | cut -d':' -f1)

if [ -z "$INSERT_LINE" ]; then
    echo "Error: Could not find 'USE_GPU=true' in docker-compose.yml"
    exit 1
fi

# Create a temporary file
TMP_FILE=$(mktemp)

# Copy content up to the insertion point
head -n $INSERT_LINE /mnt/nvm/repos/transcribe-app/docker-compose.yml > $TMP_FILE

# Add new environment variables
cat << 'EOF' >> $TMP_FILE
      - HUGGINGFACE_TOKEN=${HUGGINGFACE_TOKEN:-}
      - WHISPER_MODEL=large-v2
      - BATCH_SIZE=16
      - COMPUTE_TYPE=float16
      - DIARIZATION_MODEL=pyannote/speaker-diarization-3.1
      - MIN_SPEAKERS=1
      - MAX_SPEAKERS=10
EOF

# Copy the rest of the file
tail -n +$((INSERT_LINE+1)) /mnt/nvm/repos/transcribe-app/docker-compose.yml >> $TMP_FILE

# Move the temporary file to the original
mv $TMP_FILE /mnt/nvm/repos/transcribe-app/docker-compose.yml

echo "Docker Compose file updated with WhisperX configuration"
