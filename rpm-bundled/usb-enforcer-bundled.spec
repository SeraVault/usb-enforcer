Name:           usb-enforcer-bundled
Version:        1.0.0
Release:        1
Summary:        USB data loss prevention for Linux desktops (bundled Python deps)

License:        GPL-3.0
URL:            https://github.com/seravault/usb-enforcer
Source0:        usb-enforcer-%{version}.tar.gz
# Bundled Python dependencies (download these separately)
Source1:        python-deps.tar.gz

BuildArch:      noarch

BuildRequires:  python3-devel >= 3.8
BuildRequires:  systemd-rpm-macros
BuildRequires:  pkgconfig
BuildRequires:  cairo-devel
BuildRequires:  gobject-introspection-devel

# System dependencies (can't bundle these)
Requires:       python3 >= 3.8
Requires:       python3-gobject >= 3.46.0
Requires:       python3-cairo >= 1.16
Requires:       cryptsetup
Requires:       udisks2
Requires:       util-linux
Requires:       parted
Requires:       exfatprogs
Requires:       systemd
Requires:       polkit
Requires:       dbus
Requires:       libnotify
Requires:       gtk4
Requires:       libadwaita
Requires:       fuse3
Requires:       fuse3-libs
Requires:       file-libs
Requires:       unrar

# Provide bundled Python packages
Provides:       bundled(python3dist(pyudev)) = 0.24.4
Provides:       bundled(python3dist(pydbus)) = 0.6.0
Provides:       bundled(python3dist(typing-extensions)) = 4.15.0
Provides:       bundled(python3dist(fusepy)) = 3.0.1
Provides:       bundled(python3dist(python-magic)) = 0.4.27
Provides:       bundled(python3dist(pdfplumber)) = 0.10.3
Provides:       bundled(python3dist(python-docx)) = 1.1.0
Provides:       bundled(python3dist(openpyxl)) = 3.1.2
Provides:       bundled(python3dist(python-pptx)) = 0.6.23
Provides:       bundled(python3dist(odfpy)) = 1.4.1
Provides:       bundled(python3dist(py7zr)) = 0.20.8
Provides:       bundled(python3dist(rarfile)) = 4.1
Provides:       bundled(python3dist(xlrd)) = 2.0.1
Provides:       bundled(python3dist(olefile)) = 0.47
Provides:       bundled(python3dist(extract-msg)) = 0.48.0
Provides:       bundled(python3dist(striprtf)) = 0.0.26

%description
USB Enforcer enforces encryption on USB mass-storage devices and scans
files for sensitive data before allowing writes to removable media.
Plaintext USB devices are forced read-only, while LUKS2-encrypted devices
can be unlocked and mounted writable. A Python daemon watches udev, enforces
block-level read-only mode, and provides a DBus API. Includes a GTK wizard
for encryption/unlock flows, content scanning with FUSE overlay, and
desktop notifications with progress tracking.

This package bundles Python dependencies for airgapped/offline installation.

%prep
%setup -q -n usb-enforcer-%{version}
# Extract bundled Python dependencies
tar xzf %{SOURCE1} -C .

%build
# Pure Python, nothing to build

%install
# Set installation directories
export PREFIX=%{_prefix}
export LIBDIR=%{_libdir}/usb-enforcer
export LIBEXEC=%{_libexecdir}
export CONFIG_DIR=%{_sysconfdir}/usb-enforcer
export SYSTEMD_SYSTEM_DIR=%{_unitdir}
export SYSTEMD_USER_DIR=%{_userunitdir}
export POLKIT_DIR=%{_sysconfdir}/polkit-1/rules.d
export UDEV_DIR=%{_udevrulesdir}
export DBUS_DIR=%{_sysconfdir}/dbus-1/system.d

# Create directories
install -d %{buildroot}%{_libdir}/usb-enforcer
install -d %{buildroot}%{_libdir}/usb-enforcer/wheels
install -d %{buildroot}%{_libexecdir}
install -d %{buildroot}%{_sysconfdir}/usb-enforcer
install -d %{buildroot}%{_unitdir}
install -d %{buildroot}%{_userunitdir}
install -d %{buildroot}%{_sysconfdir}/polkit-1/rules.d
install -d %{buildroot}%{_udevrulesdir}
install -d %{buildroot}%{_sysconfdir}/dbus-1/system.d
install -d %{buildroot}%{_unitdir}/usb-enforcerd.service.d
install -d %{buildroot}%{_userunitdir}/usb-enforcer-ui.service.d
install -d %{buildroot}%{_datadir}/icons/hicolor/scalable/apps
install -d %{buildroot}%{_datadir}/applications
install -d %{buildroot}%{_datadir}/metainfo

# Install Python package
cp -r src/usb_enforcer %{buildroot}%{_libdir}/usb-enforcer/
install -m 0644 src/usb_enforcer/usb_enforcer_ui.py %{buildroot}%{_libdir}/usb-enforcer/

# Install bundled wheels
cp wheels/*.whl %{buildroot}%{_libdir}/usb-enforcer/wheels/

# Install scripts
install -m 0755 scripts/usb-enforcerd %{buildroot}%{_libexecdir}/
install -m 0755 scripts/usb-enforcer-helper %{buildroot}%{_libexecdir}/
install -m 0755 scripts/usb-enforcer-ui %{buildroot}%{_libexecdir}/
install -m 0755 scripts/usb-enforcer-wizard %{buildroot}%{_libexecdir}/

# Install configuration
install -m 0644 deploy/config.toml.sample %{buildroot}%{_sysconfdir}/usb-enforcer/config.toml

# Install udev rules
install -m 0644 deploy/udev/49-usb-enforcer.rules %{buildroot}%{_udevrulesdir}/
install -m 0644 deploy/udev/80-udisks2-usb-enforcer.rules %{buildroot}%{_udevrulesdir}/

# Install polkit rules
install -m 0644 deploy/polkit/49-usb-enforcer.rules %{buildroot}%{_sysconfdir}/polkit-1/rules.d/

# Install dbus configuration
install -m 0644 deploy/dbus/org.seravault.UsbEnforcer.conf %{buildroot}%{_sysconfdir}/dbus-1/system.d/

# Install systemd units
install -m 0644 deploy/systemd/usb-enforcerd.service %{buildroot}%{_unitdir}/
install -m 0644 deploy/systemd/usb-enforcer-ui.service %{buildroot}%{_userunitdir}/

# Install icon and desktop file
install -m 0644 deploy/icons/usb-enforcer.svg %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/
install -m 0644 deploy/desktop/usb-enforcer-wizard.desktop %{buildroot}%{_datadir}/applications/

# Install AppStream metadata for package managers
install -m 0644 deploy/appdata/org.seravault.UsbEnforcer.metainfo.xml %{buildroot}%{_datadir}/metainfo/

# Create systemd drop-in files
cat > %{buildroot}%{_unitdir}/usb-enforcerd.service.d/env.conf <<'EOF'
[Service]
Environment=PYTHONPATH=%{_libdir}/usb-enforcer
Environment=PATH=%{_libdir}/usb-enforcer/.venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin
EOF

cat > %{buildroot}%{_userunitdir}/usb-enforcer-ui.service.d/env.conf <<'EOF'
[Service]
Environment=PYTHONPATH=%{_libdir}/usb-enforcer
Environment=PATH=%{_libdir}/usb-enforcer/.venv/bin:/usr/local/bin:/usr/bin
EOF

%post
# Create virtualenv with system site packages and install from bundled wheels (no network required)
if [ $1 -eq 1 ]; then
    # Fresh install
    python3 -m venv --system-site-packages %{_libdir}/usb-enforcer/.venv
    %{_libdir}/usb-enforcer/.venv/bin/pip install --upgrade pip --no-index --find-links %{_libdir}/usb-enforcer/wheels >/dev/null 2>&1
    %{_libdir}/usb-enforcer/.venv/bin/pip install --no-index --find-links %{_libdir}/usb-enforcer/wheels \
        pyudev pydbus typing-extensions python-magic \
        pdfplumber python-docx openpyxl python-pptx odfpy \
        py7zr rarfile fusepy \
        xlrd olefile extract-msg striprtf >/dev/null 2>&1
fi

# Update icon cache
if [ -x %{_bindir}/gtk-update-icon-cache ]; then
    %{_bindir}/gtk-update-icon-cache -f -t %{_datadir}/icons/hicolor >/dev/null 2>&1 || :
fi

# Update desktop database
if [ -x %{_bindir}/update-desktop-database ]; then
    %{_bindir}/update-desktop-database %{_datadir}/applications >/dev/null 2>&1 || :
fi

%systemd_post usb-enforcerd.service

# Reload udev rules
udevadm control --reload >/dev/null 2>&1 || :

# Enable user service for all users
mkdir -p %{_userunitdir}/default.target.wants
ln -sf %{_userunitdir}/usb-enforcer-ui.service \
    %{_userunitdir}/default.target.wants/usb-enforcer-ui.service 2>/dev/null || :

%preun
%systemd_preun usb-enforcerd.service

# Stop user services for all active users
for user_runtime in /run/user/*; do
    if [ -d "$user_runtime" ]; then
        uid=$(basename "$user_runtime")
        username=$(id -nu "$uid" 2>/dev/null || echo "")
        if [ -n "$username" ] && [ "$username" != "root" ]; then
            su - "$username" -c "XDG_RUNTIME_DIR=$user_runtime systemctl --user stop usb-enforcer-ui.service" 2>/dev/null || :
        fi
    fi
done

%postun
%systemd_postun_with_restart usb-enforcerd.service

# Reload udev rules
if [ $1 -eq 0 ]; then
    # Complete removal
    udevadm control --reload >/dev/null 2>&1 || :
    rm -f %{_userunitdir}/default.target.wants/usb-enforcer-ui.service 2>/dev/null || :
    rm -rf %{_libdir}/usb-enforcer/.venv 2>/dev/null || :
    rm -rf %{_libdir}/usb-enforcer/wheels 2>/dev/null || :
fi

%files
%doc README.md
%doc docs/USB-ENFORCER.md
%config(noreplace) %{_sysconfdir}/usb-enforcer/config.toml
%{_libdir}/usb-enforcer/usb_enforcer/
%{_libdir}/usb-enforcer/usb_enforcer_ui.py
%{_libdir}/usb-enforcer/wheels/
%{_libexecdir}/usb-enforcerd
%{_libexecdir}/usb-enforcer-helper
%{_libexecdir}/usb-enforcer-ui
%{_libexecdir}/usb-enforcer-wizard
%{_udevrulesdir}/49-usb-enforcer.rules
%{_udevrulesdir}/80-udisks2-usb-enforcer.rules
%{_sysconfdir}/polkit-1/rules.d/49-usb-enforcer.rules
%{_sysconfdir}/dbus-1/system.d/org.seravault.UsbEnforcer.conf
%{_unitdir}/usb-enforcerd.service
%{_unitdir}/usb-enforcerd.service.d/env.conf
%{_userunitdir}/usb-enforcer-ui.service
%{_userunitdir}/usb-enforcer-ui.service.d/env.conf
%{_datadir}/icons/hicolor/scalable/apps/usb-enforcer.svg
%{_datadir}/applications/usb-enforcer-wizard.desktop
%{_datadir}/metainfo/org.seravault.UsbEnforcer.metainfo.xml

%changelog
* Thu Jan 09 2025 Your Name <your.email@example.com> - 1.0.0-1
- Initial RPM package release with bundled Python dependencies
- USB encryption enforcement daemon with udev/polkit integration
- GTK4 wizard for device encryption and unlock
- Desktop notifications for USB events
