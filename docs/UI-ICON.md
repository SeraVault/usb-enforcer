# USB Enforcer UI Icon

## Overview

The USB Enforcer Wizard now includes an application icon that appears in the dock/application launcher when the wizard is running.

## Files Added

- **Icon**: `deploy/icons/usb-enforcer.svg`
  - Scalable SVG icon featuring a USB drive with a lock overlay
  - Installed to: `/usr/share/icons/hicolor/scalable/apps/`

- **Desktop Entry**: `deploy/desktop/usb-enforcer-wizard.desktop`
  - FreeDesktop.org .desktop file for application launcher integration
  - Installed to: `/usr/share/applications/`

## Icon Design

The icon features:
- A USB drive in blue representing the device
- A gold/amber lock overlay indicating encryption/security
- LED indicator showing device activity
- Clean, modern design suitable for both light and dark themes

## Installation

The icon and desktop file are automatically installed by:
- Debian packages (both standard and bundled)
- RPM packages (both standard and bundled)
- Manual installation scripts (`install-debian.sh` and `install-rhel.sh`)

After installation, the icon cache and desktop database are automatically updated.

## Usage

The wizard can be launched:
1. From the application launcher/menu (search for "USB Encryption Wizard")
2. From the dock by running the application
3. From the command line: `/usr/libexec/usb-enforcer-wizard`
4. From notifications when a USB device is inserted

The icon will appear in the dock when the wizard window is open, making it easy to identify and switch to the application.

## Technical Details

- **Application ID**: `com.seravault.usb.encryption.wizard`
- **Startup WM Class**: `usb-enforcer-wizard`
- **Categories**: System, Security, Utility
- **Icon Theme Integration**: Follows FreeDesktop.org icon theme specification
