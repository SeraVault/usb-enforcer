# USB Enforcer Admin GUI - Separation and Independence

## Changes Made

### 1. Icon Update
- **Changed from**: `preferences-system` (generic settings icon)
- **Changed to**: `system-config-users` (administration/config icon)
- **Desktop file**: Added "Administration" category for better menu placement

### 2. Complete Separation from Main Package

#### Dedicated Installation Directory
- **Main usb-enforcer**: `/usr/lib/usb-enforcer/` with `.venv`
- **Admin GUI**: `/usr/lib/usb-enforcer-admin/` with separate `.venv`
- **No shared dependencies** between the two packages

#### Minimal Dependencies
Created `requirements-admin.txt` with ONLY:
- `toml` (for Python < 3.11; Python 3.11+ uses built-in `tomllib`)
- GTK4/libadwaita/python3-gi (system packages, not Python packages)

**No heavy dependencies**:
- ❌ No pdfminer.six
- ❌ No content scanning libraries
- ❌ No cryptsetup Python bindings
- ❌ No FUSE libraries
- ❌ No document parsing libraries

### 3. Separate Virtual Environment

#### Launcher Script (`scripts/usb-enforcer-admin`)
- Looks for venv at `/usr/lib/usb-enforcer-admin/.venv`
- Falls back to system Python if venv not found
- Uses dedicated PYTHONPATH

#### Install Script (`scripts/install-admin.sh`)
- Creates dedicated venv: `python3 -m venv /usr/lib/usb-enforcer-admin/.venv`
- Installs only toml if Python < 3.11
- Copies ONLY `admin.py` module (not entire usb_enforcer package)
- No system-wide pip install

### 4. Package Updates

#### Debian Package (`debian-admin/`)
- **control**: Removed python3-toml from hard dependencies
- **rules**: Creates venv during build, installs minimal deps
- **Result**: ~5MB package vs ~200MB for main package

#### RPM Package (`rpm-admin/`)
- **spec**: Removed python3-toml requirement
- **install**: Creates venv, minimal deps only
- **files**: Only includes `/usr/lib/usb-enforcer-admin/`

### 5. Uninstall Script
- Removes `/usr/lib/usb-enforcer-admin/` entirely (including venv)
- Cleans up desktop files and polkit policies
- No impact on main usb-enforcer package

## Benefits

### 1. True Independence
- Admin can be installed **without** usb-enforcer daemon
- Admin can be removed **without** affecting daemon
- Useful for:
  - Remote administration workstations
  - Configuration-only systems
  - Testing configs before deployment

### 2. Minimal Footprint
```
Main usb-enforcer:     ~200 MB (with all content scanning libs)
Admin GUI:             ~5 MB   (just toml + GTK bindings)
```

### 3. No Dependency Conflicts
- Admin venv is isolated from main venv
- Different Python versions? No problem
- Different library versions? No problem
- No pdfminer.six version issues!

### 4. Clean Installation
```bash
# Install only admin (no daemon)
sudo make admin-install

# Or via package
make deb-admin && sudo dpkg -i dist/usb-enforcer-admin_*.deb
```

### 5. Clean Removal
```bash
sudo bash scripts/uninstall-admin.sh
# Removes only: /usr/lib/usb-enforcer-admin/
# Keeps: /etc/usb-enforcer/ configs
# Keeps: main usb-enforcer installation
```

## Directory Structure

```
/usr/lib/usb-enforcer/              # Main daemon
├── .venv/                          # Daemon venv (16+ packages)
│   ├── bin/
│   ├── lib/
│   └── ...
└── usb_enforcer/                   # Full package
    ├── daemon.py
    ├── encryption/
    ├── content_verification/
    └── ...

/usr/lib/usb-enforcer-admin/        # Admin GUI (separate)
├── .venv/                          # Admin venv (0-1 packages)
│   ├── bin/
│   ├── lib/
│   └── ...
└── usb_enforcer/                   # Minimal - only admin.py
    └── ui/
        └── admin.py
```

## Installation Comparison

### Before (Shared Installation)
```bash
sudo ./scripts/install-admin.sh
# Would run: python3 setup.py install
# Installs ALL dependencies (16+ packages)
# ERROR: pdfminer.six==20251230 not found
```

### After (Separate Installation)
```bash
sudo ./scripts/install-admin.sh
# Creates: /usr/lib/usb-enforcer-admin/.venv
# Installs: toml (if Python < 3.11) - that's it!
# SUCCESS: No heavy dependencies needed
```

## Usage

### Admin GUI
```bash
# Launch admin (uses its own venv)
pkexec usb-enforcer-admin

# Admin runs from:
/usr/lib/usb-enforcer-admin/.venv/bin/python3 \
  /usr/lib/usb-enforcer-admin/usb_enforcer/ui/admin.py
```

### Main Daemon (Unaffected)
```bash
# Daemon still runs from its own venv
sudo systemctl start usb-enforcerd

# Daemon runs from:
/usr/lib/usb-enforcer/.venv/bin/python3 \
  /usr/lib/usb-enforcer/usb_enforcer/daemon.py
```

## Testing

### Test Admin Installation
```bash
# Remove old installation
sudo bash scripts/uninstall-admin.sh

# Install with new separate approach
sudo bash scripts/install-admin.sh

# Verify
ls -la /usr/lib/usb-enforcer-admin/
ls -la /usr/lib/usb-enforcer-admin/.venv/

# Launch
pkexec usb-enforcer-admin
```

### Test Independence
```bash
# Remove daemon (admin should still work)
sudo apt remove usb-enforcer

# Launch admin (should work fine)
pkexec usb-enforcer-admin

# Edit config (should work fine)
# Save config (should work fine)
```

## Program Menu

The admin GUI will appear in:
- **GNOME**: Activities → Show Applications → System Tools or Administration
- **KDE**: Application Launcher → System → Administration
- **XFCE**: Applications → Settings → System

Desktop file location: `/usr/share/applications/usb-enforcer-admin.desktop`

Categories: `System;Settings;Security;Administration;`

## Icon Options

Current: `Icon=system-config-users` (administration icon)

Other options:
- `preferences-system` - Generic settings gear
- `security-medium` - Security shield
- `emblem-system` - System emblem
- `system-users` - User management
- Custom icon (we can create one)

Would you like a custom icon? I can create one that matches the wizard style or a unique admin/security theme.
