#!/bin/bash
# Create workflow GIF with 0.9 seconds per frame

SOURCE_DIR="OpenTranscribe-gif"
OUTPUT_FILE="docs-site/static/img/opentranscribe-workflow.gif"

echo "Creating GIF with 0.9 seconds per frame..."

# Create GIF with 0.9 second delay (90 centiseconds)
convert "$SOURCE_DIR"/*.png \
  -set delay 90 \
  -dispose previous \
  -loop 0 \
  -resize 1280x \
  -layers Optimize \
  "$OUTPUT_FILE"

if [ -f "$OUTPUT_FILE" ]; then
  SIZE=$(du -h "$OUTPUT_FILE" | cut -f1)
  FRAME_COUNT=$(ls -1 "$SOURCE_DIR"/*.png | wc -l)
  DURATION=$(echo "$FRAME_COUNT * 0.9" | bc)
  echo ""
  echo "✅ GIF created successfully!"
  echo "   File: opentranscribe-workflow.gif"
  echo "   Size: $SIZE"
  echo "   Frames: $FRAME_COUNT"
  echo "   Speed: 0.9 seconds per frame"
  echo "   Total Duration: ~${DURATION}s"
else
  echo "❌ Failed to create GIF"
  exit 1
fi
