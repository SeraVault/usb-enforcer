"""
Internationalization (i18n) support for USB Enforcer.

Provides translation functions for user-facing messages.
Uses standard gettext framework with fallback to English.
"""

import gettext
import os
from pathlib import Path
from typing import Optional

# Translation domain and directory
DOMAIN = "usb-enforcer"
LOCALE_DIR = Path("/usr/share/locale")

# Fallback to package locale if system locale not available
if not LOCALE_DIR.exists():
    LOCALE_DIR = Path(__file__).parent.parent.parent / "locale"

# Initialize translation
_translations: Optional[gettext.GNUTranslations] = None


def setup_i18n(locale: Optional[str] = None):
    """
    Initialize internationalization.
    
    Args:
        locale: Specific locale to use (e.g., 'es_ES', 'fr_FR')
                If None, uses system default
    """
    global _translations
    
    # Try system locale directory first, then fall back to local
    locale_dirs = [str(LOCALE_DIR)]
    if not LOCALE_DIR.is_absolute() or not (LOCALE_DIR / "usb-enforcer.pot").exists():
        # Add local directory as fallback for development
        local_dir = Path(__file__).parent.parent.parent / "locale"
        if local_dir.exists():
            locale_dirs.insert(0, str(local_dir))
    
    for localedir in locale_dirs:
        try:
            if locale:
                # Use specific locale
                _translations = gettext.translation(
                    DOMAIN,
                    localedir=localedir,
                    languages=[locale],
                    fallback=False
                )
            else:
                # Use system locale
                _translations = gettext.translation(
                    DOMAIN,
                    localedir=localedir,
                    fallback=False
                )
            # Success! Translation found
            return
        except (FileNotFoundError, OSError):
            # Try next directory
            continue
    
    # No translations found, use NullTranslations (English)
    _translations = gettext.NullTranslations()


def _(message: str) -> str:
    """
    Translate a message.
    
    Args:
        message: English message to translate
        
    Returns:
        Translated message in current locale, or original if no translation
        
    Example:
        >>> from usb_enforcer.i18n import _
        >>> _("File blocked")
        "Archivo bloqueado"  # if locale is Spanish
    """
    if _translations is None:
        setup_i18n()
    
    return _translations.gettext(message) if _translations else message


def ngettext(singular: str, plural: str, n: int) -> str:
    """
    Translate a message with plural forms.
    
    Args:
        singular: Singular form (English)
        plural: Plural form (English)
        n: Count to determine which form
        
    Returns:
        Translated message with correct plural form
        
    Example:
        >>> ngettext("{n} file blocked", "{n} files blocked", count)
    """
    if _translations is None:
        setup_i18n()
    
    if _translations:
        return _translations.ngettext(singular, plural, n)
    else:
        return singular if n == 1 else plural


# Convenience alias
N_ = ngettext


# Initialize on import
setup_i18n()
