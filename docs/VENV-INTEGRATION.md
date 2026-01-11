# Virtual Environment Integration - Implementation Notes

## Changes Made

All Python scripts have been updated to use the installed virtual environment located at `/usr/lib/usb-enforcer/.venv`.

### Scripts Updated

1. **usb-enforcer-helper** (was direct Python script)
   - Converted to bash wrapper
   - Moved Python code to `src/usb_enforcer/helper.py`
   - Now uses venv: `${VENV}/bin/python3 -c "from usb_enforcer.helper import main; main()"`

2. **usb_enforcer_ui.py** 
   - Removed shebang (called through wrapper)
   - Called via `usb-enforcer-ui` bash wrapper

### All Wrapper Scripts Now Follow This Pattern

```bash
#!/bin/bash
set -e

LIBDIR="/usr/lib/usb-enforcer"
VENV="${LIBDIR}/.venv"

# Use venv if available, otherwise use system Python with PYTHONPATH
if [ -d "${VENV}" ] && [ -f "${VENV}/bin/python3" ]; then
    export PYTHONPATH="${LIBDIR}"
    exec "${VENV}/bin/python3" -c "from usb_enforcer.module import main; main()" "$@"
else
    export PYTHONPATH="${LIBDIR}"
    exec python3 -c "from usb_enforcer.module import main; main()" "$@"
fi
```

### Benefits

1. **Consistent dependency management**: All scripts use the same Python environment with all required dependencies installed
2. **Isolation**: Dependencies don't conflict with system Python packages
3. **Fallback**: If venv is not available, scripts fall back to system Python (useful for development)
4. **No hardcoded Python paths**: Scripts work regardless of where Python is installed

### Verification

All executable scripts in the `scripts/` directory are now bash scripts that properly invoke the venv:

- ✅ `usb-enforcerd` - Daemon wrapper
- ✅ `usb-enforcer-ui` - UI notification service wrapper
- ✅ `usb-enforcer-wizard` - Encryption wizard wrapper
- ✅ `usb-enforcer-helper` - Helper utilities wrapper

### Testing

To verify the venv is being used:

```bash
# Check that scripts are bash
file scripts/usb-enforcer*

# Verify venv usage (should show .venv path in process)
sudo systemctl restart usb-enforcerd.service
ps aux | grep usb-enforcer | grep -v grep
# Should show: /usr/lib/usb-enforcer/.venv/bin/python3

# Check UI service
systemctl --user restart usb-enforcer-ui.service  
ps aux | grep usb-enforcer-ui | grep -v grep
# Should show: /usr/lib/usb-enforcer/.venv/bin/python3
```

### Installation

The install scripts automatically:
1. Create the venv at `/usr/lib/usb-enforcer/.venv`
2. Install all dependencies into the venv
3. Copy the wrapper scripts to `/usr/libexec/`
4. Copy the Python modules to `/usr/lib/usb-enforcer/`

No changes to installation procedures are needed.
