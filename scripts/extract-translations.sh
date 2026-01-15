#!/bin/bash
# Extract translatable strings from Python source files
# Creates/updates the message catalog template (POT file)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOCALE_DIR="$PROJECT_ROOT/locale"
POT_FILE="$LOCALE_DIR/usb-enforcer.pot"

# Create locale directory
mkdir -p "$LOCALE_DIR"

echo "Extracting translatable strings..."

# Extract strings from Python files
xgettext \
    --language=Python \
    --keyword=_ \
    --keyword=N_:1,2 \
    --keyword=ngettext:1,2 \
    --from-code=UTF-8 \
    --output="$POT_FILE" \
    --package-name="USB Enforcer" \
    --package-version="1.0.0" \
    --msgid-bugs-address="https://github.com/yourusername/usb-enforcer/issues" \
    --copyright-holder="USB Enforcer Contributors" \
    --add-comments=TRANSLATORS \
    $(find "$PROJECT_ROOT/src" -name "*.py")

echo "✓ Template created: $POT_FILE"
echo ""
echo "Translation statistics:"
msggrep --no-wrap -v -e "." "$POT_FILE" | grep "^msgid" | wc -l | xargs echo "  Strings to translate:"

echo ""
echo "To create a new translation (e.g., Spanish):"
echo "  msginit -i $POT_FILE -o locale/es_ES/LC_MESSAGES/usb-enforcer.po -l es_ES"
echo ""
echo "To update existing translations:"
echo "  msgmerge -U locale/es_ES/LC_MESSAGES/usb-enforcer.po $POT_FILE"
echo ""
echo "To compile translations:"
echo "  msgfmt locale/es_ES/LC_MESSAGES/usb-enforcer.po -o locale/es_ES/LC_MESSAGES/usb-enforcer.mo"
