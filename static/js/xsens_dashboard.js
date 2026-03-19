// WebSocket Connection
const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

// Initialize Legacy GPS Map
let legacyMap = L.map('legacy-map').setView([0, 0], 2);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap contributors'
}).addTo(legacyMap);

let legacyMarker = null;
let legacyPathPoints = [];
let legacyPathPolyline = null;
let legacyMapInitialized = false;
let legacyTrackingEnabled = false;

// Initialize Xsens GPS Map
let xsensMap = L.map('xsens-map').setView([0, 0], 2);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap contributors'
}).addTo(xsensMap);

let xsensMarker = null;
let xsensPathPoints = [];
let xsensPathPolyline = null;
let xsensMapInitialized = false;
let xsensTrackingEnabled = false;

// GPS Map Update Functions
function updateLegacyGPSMap(lat, lon) {
    if (lat !== null && lon !== null && !isNaN(lat) && !isNaN(lon) && lat !== 0 && lon !== 0) {
        const latLng = [lat, lon];
        
        if (!legacyMapInitialized) {
            legacyMap.setView(latLng, 15);
            legacyMapInitialized = true;
        }
        
        if (legacyMarker) {
            legacyMarker.setLatLng(latLng);
        } else {
            const rippleIcon = L.divIcon({
                className: 'ripple-marker',
                html: '<div style="background: #f59e0b; width: 20px; height: 20px; border-radius: 50%; box-shadow: 0 0 10px rgba(245, 158, 11, 0.8);"></div>',
                iconSize: [20, 20],
                iconAnchor: [10, 10]
            });
            
            legacyMarker = L.marker(latLng, { icon: rippleIcon }).addTo(legacyMap)
                .bindPopup('Legacy GPS Position');
        }
        
        if (legacyTrackingEnabled) {
            legacyPathPoints.push(latLng);
            if (legacyPathPolyline) {
                legacyMap.removeLayer(legacyPathPolyline);
            }
            legacyPathPolyline = L.polyline(legacyPathPoints, {
                color: '#f59e0b',
                weight: 3,
                opacity: 0.7
            }).addTo(legacyMap);
        }
        
        if (legacyMap.getZoom() >= 10) {
            legacyMap.setView(latLng, legacyMap.getZoom());
        }
    }
}

function updateXsensGPSMap(lat, lon) {
    if (lat !== null && lon !== null && !isNaN(lat) && !isNaN(lon) && lat !== 0 && lon !== 0) {
        const latLng = [lat, lon];
        
        if (!xsensMapInitialized) {
            xsensMap.setView(latLng, 15);
            xsensMapInitialized = true;
        }
        
        if (xsensMarker) {
            xsensMarker.setLatLng(latLng);
        } else {
            const rippleIcon = L.divIcon({
                className: 'ripple-marker',
                html: '<div style="background: #3b82f6; width: 20px; height: 20px; border-radius: 50%; box-shadow: 0 0 10px rgba(59, 130, 246, 0.8);"></div>',
                iconSize: [20, 20],
                iconAnchor: [10, 10]
            });
            
            xsensMarker = L.marker(latLng, { icon: rippleIcon }).addTo(xsensMap)
                .bindPopup('Xsens GPS Position');
        }
        
        if (xsensTrackingEnabled) {
            xsensPathPoints.push(latLng);
            if (xsensPathPolyline) {
                xsensMap.removeLayer(xsensPathPolyline);
            }
            xsensPathPolyline = L.polyline(xsensPathPoints, {
                color: '#3b82f6',
                weight: 3,
                opacity: 0.7
            }).addTo(xsensMap);
        }
        
        if (xsensMap.getZoom() >= 10) {
            xsensMap.setView(latLng, xsensMap.getZoom());
        }
    }
}

// Chart Setup - Individual axis comparison charts
const maxDataPoints = 50;

// Acceleration X Chart
const accXChart = new Chart(document.getElementById('acc-x-chart').getContext('2d'), {
    type: 'line',
    data: {
        labels: [],
        datasets: [
            { 
                label: 'Xsens IMU', 
                data: [], 
                borderColor: 'rgb(59, 130, 246)', 
                backgroundColor: 'rgba(59, 130, 246, 0.1)',
                tension: 0.1,
                borderWidth: 2
            },
            { 
                label: 'IMU2', 
                data: [], 
                borderColor: 'rgb(239, 68, 68)', 
                backgroundColor: 'rgba(239, 68, 68, 0.1)',
                tension: 0.1,
                borderWidth: 2
            }
        ]
    },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        scales: {
            x: { display: false },
            y: { 
                beginAtZero: false,
                title: { display: true, text: 'm/s²' }
            }
        },
        plugins: {
            legend: { position: 'top' }
        }
    }
});

// Acceleration Y Chart
const accYChart = new Chart(document.getElementById('acc-y-chart').getContext('2d'), {
    type: 'line',
    data: {
        labels: [],
        datasets: [
            { 
                label: 'Xsens IMU', 
                data: [], 
                borderColor: 'rgb(59, 130, 246)', 
                backgroundColor: 'rgba(59, 130, 246, 0.1)',
                tension: 0.1,
                borderWidth: 2
            },
            { 
                label: 'IMU2', 
                data: [], 
                borderColor: 'rgb(239, 68, 68)', 
                backgroundColor: 'rgba(239, 68, 68, 0.1)',
                tension: 0.1,
                borderWidth: 2
            }
        ]
    },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        scales: {
            x: { display: false },
            y: { 
                beginAtZero: false,
                title: { display: true, text: 'm/s²' }
            }
        },
        plugins: {
            legend: { position: 'top' }
        }
    }
});

// Acceleration Z Chart
const accZChart = new Chart(document.getElementById('acc-z-chart').getContext('2d'), {
    type: 'line',
    data: {
        labels: [],
        datasets: [
            { 
                label: 'Xsens IMU', 
                data: [], 
                borderColor: 'rgb(59, 130, 246)', 
                backgroundColor: 'rgba(59, 130, 246, 0.1)',
                tension: 0.1,
                borderWidth: 2
            },
            { 
                label: 'IMU2', 
                data: [], 
                borderColor: 'rgb(239, 68, 68)', 
                backgroundColor: 'rgba(239, 68, 68, 0.1)',
                tension: 0.1,
                borderWidth: 2
            }
        ]
    },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        scales: {
            x: { display: false },
            y: { 
                beginAtZero: false,
                title: { display: true, text: 'm/s²' }
            }
        },
        plugins: {
            legend: { position: 'top' }
        }
    }
});

// Gyroscope X Chart
const gyroXChart = new Chart(document.getElementById('gyro-x-chart').getContext('2d'), {
    type: 'line',
    data: {
        labels: [],
        datasets: [
            { 
                label: 'Xsens IMU', 
                data: [], 
                borderColor: 'rgb(34, 197, 94)', 
                backgroundColor: 'rgba(34, 197, 94, 0.1)',
                tension: 0.1,
                borderWidth: 2
            },
            { 
                label: 'IMU2', 
                data: [], 
                borderColor: 'rgb(168, 85, 247)', 
                backgroundColor: 'rgba(168, 85, 247, 0.1)',
                tension: 0.1,
                borderWidth: 2
            }
        ]
    },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        scales: {
            x: { display: false },
            y: { 
                beginAtZero: false,
                title: { display: true, text: 'rad/s' }
            }
        },
        plugins: {
            legend: { position: 'top' }
        }
    }
});

// Gyroscope Y Chart
const gyroYChart = new Chart(document.getElementById('gyro-y-chart').getContext('2d'), {
    type: 'line',
    data: {
        labels: [],
        datasets: [
            { 
                label: 'Xsens IMU', 
                data: [], 
                borderColor: 'rgb(34, 197, 94)', 
                backgroundColor: 'rgba(34, 197, 94, 0.1)',
                tension: 0.1,
                borderWidth: 2
            },
            { 
                label: 'IMU2', 
                data: [], 
                borderColor: 'rgb(168, 85, 247)', 
                backgroundColor: 'rgba(168, 85, 247, 0.1)',
                tension: 0.1,
                borderWidth: 2
            }
        ]
    },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        scales: {
            x: { display: false },
            y: { 
                beginAtZero: false,
                title: { display: true, text: 'rad/s' }
            }
        },
        plugins: {
            legend: { position: 'top' }
        }
    }
});

// Gyroscope Z Chart
const gyroZChart = new Chart(document.getElementById('gyro-z-chart').getContext('2d'), {
    type: 'line',
    data: {
        labels: [],
        datasets: [
            { 
                label: 'Xsens IMU', 
                data: [], 
                borderColor: 'rgb(34, 197, 94)', 
                backgroundColor: 'rgba(34, 197, 94, 0.1)',
                tension: 0.1,
                borderWidth: 2
            },
            { 
                label: 'IMU2', 
                data: [], 
                borderColor: 'rgb(168, 85, 247)', 
                backgroundColor: 'rgba(168, 85, 247, 0.1)',
                tension: 0.1,
                borderWidth: 2
            }
        ]
    },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        scales: {
            x: { display: false },
            y: { 
                beginAtZero: false,
                title: { display: true, text: 'rad/s' }
            }
        },
        plugins: {
            legend: { position: 'top' }
        }
    }
});

// Update comparison chart function
function updateComparisonChart(chart, xsensValue, imu2Value) {
    if (chart.data.labels.length >= maxDataPoints) {
        chart.data.labels.shift();
        chart.data.datasets[0].data.shift();
        chart.data.datasets[1].data.shift();
    }
    
    const timestamp = new Date().toLocaleTimeString();
    chart.data.labels.push(timestamp);
    chart.data.datasets[0].data.push(xsensValue || 0);
    chart.data.datasets[1].data.push(imu2Value || 0);
    chart.update('none');
}

// Format value helper
function formatValue(value, decimals = 3) {
    if (value === null || value === undefined) return '--';
    return typeof value === 'number' ? value.toFixed(decimals) : '--';
}

// Update status indicator
function updateStatus(elementId, hasData) {
    const element = document.getElementById(elementId);
    if (element) {
        element.className = hasData ? 'status-indicator status-ok' : 'status-indicator status-fail';
    }
}

// WebSocket event handlers
ws.onopen = function() {
    console.log('WebSocket Connected');
    const statusEl = document.getElementById('connection-status');
    statusEl.className = 'connection-indicator connected';
    statusEl.innerHTML = '<span class="status-indicator"></span><span>Connected</span>';
};

ws.onerror = function(error) {
    console.error('WebSocket Error:', error);
};

ws.onclose = function() {
    console.log('WebSocket Disconnected');
    const statusEl = document.getElementById('connection-status');
    statusEl.className = 'connection-indicator disconnected';
    statusEl.innerHTML = '<span class="status-indicator"></span><span>Disconnected</span>';
    setTimeout(() => location.reload(), 5000);
};

// Calculate distance between two GPS coordinates (Haversine formula)
function calculateDistance(lat1, lon1, lat2, lon2) {
    const R = 6371e3; // Earth radius in meters
    const φ1 = lat1 * Math.PI / 180;
    const φ2 = lat2 * Math.PI / 180;
    const Δφ = (lat2 - lat1) * Math.PI / 180;
    const Δλ = (lon2 - lon1) * Math.PI / 180;

    const a = Math.sin(Δφ/2) * Math.sin(Δφ/2) +
                Math.cos(φ1) * Math.cos(φ2) *
                Math.sin(Δλ/2) * Math.sin(Δλ/2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));

    return R * c; // Distance in meters
}

// Update speed gauge
function updateSpeedGauge(gaugeId, speedTextId, speed, maxSpeed = 200) {
    const gauge = document.getElementById(gaugeId);
    const speedText = document.getElementById(speedTextId);
    
    if (gauge && speedText) {
        const circumference = 2 * Math.PI * 80; // radius = 80
        const percentage = Math.min(speed / maxSpeed, 1);
        const offset = circumference * (1 - percentage);
        
        gauge.style.strokeDashoffset = offset;
        speedText.textContent = Math.round(speed);
    }
}

// Update difference indicator
function updateDiffIndicator(elementId, value, thresholdGood, thresholdWarn, suffix = '') {
    const el = document.getElementById(elementId);
    if (el) {
        const absValue = Math.abs(value);
        let className = 'diff-indicator ';
        
        if (absValue <= thresholdGood) {
            className += 'diff-good';
        } else if (absValue <= thresholdWarn) {
            className += 'diff-warn';
        } else {
            className += 'diff-error';
        }
        
        el.className = className;
        el.textContent = `±${absValue.toFixed(suffix === 'm' ? 1 : 4)}${suffix}`;
    }
}

// Main data update handler
ws.onmessage = function(event) {
    const data = JSON.parse(event.data);
    
    // 更新连接状态显示
    const connectionStatus = document.getElementById('connection-status');
    if (data.vehicle_connected) {
        connectionStatus.className = 'connection-indicator connected';
        connectionStatus.innerHTML = `
            <span class="status-indicator"></span>
            <span>Connected</span>
        `;
    } else {
        connectionStatus.className = 'connection-indicator disconnected';
        connectionStatus.innerHTML = `
            <span class="status-indicator"></span>
            <span>Disconnected</span>
        `;
    }
    
    // Debug: Log received data with full structure
    console.log('Received data:', {
        hasXsens: !!data.xsens,
        hasGPS: !!data.gps,
        hasIMU2: !!data.imu2,
        hasVelocity: !!data.velocity,
        xsensGPS: data.xsens?.gps,
        legacyGPS: data.gps,
        xsensAcceleration: data.xsens?.acceleration,
        xsensVelocity: data.xsens?.velocity,
        imu2Full: data.imu2,
        xsensFull: data.xsens
    });
    
    // Update message count
    document.getElementById('message-count').textContent = data.message_count || 0;
    
    // Update Xsens data
    if (data.xsens) {
        const xsens = data.xsens;
        
        // Check if we have any data
        const hasGPSData = xsens.gps && (xsens.gps.lat !== null || xsens.gps.lon !== null);
        const hasIMUData = xsens.quaternion && xsens.quaternion.q0 !== null;
        const hasMagData = xsens.magnetic_field && xsens.magnetic_field.mag_x !== null;
        
        updateStatus('gps-status', hasGPSData);
        updateStatus('imu-status', hasIMUData);
        updateStatus('mag-status', hasMagData);
        
        // Xsens GPS Data
        let xsensLat = null, xsensLon = null, xsensAlt = null, xsensSpeed = 0;
        if (xsens.gps) {
            xsensLat = xsens.gps.lat;
            xsensLon = xsens.gps.lon;
            xsensAlt = xsens.gps.alt;
            
            document.getElementById('xsens-gps-lat').textContent = formatValue(xsensLat, 7) + '°';
            document.getElementById('xsens-gps-lon').textContent = formatValue(xsensLon, 7) + '°';
            document.getElementById('xsens-gps-alt').textContent = formatValue(xsensAlt, 2) + ' m';
            
            updateXsensGPSMap(xsensLat, xsensLon);
        }
        
        // Calculate Xsens speed from velocity
        if (xsens.velocity) {
            document.getElementById('xsens-vel-x').textContent = formatValue(xsens.velocity.vel_x, 3);
            document.getElementById('xsens-vel-y').textContent = formatValue(xsens.velocity.vel_y, 3);
            document.getElementById('xsens-vel-z').textContent = formatValue(xsens.velocity.vel_z, 3);
            
            if (xsens.velocity.vel_x !== null && xsens.velocity.vel_y !== null) {
                const speedMs = Math.sqrt(
                    xsens.velocity.vel_x ** 2 + 
                    xsens.velocity.vel_y ** 2
                );
                xsensSpeed = speedMs * 3.6; // km/h
                document.getElementById('xsens-gps-speed').textContent = formatValue(xsensSpeed, 2) + ' km/h';
                updateSpeedGauge('xsens-gauge-fill', 'xsens-gauge-speed', xsensSpeed);
            }
        }
        
        // Acceleration - Update comparison charts
        if (xsens.acceleration) {
            const xsensAccX = xsens.acceleration.acc_x || 0;
            const xsensAccY = xsens.acceleration.acc_y || 0;
            const xsensAccZ = xsens.acceleration.acc_z || 0;
            
            // Get IMU2 data (nested structure: imu2.accel.x/y/z)
            // Convert from g to m/s² by multiplying by 9.81
            const imu2AccX = (data.imu2?.accel?.x || 0) * 9.81;
            const imu2AccY = (data.imu2?.accel?.y || 0) * 9.81;
            const imu2AccZ = (data.imu2?.accel?.z || 0) * 9.81;
            
            updateComparisonChart(accXChart, xsensAccX, imu2AccX);
            updateComparisonChart(accYChart, xsensAccY, imu2AccY);
            updateComparisonChart(accZChart, xsensAccZ, imu2AccZ);
        }
        
        // Rate of Turn (Gyroscope) - Update comparison charts
        if (xsens.rate_of_turn) {
            const xsensGyrX = xsens.rate_of_turn.gyr_x || 0;
            const xsensGyrY = xsens.rate_of_turn.gyr_y || 0;
            const xsensGyrZ = xsens.rate_of_turn.gyr_z || 0;
            
            // Get IMU2 data (nested structure: imu2.gyro.x/y/z)
            const imu2GyrX = data.imu2?.gyro?.x || 0;
            const imu2GyrY = data.imu2?.gyro?.y || 0;
            const imu2GyrZ = data.imu2?.gyro?.z || 0;
            
            updateComparisonChart(gyroXChart, xsensGyrX, imu2GyrX);
            updateComparisonChart(gyroYChart, xsensGyrY, imu2GyrY);
            updateComparisonChart(gyroZChart, xsensGyrZ, imu2GyrZ);
        }
        
        // Delta V
        if (xsens.delta_v) {
            document.getElementById('xsens-deltav-x').textContent = formatValue(xsens.delta_v.x, 5);
            document.getElementById('xsens-deltav-y').textContent = formatValue(xsens.delta_v.y, 5);
            document.getElementById('xsens-deltav-z').textContent = formatValue(xsens.delta_v.z, 5);
        }
        
        // Delta Q
        if (xsens.delta_q) {
            document.getElementById('xsens-deltaq-w').textContent = formatValue(xsens.delta_q.dq0, 5);
            document.getElementById('xsens-deltaq-x').textContent = formatValue(xsens.delta_q.dq1, 5);
            document.getElementById('xsens-deltaq-y').textContent = formatValue(xsens.delta_q.dq2, 5);
            document.getElementById('xsens-deltaq-z').textContent = formatValue(xsens.delta_q.dq3, 5);
        }
    }

    // Legacy GPS comparison (outside xsens block)
    if (data.gps) {
        const legacyLat = data.gps.lat;
        const legacyLon = data.gps.lon;
        const legacyAlt = data.gps.alt;
        const legacySpeed = data.velocity?.speed_kmh || 0;
        
        document.getElementById('legacy-gps-lat').textContent = formatValue(legacyLat, 7) + '°';
        document.getElementById('legacy-gps-lon').textContent = formatValue(legacyLon, 7) + '°';
        document.getElementById('legacy-gps-alt').textContent = formatValue(legacyAlt, 2) + ' m';
        document.getElementById('legacy-gps-speed').textContent = formatValue(legacySpeed, 2) + ' km/h';
        updateSpeedGauge('legacy-gauge-fill', 'legacy-gauge-speed', legacySpeed);
        
        updateLegacyGPSMap(legacyLat, legacyLon);
        
        // Calculate differences only if xsens data exists
        if (data.xsens && data.xsens.gps) {
            const xsensLat = data.xsens.gps.lat;
            const xsensLon = data.xsens.gps.lon;
            const xsensAlt = data.xsens.gps.alt;
            
            // Calculate Xsens speed
            let xsensSpeed = 0;
            if (data.xsens.velocity && data.xsens.velocity.vel_x !== null && data.xsens.velocity.vel_y !== null) {
                const speedMs = Math.sqrt(
                    data.xsens.velocity.vel_x ** 2 + 
                    data.xsens.velocity.vel_y ** 2
                );
                xsensSpeed = speedMs * 3.6;
            }
            
            if (xsensLat !== null && legacyLat !== null) {
                const latDiff = xsensLat - legacyLat;
                const lonDiff = xsensLon - legacyLon;
                const altDiff = xsensAlt - legacyAlt;
                const speedDiff = xsensSpeed - legacySpeed;
                
                updateDiffIndicator('lat-diff', latDiff, 0.0001, 0.001);
                updateDiffIndicator('lon-diff', lonDiff, 0.0001, 0.001);
                updateDiffIndicator('alt-diff', altDiff, 5, 20, ' m');
                updateDiffIndicator('speed-diff', speedDiff, 2, 5, ' km/h');
                
                // Calculate distance difference
                const distance = calculateDistance(legacyLat, legacyLon, xsensLat, xsensLon);
                document.getElementById('gps-distance-diff').textContent = formatValue(distance, 2) + ' m';
            }
        }
    }
};

// GPS Tracking Controls
document.getElementById('toggle-legacy-track-btn').addEventListener('click', function() {
    legacyTrackingEnabled = !legacyTrackingEnabled;
    this.textContent = legacyTrackingEnabled ? 'Stop Track' : 'Start Track';
    this.style.background = legacyTrackingEnabled ? 'rgba(239, 68, 68, 0.5)' : 'rgba(34, 197, 94, 0.5)';
});

document.getElementById('clear-legacy-track-btn').addEventListener('click', function() {
    legacyPathPoints = [];
    if (legacyPathPolyline) {
        legacyMap.removeLayer(legacyPathPolyline);
        legacyPathPolyline = null;
    }
});

document.getElementById('toggle-xsens-track-btn').addEventListener('click', function() {
    xsensTrackingEnabled = !xsensTrackingEnabled;
    this.textContent = xsensTrackingEnabled ? 'Stop Track' : 'Start Track';
    this.style.background = xsensTrackingEnabled ? 'rgba(239, 68, 68, 0.5)' : 'rgba(34, 197, 94, 0.5)';
});

document.getElementById('clear-xsens-track-btn').addEventListener('click', function() {
    xsensPathPoints = [];
    if (xsensPathPolyline) {
        xsensMap.removeLayer(xsensPathPolyline);
        xsensPathPolyline = null;
    }
});

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
});