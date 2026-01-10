#!/bin/bash
# Example script to set up group-based USB enforcement exemptions
# Run with: sudo ./setup-exemption-group.sh

set -e

GROUP_NAME="usb-exempt"
CONFIG_FILE="/etc/usb-encryption-enforcer/config.toml"

echo "Setting up USB enforcement exemption group..."

# Create the exemption group if it doesn't exist
if ! getent group "$GROUP_NAME" > /dev/null 2>&1; then
    echo "Creating group: $GROUP_NAME"
    groupadd "$GROUP_NAME"
else
    echo "Group $GROUP_NAME already exists"
fi

# Show current members
echo ""
echo "Current members of $GROUP_NAME:"
getent group "$GROUP_NAME" | cut -d: -f4

# Prompt to add users
echo ""
read -p "Enter username to add to $GROUP_NAME (or press Enter to skip): " USERNAME
if [ -n "$USERNAME" ]; then
    if id "$USERNAME" > /dev/null 2>&1; then
        usermod -aG "$GROUP_NAME" "$USERNAME"
        echo "Added $USERNAME to $GROUP_NAME"
        echo "Note: User must log out and back in for group membership to take effect"
    else
        echo "User $USERNAME not found"
        exit 1
    fi
fi

# Update config if it exists
echo ""
if [ -f "$CONFIG_FILE" ]; then
    echo "Config file exists: $CONFIG_FILE"
    if grep -q "exempted_groups" "$CONFIG_FILE"; then
        echo "Config already has exempted_groups setting"
        echo "Please manually edit $CONFIG_FILE to add '$GROUP_NAME' to exempted_groups list"
    else
        echo "Adding exempted_groups to config..."
        echo "" >> "$CONFIG_FILE"
        echo "# Group-based exemptions" >> "$CONFIG_FILE"
        echo "exempted_groups = [\"$GROUP_NAME\"]" >> "$CONFIG_FILE"
        echo "Added exempted_groups = [\"$GROUP_NAME\"] to $CONFIG_FILE"
    fi
else
    echo "Config file not found at $CONFIG_FILE"
    echo "After installing, add this line to your config:"
    echo "  exempted_groups = [\"$GROUP_NAME\"]"
fi

# Restart daemon if running
echo ""
if systemctl is-active --quiet usb-encryption-enforcerd; then
    read -p "Restart USB enforcement daemon to apply changes? [y/N]: " RESTART
    if [ "$RESTART" = "y" ] || [ "$RESTART" = "Y" ]; then
        systemctl restart usb-encryption-enforcerd
        echo "Daemon restarted"
    fi
else
    echo "Daemon not running. Start it with: sudo systemctl start usb-encryption-enforcerd"
fi

echo ""
echo "Setup complete!"
echo ""
echo "To add more users to the exemption group:"
echo "  sudo usermod -aG $GROUP_NAME username"
echo ""
echo "To remove a user from the exemption group:"
echo "  sudo gpasswd -d username $GROUP_NAME"
echo ""
echo "To view group members:"
echo "  getent group $GROUP_NAME"
