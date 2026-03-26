// Initialize WebSocket
const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

// Initialize Map
let map = L.map('map').setView([0, 0], 2);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap contributors'
}).addTo(map);

let vehicleMarker = null;
let pathPoints = [];
let pathPolyline = null;
let mapInitialized = false;
let trackingEnabled = false;

// GPS Tracking Controls
document.getElementById('toggle-track-btn').addEventListener('click', function() {
    trackingEnabled = !trackingEnabled;
    this.textContent = trackingEnabled ? 'Disable Track' : 'Enable Track';
    this.className = trackingEnabled ? 'btn-secondary text-sm' : 'btn-primary text-sm';
    
    if (!trackingEnabled && pathPolyline) {
        map.removeLayer(pathPolyline);
        pathPolyline = null;
    }
});

document.getElementById('clear-track-btn').addEventListener('click', function() {
    pathPoints = [];
    if (pathPolyline) {
        map.removeLayer(pathPolyline);
        pathPolyline = null;
    }
});

// Collapsible functionality
function toggleCollapsible(id) {
    const content = document.getElementById(id + '-content');
    const icon = document.getElementById(id + '-icon');
    
    if (content.classList.contains('active')) {
        content.classList.remove('active');
        icon.style.transform = 'rotate(0deg)';
    } else {
        content.classList.add('active');
        icon.style.transform = 'rotate(180deg)';
    }
}

// Initialize collapsible sections with content
function initializeCollapsibleSections() {
    // Initialize voltage segments
    const voltageContainer = document.getElementById('acc-cell-voltages');
    for (let i = 0; i < 7; i++) {
        const segmentDiv = document.createElement('div');
        segmentDiv.className = 'segment-container';
        segmentDiv.innerHTML = `
            <div class="text-xs text-gray-500 mb-1">
                Segment ${i} (Cells ${i*15}-${Math.min(i*15+14, 104)}) - Battery Pack ${i+1}
                <span id="segment-sum-${i}" class="ml-2 text-blue-600 font-bold"></span>
            </div>
            <div id="voltage-segment-${i}" class="value-display text-xs bg-white p-2 rounded max-h-24 overflow-y-auto">N/A</div>
        `;
        voltageContainer.appendChild(segmentDiv);
    }

    // Initialize temperature segments (224 cells, 7 segments of 32 each)
    const tempContainer = document.getElementById('acc-cell-temps');
    for (let i = 0; i < 7; i++) {
        const segmentDiv = document.createElement('div');
        segmentDiv.className = 'segment-container';
        segmentDiv.innerHTML = `
            <div class="text-xs text-gray-500 mb-1">
                Segment ${i} (Cells ${i*32}-${Math.min(i*32+31, 223)}) - Temperature Pack ${i+1}
                <span id="temp-segment-max-${i}" class="ml-2 text-orange-600 font-bold"></span>
            </div>
            <div id="temp-segment-${i}" class="value-display text-xs bg-white p-2 rounded max-h-24 overflow-y-auto">N/A</div>
        `;
        tempContainer.appendChild(segmentDiv);
    }
}

// Connection status
ws.onopen = function() {
    document.getElementById('connection-status').innerHTML = `
        <span class="heartbeat-indicator heartbeat-ok mr-2"></span>
        Connected
    `;
};

ws.onclose = function() {
    document.getElementById('connection-status').innerHTML = `
        <span class="heartbeat-indicator heartbeat-fail mr-2"></span>
        Disconnected
    `;
};

ws.onerror = function() {
    document.getElementById('connection-status').innerHTML = `
        <span class="heartbeat-indicator heartbeat-fail mr-2"></span>
        Error
    `;
};

// Data update handler
ws.onmessage = function(event) {
    const data = JSON.parse(event.data);
    
    // 更新连接状态显示
    const connectionStatus = document.getElementById('connection-status');
    if (data.vehicle_connected) {
        connectionStatus.innerHTML = `
            <span class="heartbeat-indicator heartbeat-ok mr-2"></span>
            Connected
        `;
        connectionStatus.className = 'text-sm text-green-300 flex items-center justify-end';
    } else {
        connectionStatus.innerHTML = `
            <span class="heartbeat-indicator heartbeat-fail mr-2"></span>
            Disconnected
        `;
        connectionStatus.className = 'text-sm text-red-300 flex items-center justify-end';
    }
    
    updateDisplay(data);
};

function formatValue(value, suffix = '', decimals = 2) {
    if (value === null || value === undefined) {
        return 'N/A';
    }
    if (typeof value === 'number') {
        return value.toFixed(decimals) + suffix;
    }
    return value.toString() + suffix;
}

function formatStatus(status) {
    if (status === null || status === undefined) {
        return '<span class="status-unknown">N/A</span>';
    }
    if (status === 1 || status === true) {
        return '<span class="status-ok">OK</span>';
    }
    return '<span class="status-bad">FAIL</span>';
}

function formatInverterStatus(status) {
    if (status === null || status === undefined) {
        return '<span class="status-unknown">N/A</span>';
    }
    INVready = false;
    INVenabled = false;
    INVfault = false;
    HV = false
    for (let i = 0; i < 8;i++) {
        if ((status[0]>>i) &0x01 ) {
            switch (i) {
                case 1:
                    INVready = true;
                    break;
                case 2:
                    INVenabled = true
                    break;
                case 3:
                    INVfault = true;
                    break;
                case 4:
                    HV = true;
                    break;
            }
        }
    }
    let statusText3 = '';
    let statusClass = 'status-unknown';
    ERRORstatus = status[1];
    switch (ERRORstatus) {
        case 0x0000:
            statusText3 = 'ERROR_NONE';
            break;
        case 0x0001:
            statusText3 = 'ERROR_INSTANT_OC';
            break;
        case 0x0002:
            statusText3 = 'ERROR_RMS_OC';
            break;
        case 0x0003:
            statusText3 = 'ERROR_INV_OT';
            break;
        case 0x0004:
            statusText3 = 'ERROR_MOT_OT';
            break;
        case 0x0005:
            statusText3 = 'ERROR_ENC';
            break;
        case 0x0006:
            statusText3 = 'ERROR_CAN_OT';
            break;
        case 0x0007:
            statusText3 = 'ERROR_GATE';
            break;
        case 0x0008:
            statusText3 = 'ERROR_HW_OC';
        default:
            statusText3 = 'Unknown Error';
            break;
    }

    return `<span class="${statusClass}"> Ready: ${INVready} - Enabled: ${INVenabled} - Fault: ${INVfault} - HV: ${HV}  -  ${statusText3}(${ERRORstatus})</span>`;
}

function formatCellSegments(cellArray, suffix = '', cellsPerSegment = 15) {
    if (!cellArray || !Array.isArray(cellArray)) {
        return Array(7).fill('N/A');
    }
    
    const segments = [];
    const totalCells = cellArray.length;
    const numSegments = 7;
    
    for (let segment = 0; segment < numSegments; segment++) {
        const startIndex = segment * cellsPerSegment;
        const endIndex = Math.min(startIndex + cellsPerSegment, totalCells);
        const segmentData = cellArray.slice(startIndex, endIndex);
        
        const formattedValues = [];
        for (let i = 0; i < cellsPerSegment && (startIndex + i) < totalCells; i++) {
            const value = segmentData[i];
            if (value !== null && value !== undefined) {
                formattedValues.push(`Cell${startIndex + i}: ${value.toFixed(2)}${suffix}`);
            } else {
                formattedValues.push(`Cell${startIndex + i}: N/A`);
            }
        }
        
        segments.push(formattedValues.join(', '));
    }
    
    return segments;
}

function updateCellSegments(data) {
    // Update voltage segments (105 cells, 15 per segment)
    if (data.accumulator && data.accumulator.cell_voltages) {
        const voltageSegments = formatCellSegments(data.accumulator.cell_voltages, 'V', 15);
        for (let i = 0; i < 7; i++) {
            const element = document.getElementById(`voltage-segment-${i}`);
            if (element) {
                element.textContent = voltageSegments[i];
            }
            // segment sum
            const sumElement = document.getElementById(`segment-sum-${i}`);
            if (sumElement) {
                const start = i * 15;
                const end = Math.min(start + 15, data.accumulator.cell_voltages.length);
                let sum = 0;
                let count = 0;
                for (let j = start; j < end; j++) {
                    const v = data.accumulator.cell_voltages[j];
                    if (v !== null && v !== undefined && v > 0) {
                        sum += v;
                        count++;
                    }
                }
                sumElement.textContent = count > 0 ? `Σ=${sum.toFixed(2)}V` : '';
            }
        }
    }
    
    // Update temperature segments (224 cells, 32 per segment)
    if (data.accumulator && data.accumulator.cell_temperatures) {
        const tempSegments = formatCellSegments(data.accumulator.cell_temperatures, '°C', 32);
        for (let i = 0; i < 7; i++) {
            const element = document.getElementById(`temp-segment-${i}`);
            if (element) {
                element.textContent = tempSegments[i];
            }
            // 溫度最高值顯示
            const maxElement = document.getElementById(`temp-segment-max-${i}`);
            if (maxElement) {
                const start = i * 32;
                const end = Math.min(start + 32, data.accumulator.cell_temperatures.length);
                let max = null;
                for (let j = start; j < end; j++) {
                    const t = data.accumulator.cell_temperatures[j];
                    if (t !== null && t !== undefined && t !== -13) {
                        if (max === null || t > max) max = t;
                    }
                }
                maxElement.textContent = max !== null ? `Max=${max.toFixed(2)}°C` : '';
            }
        }
    }
}

function updateHeartbeat(elementId, status) {
    const element = document.getElementById(elementId);
    if (!element) return;
    
    if (status === true) {
        element.className = 'heartbeat-indicator heartbeat-ok';
    } else {
        element.className = 'heartbeat-indicator heartbeat-fail';
    }
}

function updateInverterHeartbeat(invNum, status) {
    const element = document.querySelector(`[data-inv="${invNum}"]`);
    if (!element) return;
    
    if (status === true) {
        element.className = 'heartbeat-indicator heartbeat-ok';
    } else {
        element.className = 'heartbeat-indicator heartbeat-fail';
    }
}

function updateBatteryInfoBar(accumulator) {
    if (!accumulator) return;
    
    // Update SOC (State of Charge)
    const socElement = document.getElementById('battery-soc-value');
    const socBarElement = document.getElementById('battery-soc-bar');
    if (accumulator.soc !== null && accumulator.soc !== undefined) {
        const socPercent = Math.max(0, Math.min(100, accumulator.soc));
        if (socElement) socElement.textContent = `${socPercent}%`;
        if (socBarElement) {
            socBarElement.style.width = `${socPercent}%`;
            // 根據電量變更顏色
            if (socPercent > 50) {
                socBarElement.className = 'battery-bar bg-green-500 h-full rounded transition-all duration-300';
            } else if (socPercent > 20) {
                socBarElement.className = 'battery-bar bg-yellow-500 h-full rounded transition-all duration-300';
            } else {
                socBarElement.className = 'battery-bar bg-red-500 h-full rounded transition-all duration-300';
            }
        }
    }
    
    // Update Battery Temperature
    const tempElement = document.getElementById('battery-temp-value');
    if (accumulator.temperature !== null && accumulator.temperature !== undefined && tempElement) {
        tempElement.textContent = `${accumulator.temperature.toFixed(1)}°C`;
        // 根據溫度變更顏色
        if (accumulator.temperature > 60) {
            tempElement.className = 'text-red-400 font-bold text-xl';
        } else if (accumulator.temperature > 45) {
            tempElement.className = 'text-yellow-400 font-bold text-xl';
        } else {
            tempElement.className = 'text-green-400 font-bold text-xl';
        }
    }
    
    // Calculate and update Total Voltage (sum of all cell voltages)
    const voltageElement = document.getElementById('battery-voltage-value');
    const cellCountElement = document.getElementById('battery-cells-count');
    if (accumulator.cell_voltages && Array.isArray(accumulator.cell_voltages)) {
        let totalVoltage = 0;
        let validCells = 0;
        
        accumulator.cell_voltages.forEach(voltage => {
            if (voltage !== null && voltage !== undefined && voltage !== -13 && voltage > 0) {
                totalVoltage += voltage;
                validCells++;
            }
        });
        
        if (voltageElement) {
            voltageElement.textContent = `${totalVoltage.toFixed(1)}V`;
        }
        if (cellCountElement) {
            cellCountElement.textContent = `${validCells} cells`;
        }
    }
    
    // Update Pack Voltage from direct reading
    const packVoltageElement = document.getElementById('battery-pack-voltage');
    if (accumulator.voltage !== null && accumulator.voltage !== undefined && packVoltageElement) {
        packVoltageElement.textContent = `${accumulator.voltage.toFixed(1)}V`;
    }
    
    // Update Current
    const currentElement = document.getElementById('battery-current-value');
    if (accumulator.current !== null && accumulator.current !== undefined && currentElement) {
        currentElement.textContent = `${accumulator.current.toFixed(2)}A`;
        // 根據電流方向變更顏色 (正值充電，負值放電)
        if (accumulator.current > 0) {
            currentElement.className = 'text-green-400 font-bold';
        } else {
            currentElement.className = 'text-orange-400 font-bold';
        }
    }
}

function updateGPSMap(lat, lon) {
    if (lat !== null && lon !== null && lat !== undefined && lon !== undefined && 
        !isNaN(lat) && !isNaN(lon) && lat !== 0 && lon !== 0) {
        const latLng = [lat, lon];
        
        if (!mapInitialized) {
            map.setView(latLng, 15);
            mapInitialized = true;
        }
        
        if (vehicleMarker) {
            vehicleMarker.setLatLng(latLng);
        } else {
            const rippleIcon = L.divIcon({
                className: 'ripple-marker',
                html: '',
                iconSize: [20, 20],
                iconAnchor: [10, 10]
            });
            
            vehicleMarker = L.marker(latLng, { icon: rippleIcon }).addTo(map)
                .bindPopup('Vehicle Position');
        }
        
        // Update tracking path
        if (trackingEnabled) {
            pathPoints.push(latLng);
            if (pathPolyline) {
                map.removeLayer(pathPolyline);
            }
            pathPolyline = L.polyline(pathPoints, {
                color: 'red',
                weight: 3,
                opacity: 0.7
            }).addTo(map);
        }
        
        if (map.getZoom() >= 10) {
            map.setView(latLng, map.getZoom());
        }
    }
}

function updateDisplay(data) {
    // Update message count
    document.getElementById('message-count').textContent = data.message_count || 0;
    
    // Update last update time
    if (data.update_time) {
        const updateTime = new Date(data.update_time);
        document.getElementById('last-update').textContent = updateTime.toLocaleString();
    }
    
    // Update dashboard speed display
    if (data.velocity && data.velocity.speed_kmh !== null) {
        document.getElementById('dashboard-speed').textContent = Math.round(data.velocity.speed_kmh || 0);
    }
    
    // Update dashboard SOC and voltage
    if (data.accumulator) {
        document.getElementById('dashboard-soc').textContent = 
            data.accumulator.soc !== null ? data.accumulator.soc + '%' : '--';
        document.getElementById('dashboard-voltage').textContent = 
            data.accumulator.voltage !== null ? formatValue(data.accumulator.voltage, 'V', 1) : '--';
        document.getElementById('dashboard-temp').textContent = 
            data.accumulator.temperature !== null ? formatValue(data.accumulator.temperature, '°C', 1) : '--°C';
    }
    
    // Update VCU data
    if (data.vcu) {
        document.getElementById('vcu-steer').textContent = formatValue(-data.vcu.steer, '°', 1); // invert steering angle for display
        document.getElementById('vcu-accel').textContent = formatValue(data.vcu.accel, '%', 0);
        document.getElementById('vcu-apps1').textContent = formatValue(data.vcu.apps1, '', 0);
        document.getElementById('vcu-apps2').textContent = formatValue(data.vcu.apps2, '', 0);
        document.getElementById('vcu-brake').textContent = formatValue(data.vcu.brake, '%', 0);
        document.getElementById('vcu-bse1').textContent = formatValue(data.vcu.bse1, '', 0);
        document.getElementById('vcu-bse2').textContent = formatValue(data.vcu.bse2, '', 0);
    }
    
    // Update GPS data
    if (data.gps) {
        document.getElementById('gps-lat').textContent = formatValue(data.gps.lat, '°', 7);
        document.getElementById('gps-lon').textContent = formatValue(data.gps.lon, '°', 7);
        document.getElementById('gps-alt').textContent = formatValue(data.gps.alt, 'm', 1);
        document.getElementById('gps-status').innerHTML = data.gps.status !== null ? 
            `0x${data.gps.status.toString(16).toUpperCase().padStart(2, '0')}` : 'N/A';
        
        updateGPSMap(data.gps.lat, data.gps.lon);
    }
    
    // Update velocity data
    if (data.velocity) {
        document.getElementById('vel-linear-x').textContent = formatValue(data.velocity.linear_x, ' m/s', 3);
        document.getElementById('vel-linear-y').textContent = formatValue(data.velocity.linear_y, ' m/s', 3);
        document.getElementById('vel-linear-z').textContent = formatValue(data.velocity.linear_z, ' m/s', 3);
        document.getElementById('vel-angular-x').textContent = formatValue(data.velocity.angular_x, ' rad/s', 3);
        document.getElementById('vel-angular-y').textContent = formatValue(data.velocity.angular_y, ' rad/s', 3);
        document.getElementById('vel-angular-z').textContent = formatValue(data.velocity.angular_z, ' rad/s', 3);
        document.getElementById('vel-magnitude').textContent = formatValue(data.velocity.magnitude, ' m/s', 3);
        document.getElementById('vel-speed').textContent = formatValue(data.velocity.speed_kmh, ' km/h', 2);
    }
    
    // Update accumulator data
    if (data.accumulator) {
        document.getElementById('acc-soc').textContent = formatValue(data.accumulator.soc, '%', 0);
        document.getElementById('acc-voltage').textContent = formatValue(data.accumulator.voltage, 'V', 2);
        document.getElementById('acc-current').textContent = formatValue(data.accumulator.current, 'A', 2);
        document.getElementById('acc-temperature').textContent = formatValue(data.accumulator.temperature, '°C', 1);
        document.getElementById('acc-status').innerHTML = formatStatus(data.accumulator.status);
        document.getElementById('acc-capacity').textContent = formatValue(data.accumulator.capacity, 'Ah', 1);
        
        updateCellSegments(data);
        updateHeartbeat('acc-heartbeat', data.accumulator.heartbeat);
        updateHeartbeat('sys-acc-heartbeat', data.accumulator.heartbeat);
        
        // Update Battery Information Bar
        updateBatteryInfoBar(data.accumulator);
    }
    
    // Update inverter data
    if (data.inverters) {
        for (let invNum = 1; invNum <= 4; invNum++) {
            const inv = data.inverters[invNum];
            if (inv) {
                const container = document.getElementById(`inverter-${invNum}`);
                if (container) {
                    container.querySelector('.inv-status').innerHTML = formatInverterStatus(inv.status);
                    container.querySelector('.inv-torque').textContent = formatValue(inv.torque, '', 3);
                    container.querySelector('.inv-speed').textContent = formatValue(inv.speed, ' RPM', 0);
                    container.querySelector('.inv-dc-voltage').textContent = formatValue(inv.dc_voltage, 'V', 1);
                    container.querySelector('.inv-dc-current').textContent = formatValue(inv.dc_current, 'A', 1);
                    container.querySelector('.inv-mos-temp').textContent = formatValue(inv.mos_temp, '°C', 1);
                    container.querySelector('.inv-mcu-temp').textContent = formatValue(inv.mcu_temp, '°C', 1);
                    container.querySelector('.inv-motor-temp').textContent = formatValue(inv.motor_temp, '°C', 1);
                    container.querySelector('.inv-heartbeat').innerHTML = formatStatus(inv.heartbeat);
                }
                // 新增：同步更新標題後方的RPM
                const rpmSpan = document.getElementById(`inv${invNum}-rpm`);
                if (rpmSpan) {
                    rpmSpan.textContent = `SPEED: ${inv.speed !== null && inv.speed !== undefined ? Math.round(inv.speed * 20 * 2.54 * 3.14 * 60 / 1350000, 2) : 'N/A'} km/h`;
                }
                updateInverterHeartbeat(invNum, inv.heartbeat);
            }
        }
    }
}

// Initialize the page
document.addEventListener('DOMContentLoaded', function() {
    initializeCollapsibleSections();
    
    // Initial data fetch
    fetch('/api/data')
        .then(response => response.json())
        .then(data => updateDisplay(data))
        .catch(error => console.error('Error fetching initial data:', error));
});