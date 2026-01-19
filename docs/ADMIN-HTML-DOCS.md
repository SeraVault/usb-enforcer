# Admin GUI - HTML Documentation Support

## Overview

The USB Enforcer Admin GUI now supports displaying documentation in beautifully formatted HTML using WebKit, providing a much better reading experience than the previous plain text markdown rendering.

## Features

### Build-Time Conversion
- All markdown documentation (`.md` files) are automatically converted to HTML during package build
- Conversion uses `python3-markdown` with extended features:
  - Tables
  - Fenced code blocks with syntax highlighting  
  - Table of contents
  - Better list handling
  - GitHub-flavored markdown

### Intelligent Display
The admin app intelligently chooses the best format:
1. **With WebKit**: Displays HTML with proper formatting, clickable links, styled code blocks
2. **Without WebKit**: Falls back to markdown with basic text formatting

### Search Path Priority
When opening documentation, the app searches in this order:
1. `/usr/share/doc/usb-enforcer/html/{filename}.html` - Uncompressed HTML
2. `/usr/share/doc/usb-enforcer/html/{filename}.html.gz` - Compressed HTML  
3. `/usr/share/doc/usb-enforcer/{filename}.md` - Uncompressed markdown
4. `/usr/share/doc/usb-enforcer/{filename}.md.gz` - Compressed markdown (Debian)
5. Workspace `docs/{filename}.md` - Development environment

## Package Differences

### Debian Packages
- HTML files: Stored in `/usr/share/doc/usb-enforcer/html/` (**uncompressed**)
- Markdown files: Stored in `/usr/share/doc/usb-enforcer/` (**compressed** with gzip)
- HTML files are NOT compressed, ensuring fast loading

### RPM Packages  
- HTML files: `/usr/share/doc/usb-enforcer/html/` (uncompressed)
- Markdown files: `/usr/share/doc/usb-enforcer/` (uncompressed)

## Dependencies

### Build Dependencies
- **Debian**: `python3-markdown` (in Build-Depends)
- **RPM**: `python3-markdown` (in BuildRequires)

### Runtime Dependencies
- **Debian**: `gir1.2-webkit-6.0` (for HTML display)
- **RPM**: `webkit2gtk4.1` (for HTML display)

**Note**: WebKit is optional - the app works without it, just with markdown rendering instead.

## HTML Styling

The generated HTML includes embedded CSS for:
- Clean, modern typography
- Syntax-highlighted code blocks  
- Responsive tables
- GitHub-style formatting
- Proper heading hierarchy
- Styled blockquotes and lists

## File Sizes

Comparison for ADMINISTRATION.md:
- Markdown (compressed): 4,680 bytes  
- HTML (uncompressed): 39,331 bytes
- HTML is ~8x larger but provides much better UX

## Build Process

### Debian
```makefile
# debian-admin/rules
python3 scripts/convert-docs-to-html.py docs $(CURDIR)/debian/usb-enforcer-admin/usr/share/doc/usb-enforcer/html
```

### RPM  
```spec
# rpm-admin/usb-enforcer-admin.spec
python3 scripts/convert-docs-to-html.py docs %{buildroot}%{_docdir}/usb-enforcer/html
```

### Direct Install
```bash
# scripts/install-admin.sh
python3 scripts/convert-docs-to-html.py docs /usr/share/doc/usb-enforcer/html
```

## Graceful Degradation

The implementation handles missing components gracefully:

1. **No WebKit**: Falls back to markdown rendering  
2. **No HTML files**: Loads compressed/uncompressed markdown
3. **No python3-markdown at build**: Markdown files still available
4. **Conversion fails**: Build continues, markdown available

## Testing

### Verify HTML files in package
```bash
dpkg-deb -c dist/usb-enforcer-admin_*.deb | grep html/
```

### Check WebKit availability
```bash
python3 -c "import gi; gi.require_version('WebKit', '6.0'); from gi.repository import WebKit; print('WebKit available')"
```

### Install WebKit (if needed)
```bash
# Debian/Ubuntu  
sudo apt install gir1.2-webkit-6.0

# Fedora/RHEL
sudo dnf install webkit2gtk4.1
```

## Future Enhancements

Possible improvements:
- Dark mode support (detect system theme)
- Search within documentation
- Navigate between docs without closing dialog
- Print documentation
- Export as PDF

## Files Modified

### New Files
- `scripts/convert-docs-to-html.py` - Markdown to HTML converter

### Updated Files  
- `src/usb_enforcer/ui/admin.py` - Added WebKit support, HTML display
- `debian-admin/rules` - Added conversion step
- `debian-admin/control` - Added dependencies
- `rpm-admin/usb-enforcer-admin.spec` - Added conversion step, dependencies
- `scripts/install-admin.sh` - Added conversion for direct install

## Benefits

✅ **Better Readability**: Proper formatting, headings, and styling  
✅ **Clickable Links**: Navigate to related documentation  
✅ **Syntax Highlighting**: Code examples are easier to read  
✅ **Tables**: Properly formatted configuration tables  
✅ **Backwards Compatible**: Falls back to markdown if WebKit unavailable  
✅ **Performance**: HTML loads faster than parsing markdown at runtime
