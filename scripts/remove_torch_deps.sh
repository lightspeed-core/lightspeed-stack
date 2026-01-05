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

# output version of torch, faiss-cpu, and tiktoken
TORCH_VERSION=$(grep -o 'torch==[0-9\.]*' "$INPUT_FILE")
FAISS_VERSION=$(grep -o 'faiss-cpu==[0-9\.]*' "$INPUT_FILE")
TIKTOKEN_VERSION=$(grep -o 'tiktoken==[0-9\.]*' "$INPUT_FILE")
JITER_VERSION=$(grep -o 'jiter==[0-9\.]*' "$INPUT_FILE")
echo "torch version: $TORCH_VERSION"
echo "faiss-cpu version: $FAISS_VERSION"
echo "tiktoken version: $TIKTOKEN_VERSION"
echo "jiter version: $JITER_VERSION"

# Generate requirements.torch.txt file
echo "${TORCH_VERSION}" | uv pip compile  - -o requirements.torch.txt --generate-hashes  --python-version 3.12 --torch-backend cpu --emit-index-url  --no-deps --index-url https://download.pytorch.org/whl/cpu --refresh
# Generate requirements.binary.txt file
printf "%s\n%s\n%s" "${FAISS_VERSION}" "${TIKTOKEN_VERSION}" "${JITER_VERSION}" | uv pip compile  - -o requirements.binary.txt --generate-hashes  --python-version 3.12 --no-deps --universal
# remove torch from requirements.$(uname -m).txt
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

# remove faiss-cpu from requirements.$(uname -m).txt
awk '
BEGIN {
    in_faiss_section = 0
}

# If we find a line starting with faiss-cpu==
/^faiss-cpu==/ {
    in_faiss_section = 1
    next  # Skip this line
}

# If we are in faiss section and line starts with 4 spaces, skip it
in_faiss_section == 1 && /^    / {
    next  # Skip this line
}

# If we are in faiss section and line does NOT start with 4 spaces, exit faiss section
in_faiss_section == 1 && !/^    / {
    in_faiss_section = 0
    # Fall through to print this line
}

# Print all lines that are not part of faiss section
in_faiss_section == 0 {
    print
}
' "${INPUT_FILE}.tmp" > "${INPUT_FILE}.tmp2"

# remove tiktoken from requirements.$(uname -m).txt
awk '
BEGIN {
    in_tiktoken_section = 0
}

# If we find a line starting with tiktoken==
/^tiktoken==/ {
    in_tiktoken_section = 1
    next  # Skip this line
}

# If we are in tiktoken section and line starts with 4 spaces, skip it
in_tiktoken_section == 1 && /^    / {
    next  # Skip this line
}

# If we are in tiktoken section and line does NOT start with 4 spaces, exit tiktoken section
in_tiktoken_section == 1 && !/^    / {
    in_tiktoken_section = 0
    # Fall through to print this line
}

# Print all lines that are not part of tiktoken section
in_tiktoken_section == 0 {
    print
}
' "${INPUT_FILE}.tmp2" > "${INPUT_FILE}.tmp3"

# remove jiter from requirements.$(uname -m).txt
awk '
BEGIN {
    in_jiter_section = 0
}

# If we find a line starting with jiter==
/^jiter==/ {
    in_jiter_section = 1
    next  # Skip this line
}

# If we are in jiter section and line starts with 4 spaces, skip it
in_jiter_section == 1 && /^    / {
    next  # Skip this line
}

# If we are in jiter section and line does NOT start with 4 spaces, exit jiter section
in_jiter_section == 1 && !/^    / {
    in_jiter_section = 0
    # Fall through to print this line
}

# Print all lines that are not part of jiter section
in_jiter_section == 0 {
    print
}
' "${INPUT_FILE}.tmp3" > "${INPUT_FILE}.tmp4"

# Replace original file with processed version and clean up temporary files
mv "${INPUT_FILE}.tmp4" "$INPUT_FILE"
rm "${INPUT_FILE}.tmp" "${INPUT_FILE}.tmp2" "${INPUT_FILE}.tmp3"

echo "Successfully removed torch, faiss-cpu, and tiktoken dependencies from $INPUT_FILE"
echo "Original file backed up to $BACKUP_FILE"
diff "$INPUT_FILE" "$BACKUP_FILE" || true
