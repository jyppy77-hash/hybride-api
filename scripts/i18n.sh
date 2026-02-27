#!/bin/bash
# =============================================================================
# LotoIA — i18n utility commands (Babel / gettext)
# Usage: ./scripts/i18n.sh {extract|update|compile|init <lang>}
# =============================================================================

set -e

TRANSLATIONS_DIR="translations"
BABEL_CFG="$TRANSLATIONS_DIR/babel.cfg"
POT_FILE="$TRANSLATIONS_DIR/messages.pot"

case "$1" in
  extract)
    pybabel extract -F "$BABEL_CFG" -o "$POT_FILE" .
    echo "Extraction done -> $POT_FILE"
    ;;
  update)
    pybabel update -i "$POT_FILE" -d "$TRANSLATIONS_DIR"
    echo ".po files updated"
    ;;
  compile)
    pybabel compile -d "$TRANSLATIONS_DIR"
    echo ".mo files compiled"
    ;;
  init)
    if [ -z "$2" ]; then
      echo "Usage: ./scripts/i18n.sh init <lang>"
      exit 1
    fi
    pybabel init -i "$POT_FILE" -d "$TRANSLATIONS_DIR" -l "$2"
    echo "Language $2 initialised"
    ;;
  *)
    echo "Usage: ./scripts/i18n.sh {extract|update|compile|init <lang>}"
    exit 1
    ;;
esac
