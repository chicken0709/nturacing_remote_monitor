// WebSocket 連接
const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
const wsUrl = `${protocol}://${window.location.host}/ws`;
let ws = new WebSocket(wsUrl);

ws.onopen = () => {
    document.getElementById('connection-indicator').className = 'w-3 h-3 rounded-full bg-green-500 status-indicator';
    document.getElementById('connection-text').textContent = 'System Running';
    document.getElementById('server-status').textContent = 'Running';
};

ws.onclose = () => {
    document.getElementById('connection-indicator').className = 'w-3 h-3 rounded-full bg-red-500';
    document.getElementById('connection-text').textContent = 'Connection Lost';
    document.getElementById('server-status').textContent = 'Offline';
    
    // 重新連接
    setTimeout(() => {
        ws = new WebSocket(wsUrl);
    }, 3000);
};

ws.onmessage = (event) => {
    try {
        const data = JSON.parse(event.data);
        if (data.message_count) {
            document.getElementById('message-count').textContent = data.message_count;
        }
        if (data.vehicle_clients !== undefined) {
            document.getElementById('client-count').textContent = data.vehicle_clients;
        }
    } catch (e) {
        console.error('Error parsing WebSocket data:', e);
    }
};

// 定期獲取狀態
async function updateStatus() {
    try {
        const response = await fetch('/api/status');
        const status = await response.json();
        document.getElementById('client-count').textContent = status.vehicle_clients || 0;
        document.getElementById('message-count').textContent = status.message_count || 0;
    } catch (e) {
        console.error('Failed to fetch status:', e);
    }
}

setInterval(updateStatus, 5000);
updateStatus();