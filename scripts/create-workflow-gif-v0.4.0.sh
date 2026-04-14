#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

SCREENSHOTS_DIR="$REPO_ROOT/docs-site/static/img/screenshots"
OUTPUT="$REPO_ROOT/docs-site/static/img/opentranscribe-workflow.gif"

echo "Building OpenTranscribe workflow GIF (v0.4.0)..."
echo "Source: $SCREENSHOTS_DIR"
echo "Output: $OUTPUT"

convert \
  -delay 80  "$SCREENSHOTS_DIR/auth/login-empty.png" \
  -delay 120 "$SCREENSHOTS_DIR/auth/login-filled.png" \
  -delay 100 "$SCREENSHOTS_DIR/auth/register.png" \
  -delay 250 "$SCREENSHOTS_DIR/gallery/gallery-overview.png" \
  -delay 150 "$SCREENSHOTS_DIR/upload/upload-file-drop.png" \
  -delay 200 "$SCREENSHOTS_DIR/upload/upload-settings-step.png" \
  -delay 150 "$SCREENSHOTS_DIR/upload/upload-url.png" \
  -delay 150 "$SCREENSHOTS_DIR/workflow/notifications-panel.png" \
  -delay 180 "$SCREENSHOTS_DIR/workflow/notifications-multiple.png" \
  -delay 250 "$SCREENSHOTS_DIR/transcript/file-detail-video.png" \
  -delay 180 "$SCREENSHOTS_DIR/transcript/file-detail-bottom.png" \
  -delay 250 "$SCREENSHOTS_DIR/speakers/speaker-editor-panel.png" \
  -delay 180 "$SCREENSHOTS_DIR/transcript/file-detail-tags.png" \
  -delay 150 "$SCREENSHOTS_DIR/transcript/file-detail-collections.png" \
  -delay 150 "$SCREENSHOTS_DIR/transcript/file-detail-collections-expanded.png" \
  -delay 200 "$SCREENSHOTS_DIR/info/file-details-tab.png" \
  -delay 200 "$SCREENSHOTS_DIR/transcript/transcript-full.png" \
  -delay 300 "$SCREENSHOTS_DIR/ai-features/ai-summary.png" \
  -delay 120 "$SCREENSHOTS_DIR/transcript/export-options.png" \
  -delay 100 "$SCREENSHOTS_DIR/search/search-empty.png" \
  -delay 220 "$SCREENSHOTS_DIR/search/search-results.png" \
  -delay 250 "$SCREENSHOTS_DIR/speakers/speaker-management-clusters.png" \
  -delay 180 "$SCREENSHOTS_DIR/info/file-status-errors.png" \
  -delay 130 "$SCREENSHOTS_DIR/info/file-status-completed.png" \
  -delay 180 "$SCREENSHOTS_DIR/info/about-dialog.png" \
  -delay 220 "$SCREENSHOTS_DIR/settings/settings-system-stats.png" \
  -delay 180 "$SCREENSHOTS_DIR/settings/settings-llm-config.png" \
  -delay 180 "$SCREENSHOTS_DIR/settings/settings-data-integrity.png" \
  -resize 1280x \
  -loop 0 \
  -layers Optimize \
  "$OUTPUT"

FRAME_COUNT=28
TOTAL_CS=$(( 80+120+100+250+150+200+150+150+180+250+180+250+180+150+150+200+200+300+120+100+220+250+180+130+180+220+180+180 ))
TOTAL_S=$(echo "scale=1; $TOTAL_CS / 100" | bc)
FILE_SIZE=$(du -h "$OUTPUT" | cut -f1)

echo ""
echo "GIF created successfully!"
echo "  Frames:   $FRAME_COUNT"
echo "  Duration: ${TOTAL_S}s (${TOTAL_CS} centiseconds)"
echo "  Size:     $FILE_SIZE"
echo "  Output:   $OUTPUT"
