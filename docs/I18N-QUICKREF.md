# i18n Quick Reference

## Testing Translations

### Test Spanish notifications
```bash
cd /home/dguedry/Documents/usb-enforcer
LANGUAGE=es /usr/lib/usb-enforcer/.venv/bin/python3 -c "
import sys
sys.path.insert(0, 'src')
from usb_enforcer.i18n import setup_i18n, _, ngettext
setup_i18n()
print(_('Encrypted USB detected'))
print(_('⛔ File Blocked - Sensitive Data Detected'))
print(ngettext('pattern', 'patterns', 1))
print(ngettext('pattern', 'patterns', 3))
"
```

Expected output:
```
USB cifrado detectado
⛔ Archivo bloqueado - Datos sensibles detectados
patrón
patrones
```

### Test UI with Spanish
```bash
LANGUAGE=es /usr/lib/usb-enforcer/.venv/bin/python3 /path/to/usb_enforcer_ui.py
```

## Adding a New Translation

### 1. Extract strings (run once after code changes)
```bash
./scripts/extract-translations.sh
```

### 2. Create translation for French
```bash
msginit -i locale/usb-enforcer.pot \
        -o locale/fr/LC_MESSAGES/usb-enforcer.po \
        -l fr_FR
```

### 3. Edit translation file
```bash
# Use any text editor or translation tool
nano locale/fr/LC_MESSAGES/usb-enforcer.po
# Or use Poedit (GUI): poedit locale/fr/LC_MESSAGES/usb-enforcer.po
```

### 4. Compile translations
```bash
make translations
# Or manually:
msgfmt locale/fr/LC_MESSAGES/usb-enforcer.po -o locale/fr/LC_MESSAGES/usb-enforcer.mo
```

### 5. Test
```bash
LANGUAGE=fr /usr/lib/usb-enforcer/.venv/bin/python3 -m usb_enforcer.usb_enforcer_ui
```

## Updating Existing Translation

When source code adds new strings:

```bash
# 1. Extract new strings
./scripts/extract-translations.sh

# 2. Merge with existing translation
msgmerge --update locale/es/LC_MESSAGES/usb-enforcer.po locale/usb-enforcer.pot

# 3. Edit and translate new strings
nano locale/es/LC_MESSAGES/usb-enforcer.po

# 4. Compile
make translations

# 5. Test
LANGUAGE=es /usr/lib/usb-enforcer/.venv/bin/python3 -m usb_enforcer.usb_enforcer_ui
```

## Developer Workflow

### Mark string for translation
```python
from .i18n import _, ngettext

# Simple string
_("Encrypted USB detected")

# With formatting
_("Device {name} unlocked").format(name=dev)

# Plurals
ngettext("{n} pattern", "{n} patterns", count).format(n=count)
```

### Extract and compile
```bash
./scripts/extract-translations.sh  # Creates/updates .pot
make translations                   # Compiles all .po to .mo
```

### Test locally
```bash
# Set LANGUAGE to test specific locale
LANGUAGE=es python3 your_script.py
```

## File Reference

| File | Purpose | Edit? |
|------|---------|-------|
| `usb-enforcer.pot` | Translation template | No (auto-generated) |
| `*.po` | Translation source | Yes (human-readable) |
| `*.mo` | Compiled translation | No (binary, auto-generated) |

## Common Languages

| Code | Language |
|------|----------|
| `es` | Spanish |
| `fr` | French |
| `de` | German |
| `it` | Italian |
| `pt_BR` | Portuguese (Brazil) |
| `ru` | Russian |
| `zh_CN` | Chinese (Simplified) |
| `ja` | Japanese |

## Troubleshooting

### Translations not loading
```bash
# Check if .mo file exists
ls -la locale/es/LC_MESSAGES/usb-enforcer.mo

# Verify LANGUAGE is set
echo $LANGUAGE

# Test directly
LANGUAGE=es python3 -c "from usb_enforcer.i18n import _; print(_('test'))"
```

### String not translated
1. Check if string is marked with `_()` in source
2. Run `extract-translations.sh` to update `.pot`
3. Run `msgmerge` to update `.po` files
4. Translate the string in `.po` file
5. Run `make translations` to compile
6. Restart application

### Plural forms wrong
Check `Plural-Forms:` header in `.po` file:
```
Plural-Forms: nplurals=2; plural=(n != 1);
```

Different languages have different plural rules!
