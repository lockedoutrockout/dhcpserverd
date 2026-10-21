#!/bin/sh

#############################################################################################
# install.sh                                                                                #
#                                                                                           #
# Installation script. Must be ran as root. Developed/tested on OpenSUSE Leap 15.6. Doesn't #
# work on your distro? Open an issue and let me know what distribution you're using. Using  #
# Windows? Not supported.                                                                   #
#############################################################################################

SOURCE_DIR="/usr/lib/dhcpserverd"
CONFIG_DIR="/etc/dhcpserverd/config"
RSC_DIR="/etc/dhcpserverd/rsc"
SYSTEMD_UNIT_TARGET="/etc/systemd/system/dhcpserverd.service"
SECURITY_POLICY_TARGET="/usr/share/dbus-1/system.d/org.dhcpserverd.DHCPServer.conf"
BIN_TARGET="/usr/bin/dhcpserverd"

# Make sure running as root
if [[ "$EUID" -ne 0 ]]; then
	echo "This script must be ran as root! Quitting!"
	exit 1
fi

# Create necessary directories
mkdir -p "${SOURCE_DIR}"
mkdir -p "${CONFIG_DIR}"
mkdir -p "${RSC_DIR}"

# Move script to source directory
echo "Installing application files..."
cp -r dhcpserverd.py lib/ "${SOURCE_DIR}/"

# Create the launcher
echo "Creating launcher script..."
cat > "${BIN_TARGET}" <<EOF
#!/bin/sh
exec /usr/bin/env python3 ${SOURCE_DIR}/dhcpserverd.py "\$@"
EOF
chmod +x "${BIN_TARGET}"

# Move the configuration file
echo "Copying configuration file..."
cp config/dhcpserverd.ini "${CONFIG_DIR}"

# Copy other dependencies. Event handler scripts, etc.
cp rsc/event-script.sh "${RSC_DIR}"
chmod +x "${RSC_DIR}/event-script.sh"

# Set up the DBus interface
echo "Copying DBus interface definition and security policy..."
cp rsc/dbus-interface.xml "${RSC_DIR}"
cp rsc/security-policy.conf "${SECURITY_POLICY_TARGET}"

# Set up the systemd unit file
echo "Copying systemd unit..."
cp rsc/systemd-unit.service "${SYSTEMD_UNIT_TARGET}"

# Reload systemd
echo "Reloading systemd..."
systemctl daemon-reload

echo "Installation complete!"

