#!/bin/bash
# Script that installs the NTURT Server as a systemd service

echo "Installing NTURT Server service..."

# Add execute permission to the startup script
chmod +x /home/pi/Desktop/GUI_SC-dev/start_server.sh

# Copy the service file to systemd directory
sudo cp /home/pi/Desktop/GUI_SC-dev/nturt-server.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable the service (start on boot)
sudo systemctl enable nturt-server.service

# Start the service
sudo systemctl start nturt-server.service

echo ""
echo "Installation complete!"
echo ""
echo "Common used commands:"
echo "  Check status: sudo systemctl status nturt-server"
echo "  Start service: sudo systemctl start nturt-server"
echo "  Stop service: sudo systemctl stop nturt-server"
echo "  Restart service: sudo systemctl restart nturt-server"
echo "  View logs: sudo journalctl -u nturt-server -f"
echo "  Disable boot startup: sudo systemctl disable nturt-server"
