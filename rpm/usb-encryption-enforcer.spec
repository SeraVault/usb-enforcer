Name:           usb-encryption-enforcer
Version:        1.0.0
Release:        1%{?dist}
Summary:        USB data loss prevention for Linux desktops

License:        MIT
URL:            https://github.com/seravault/usb-encryption-enforcer
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch

BuildRequires:  python3-devel
BuildRequires:  python3-pip
BuildRequires:  python3-setuptools
BuildRequires:  systemd-rpm-macros

Requires:       python3 >= 3.8
Requires:       python3-pyudev >= 0.24.0
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

%description
USB Encryption Enforcer enforces encryption on USB mass-storage devices.
Plaintext USB devices are forced read-only, while LUKS2-encrypted devices
can be unlocked and mounted writable. A Python daemon watches udev, enforces
block-level read-only mode, and provides a DBus API. Includes a GTK wizard
for encryption/unlock flows and desktop notifications.

%prep
%setup -q

%build
# Pure Python, nothing to build

%install
# Set installation directories
export PREFIX=%{_prefix}
export LIBDIR=%{_libdir}/%{name}
export LIBEXEC=%{_libexecdir}
export CONFIG_DIR=%{_sysconfdir}/%{name}
export SYSTEMD_SYSTEM_DIR=%{_unitdir}
export SYSTEMD_USER_DIR=%{_userunitdir}
export POLKIT_DIR=%{_sysconfdir}/polkit-1/rules.d
export UDEV_DIR=%{_udevrulesdir}
export DBUS_DIR=%{_sysconfdir}/dbus-1/system.d

# Create directories
install -d %{buildroot}%{_libdir}/%{name}
install -d %{buildroot}%{_libexecdir}
install -d %{buildroot}%{_sysconfdir}/%{name}
install -d %{buildroot}%{_unitdir}
install -d %{buildroot}%{_userunitdir}
install -d %{buildroot}%{_sysconfdir}/polkit-1/rules.d
install -d %{buildroot}%{_udevrulesdir}
install -d %{buildroot}%{_sysconfdir}/dbus-1/system.d
install -d %{buildroot}%{_unitdir}/usb-encryption-enforcerd.service.d
install -d %{buildroot}%{_userunitdir}/usb-encryption-enforcer-ui.service.d

# Install Python package
cp -r src/usb_enforcer %{buildroot}%{_libdir}/%{name}/

# Install scripts
install -m 0755 scripts/usb-encryption-enforcerd %{buildroot}%{_libexecdir}/
install -m 0755 scripts/usb-encryption-enforcer-helper %{buildroot}%{_libexecdir}/
install -m 0755 scripts/usb-encryption-enforcer-ui %{buildroot}%{_libexecdir}/
install -m 0755 scripts/usb-encryption-enforcer-wizard %{buildroot}%{_libexecdir}/

# Install configuration
install -m 0644 deploy/config.toml.sample %{buildroot}%{_sysconfdir}/%{name}/config.toml

# Install udev rules
install -m 0644 deploy/udev/49-usb-encryption-enforcer.rules %{buildroot}%{_udevrulesdir}/
install -m 0644 deploy/udev/80-udisks2-usb-encryption-enforcer.rules %{buildroot}%{_udevrulesdir}/

# Install polkit rules
install -m 0644 deploy/polkit/49-usb-encryption-enforcer.rules %{buildroot}%{_sysconfdir}/polkit-1/rules.d/

# Install dbus configuration
install -m 0644 deploy/dbus/org.seravault.UsbEncryptionEnforcer.conf %{buildroot}%{_sysconfdir}/dbus-1/system.d/

# Install systemd units
install -m 0644 deploy/systemd/usb-encryption-enforcerd.service %{buildroot}%{_unitdir}/
install -m 0644 deploy/systemd/usb-encryption-enforcer-ui.service %{buildroot}%{_userunitdir}/

# Create systemd drop-in files
cat > %{buildroot}%{_unitdir}/usb-encryption-enforcerd.service.d/env.conf <<'EOF'
[Service]
Environment=PYTHONPATH=%{_libdir}/%{name}
Environment=PATH=%{_libdir}/%{name}/.venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin
EOF

cat > %{buildroot}%{_userunitdir}/usb-encryption-enforcer-ui.service.d/env.conf <<'EOF'
[Service]
Environment=PYTHONPATH=%{_libdir}/%{name}
Environment=PATH=%{_libdir}/%{name}/.venv/bin:/usr/local/bin:/usr/bin
EOF

%post
# Create virtualenv
if [ $1 -eq 1 ]; then
    # Fresh install
    python3 -m venv %{_libdir}/%{name}/.venv
    %{_libdir}/%{name}/.venv/bin/pip install --upgrade pip >/dev/null 2>&1
    %{_libdir}/%{name}/.venv/bin/pip install pyudev>=0.24.0 pydbus>=0.6.0 typing-extensions>=4.8.0 PyGObject>=3.46.0 >/dev/null 2>&1
fi

%systemd_post usb-encryption-enforcerd.service

# Reload udev rules
udevadm control --reload >/dev/null 2>&1 || :

# Enable user service for all users
mkdir -p %{_userunitdir}/default.target.wants
ln -sf %{_userunitdir}/usb-encryption-enforcer-ui.service \
    %{_userunitdir}/default.target.wants/usb-encryption-enforcer-ui.service 2>/dev/null || :

%preun
%systemd_preun usb-encryption-enforcerd.service

# Stop user services for all active users
for user_runtime in /run/user/*; do
    if [ -d "$user_runtime" ]; then
        uid=$(basename "$user_runtime")
        username=$(id -nu "$uid" 2>/dev/null || echo "")
        if [ -n "$username" ] && [ "$username" != "root" ]; then
            su - "$username" -c "XDG_RUNTIME_DIR=$user_runtime systemctl --user stop usb-encryption-enforcer-ui.service" 2>/dev/null || :
        fi
    fi
done

%postun
%systemd_postun_with_restart usb-encryption-enforcerd.service

# Reload udev rules
if [ $1 -eq 0 ]; then
    # Complete removal
    udevadm control --reload >/dev/null 2>&1 || :
    rm -f %{_userunitdir}/default.target.wants/usb-encryption-enforcer-ui.service 2>/dev/null || :
    rm -rf %{_libdir}/%{name}/.venv 2>/dev/null || :
fi

%files
%doc README.md
%doc docs/usb-encryption-enforcer.md
%config(noreplace) %{_sysconfdir}/%{name}/config.toml
%{_libdir}/%{name}/usb_enforcer/
%{_libexecdir}/usb-encryption-enforcerd
%{_libexecdir}/usb-encryption-enforcer-helper
%{_libexecdir}/usb-encryption-enforcer-ui
%{_libexecdir}/usb-encryption-enforcer-wizard
%{_udevrulesdir}/49-usb-encryption-enforcer.rules
%{_udevrulesdir}/80-udisks2-usb-encryption-enforcer.rules
%{_sysconfdir}/polkit-1/rules.d/49-usb-encryption-enforcer.rules
%{_sysconfdir}/dbus-1/system.d/org.seravault.UsbEncryptionEnforcer.conf
%{_unitdir}/usb-encryption-enforcerd.service
%{_unitdir}/usb-encryption-enforcerd.service.d/env.conf
%{_userunitdir}/usb-encryption-enforcer-ui.service
%{_userunitdir}/usb-encryption-enforcer-ui.service.d/env.conf

%changelog
* Thu Jan 09 2025 Your Name <your.email@example.com> - 1.0.0-1
- Initial RPM package release
- USB encryption enforcement daemon with udev/polkit integration
- GTK4 wizard for device encryption and unlock
- Desktop notifications for USB events
