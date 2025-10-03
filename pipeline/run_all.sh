#!/usr/bin/env bash
# Runs process_localization.py for each subfolder of pictures/,
# updating .env for each run.

set -u -o pipefail

BASE="/home/kn-bit/programow/nvidia-geo-guessing/pipeline"
PICTURES_DIR="$BASE/pictures"
ENV_FILE="$BASE/.env"
LOG_DIR="$BASE/logs"

DEFAULT_OUTPUTS_PATH="/home/kn-bit/comfy/ComfyUI/output"
DEFAULT_FIND_MAX_FILE="/home/kn-bit/comfy/ComfyUI/temp/scores.txt"
SERVER_ADDRESS="127.0.0.1:8188"
WORKFLOW_FILE="pipeline_api.json"

mkdir -p "$LOG_DIR"

# Backup current .env (if it exists)
timestamp="$(date +%Y%m%d-%H%M%S)"
BACKUP="$ENV_FILE.bak.$timestamp"
if [[ -f "$ENV_FILE" ]]; then
  cp -f "$ENV_FILE" "$BACKUP"
  echo "Backed up .env to $BACKUP"
fi

# Ensure the glob doesn't pass a literal when no dirs exist
shopt -s nullglob

success_count=0
fail_count=0
ran_any=false

for dir in "$PICTURES_DIR"/*/; do
  [[ -d "$dir" ]] || continue
  ran_any=true
  folder_name="$(basename "$dir")"

  before_path="$PICTURES_DIR/$folder_name/before"
  after_path="$PICTURES_DIR/$folder_name/after"

  # Create before/after if they don't exist (harmless if already there)
  mkdir -p "$before_path" "$after_path"

  # Re-write .env for this folder
  cat > "$ENV_FILE" <<EOF
DEFAULT_OUTPUTS_PATH="$DEFAULT_OUTPUTS_PATH"
DEFAULT_FIND_MAX_FILE="$DEFAULT_FIND_MAX_FILE"
DEFAULT_COPY_DEST="$after_path"
SERVER_ADDRESS="$SERVER_ADDRESS"
WORKFLOW_FILE="$WORKFLOW_FILE"
PICTURES_DIRECTORY="$before_path"
EOF

  echo "[$(date '+%F %T')] Running for folder: $folder_name"
  log_file="$LOG_DIR/${folder_name}.log"

  # Run the program and capture output
  if python3 "$BASE/process_localization.py" >"$log_file" 2>&1; then
    echo "✅ Finished: $folder_name"
    ((success_count++))
  else
    echo "❌ Failed: $folder_name (see $log_file)"
    ((fail_count++))
  fi
done

# Restore original .env (if there was one)
if [[ -f "$BACKUP" ]]; then
  mv -f "$BACKUP" "$ENV_FILE"
  echo "Restored original .env"
fi

if [[ "$ran_any" == false ]]; then
  echo "No subfolders found in $PICTURES_DIR"
else
  echo "Done. Success: $success_count  Failures: $fail_count  (logs in $LOG_DIR)"
fi
