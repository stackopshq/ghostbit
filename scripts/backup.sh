#!/usr/bin/env bash
# Encrypted Ghostbit backup.
#
# Streams `python -m app.admin export` through age and writes one
# timestamped file per run to $BACKUP_DIR. The stream goes through a
# pipe end-to-end so the plaintext export is never materialised on
# disk — a stolen backup file is useless without the age recipient's
# private key.
#
# Usage (one-shot):
#   BACKUP_DIR=/var/backups/ghostbit \
#   AGE_RECIPIENT="age1xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" \
#     scripts/backup.sh
#
# As a recurring job: see scripts/ghostbit-backup.{service,timer}.
#
# Restore:
#   age --decrypt -i ~/.config/age/keys.txt backup-2026-05-24T03:00.jsonl.age \
#     | python -m app.admin import
#
# Why age rather than gpg: age has a single recipient flag, no key-server
# nonsense, no asymmetric-vs-symmetric mode footgun, and the file format
# is small and forward-compatible. gpg works too — swap the encrypt
# command if your ops standardises on it.

set -euo pipefail

: "${BACKUP_DIR:?BACKUP_DIR must be set (e.g. /var/backups/ghostbit)}"
: "${AGE_RECIPIENT:?AGE_RECIPIENT must be set (an age public key)}"

command -v age >/dev/null || {
    echo "age is not installed. https://age-encryption.org" >&2
    exit 1
}

mkdir -p "$BACKUP_DIR"

# UTC + ISO-ish, sortable, safe in filenames.
TS=$(date -u +%Y-%m-%dT%H-%M-%SZ)
OUT="$BACKUP_DIR/ghostbit-$TS.jsonl.age"
TMP="$OUT.partial"

# Pipefail catches a failure on either side of the pipe.
python -m app.admin export | age -r "$AGE_RECIPIENT" -o "$TMP"

# Atomic rename so a partially-written file can never be picked up as a
# "good" backup by a downstream rotation/sync step.
mv "$TMP" "$OUT"

echo "$OUT"
