# NTURT CAN Monitor - Client/Server Configuration

## Client Configuration
### Modify the following parameters on the vehicle RPI:

    - Server URL
    SERVER_URL = "ws://YOUR_SERVER_IP:8889"
    For example: "ws://100.127.237.75:8889" or "ws://192.168.1.100:8889"

    - Reconnect delay (seconds)
    RECONNECT_DELAY = 5

    - Heartbeat interval
    HEARTBEAT_INTERVAL = 1

    - Logs
    LOGS_DIR = ../LOGS

## Server Configuration
### Modify the following parameters on the remote RPI:

    - Web server port
    WEB_PORT = 8888

    - Vehicle data receiving port
    DATA_PORT = 8889

## Deployment 

### 1. Vehicle side
    
    - Steps：
    1. Copy client_vehicle_bidir.py to the vehicle RPI
    2. Modify SERVER_URL to your server IP address
    3. Ensure CAN interface is configured (can0, can1) 
    4. Execute: python3 client_vehicle_bidir.py
    
    - Dependencies：
    asyncio
    python-can
    websockets

### 2. Server side

    - Steps：
    1. Copy server_remote_bidir.py to the remote RPI
    2. Ensure directories templates/ and static/ exist
    3. Execute: python3 server_remote_bidir.py
    4. Visit in browser: http://SERVER_IP:8888
    
    - Dependencies：
    fastapi
    uvicorn
    websockets
    jinja2
    cantools

### 3. Network configuration
    
    - Ensure vehicle RPI and server RPI is in the same network or can connect to each other
    - If using Tailscale, using Tailscale IP address is allowed
    - Ensure firewall permits port 8888 (web page) and 8889 (data)

## 4. Auto-start (Optional)
    
    Use systemd service:
    
    Vehicle side: /etc/systemd/system/can-client.service

    # [Unit]
    # Description=CAN Data Client
    # After=network.target
    #
    # [Service]
    # Type=simple
    # User=pi
    # WorkingDirectory=/home/pi/GUI-dev
    # ExecStart=/usr/bin/python3 /home/pi/GUI-dev/client_vehicle_bidir.py
    # Restart=always
    #
    # [Install]
    # WantedBy=multi-user.target
    
    Server side: /etc/systemd/system/nturt-server.service
    
    # [Unit]
    # Description=NTURT CAN Monitor Server - Remote Side
    # After=network.target

    # [Service]
    # Type=simple
    # User=pi
    # WorkingDirectory=/home/pi/Desktop/GUI_SC-dev
    # ExecStart=/usr/bin/python3 /home/pi/Desktop/GUI_SC-dev/server_remote.py
    # Restart=always
    # RestartSec=10
    # StandardOutput=journal
    # StandardError=journal

    # # Enviromental variables
    # Environment="PYTHONUNBUFFERED=1"

    # [Install]
    # WantedBy=multi-user.target
    
    Enable and start service：
    sudo systemctl enable can-client  # client side
    sudo systemctl enable can-server  # server side
    sudo systemctl start can-client
    sudo systemctl start can-server

### 5. Connection testing
    
    1. Start server side
    2. Start vehicle side
    3. Check if the vehicle side shows "Connected to server successfully!"
    4. Visit server web page in browser and check if data is updating
    5. Visit http://SERVER_IP:8888/api/status to check connection status

## Troubleshooting

### Connection problem

    - Check network connection
    - Check firewall settings
    - Ensure SERVER_URL is configured correctly
    - Check server log
    - Check if Tailscale is expired

### Data not updating

    - Ensure CAN interface is working correctly
    - Check if vehicle side is sending data normally
    - Check if server side has received any data
    - Check message_count in /api/status

### Performance optimization

    - Modify HEARTBEAT_INTERVAL: reduce heartbeat frequency
    - Modify sleep time in broacaster_loop of server
    - Check network bandwidth and delay
