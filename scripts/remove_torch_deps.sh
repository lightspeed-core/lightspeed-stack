#!/bin/bash

# Script to remove torch dependencies from requirements.txt
# Detects torch==<version> and removes it along with all subsequent lines starting with 4 spaces

set -e

# Get the input file (default to requirements.x86_64.txt)
INPUT_FILE="${1:-requirements.x86_64.txt}"

if [ ! -f "$INPUT_FILE" ]; then
    echo "Error: File '$INPUT_FILE' not found"
    exit 1
fi

# Create a backup
BACKUP_FILE="${INPUT_FILE}.backup"
cp "$INPUT_FILE" "$BACKUP_FILE"
echo "Created backup: $BACKUP_FILE"

# Use awk to process the file
awk '
BEGIN {
    in_torch_section = 0
}

# If we find a line starting with torch==
/^torch==/ {
    in_torch_section = 1
    next  # Skip this line
}

# If we are in torch section and line starts with 4 spaces, skip it
in_torch_section == 1 && /^    / {
    next  # Skip this line
}

# If we are in torch section and line does NOT start with 4 spaces, exit torch section
in_torch_section == 1 && !/^    / {
    in_torch_section = 0
    # Fall through to print this line
}

# Print all lines that are not part of torch section
in_torch_section == 0 {
    print
}
' "$INPUT_FILE" > "${INPUT_FILE}.tmp"

# Replace original file with processed version
mv "${INPUT_FILE}.tmp" "$INPUT_FILE"

echo "Successfully removed torch dependencies from $INPUT_FILE"
echo "Original file backed up to $BACKUP_FILE"
diff "$INPUT_FILE" "$BACKUP_FILE" || true
