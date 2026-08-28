#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_DIR="${OUTPUT_DIR:-$ROOT_DIR/handoff}"
STAMP="${HANDOFF_DATE:-$(date +%Y%m%d)}"
ARCHIVE_NAME="chatbot-hocvu-ctut-${STAMP}.tar.gz"
ARCHIVE_PATH="$OUTPUT_DIR/$ARCHIVE_NAME"
CHECKSUM_PATH="$OUTPUT_DIR/$ARCHIVE_NAME.sha256"
ZIP_NAME="chatbot-hocvu-ctut-${STAMP}.zip"
ZIP_PATH="$OUTPUT_DIR/$ZIP_NAME"
ZIP_CHECKSUM_PATH="$OUTPUT_DIR/$ZIP_NAME.sha256"
WORK_DIR="$(mktemp -d)"
STAGING_DIR="$WORK_DIR/chatbot-hocvu"

cleanup() {
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT

mkdir -p "$OUTPUT_DIR" "$STAGING_DIR"

tar -C "$ROOT_DIR" -cf - \
  --exclude='./.env' \
  --exclude='./.env.local' \
  --exclude='./frontend/.env.local' \
  --exclude='./.git' \
  --exclude='./.venv' \
  --exclude='./venv' \
  --exclude='./env' \
  --exclude='./frontend/node_modules' \
  --exclude='./frontend/.next' \
  --exclude='./frontend/next-env.d.ts' \
  --exclude='./frontend/tsconfig.tsbuildinfo' \
  --exclude='./node_modules' \
  --exclude='./qdrant_storage' \
  --exclude='./data/app.db' \
  --exclude='./data/processed' \
  --exclude='./logs' \
  --exclude='./.pytest_cache' \
  --exclude='./__pycache__' \
  --exclude='*/__pycache__' \
  --exclude='./DA08-VSF-AI' \
  --exclude='./handoff' \
  --exclude='./chunks_debug.json' \
  --exclude='./login.png' \
  --exclude='./testchunk.py' \
  . | tar -C "$STAGING_DIR" -xf -

if find "$STAGING_DIR" -type f \( -name '.env' -o -name '*.pem' -o -name '*.key' \) -print -quit | grep -q .; then
  echo "Refusing to package secret-like files." >&2
  exit 1
fi

tar -C "$WORK_DIR" -czf "$ARCHIVE_PATH" chatbot-hocvu
sha256sum "$ARCHIVE_PATH" | tee "$CHECKSUM_PATH"
rm -f "$ZIP_PATH" "$ZIP_CHECKSUM_PATH"
(cd "$WORK_DIR" && zip -qr "$ZIP_PATH" chatbot-hocvu)
sha256sum "$ZIP_PATH" | tee "$ZIP_CHECKSUM_PATH"

echo "Created: $ARCHIVE_PATH"
echo "Size: $(du -h "$ARCHIVE_PATH" | cut -f1)"
echo "Created: $ZIP_PATH"
echo "Size: $(du -h "$ZIP_PATH" | cut -f1)"
