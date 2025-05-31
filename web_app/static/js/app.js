// RUCKUS ZTP Agent Web Interface JavaScript

// Global state
let config = {};
let credentials = [];
let seedSwitches = [];
let baseConfigs = {};
let currentTab = 'config';
let statusUpdateInterval;
let topologyUpdateInterval;

// Initialize the application
document.addEventListener('DOMContentLoaded', function() {
    initializeApp();
});

async function initializeApp() {
    await loadConfig();
    await loadBaseConfigs();
    setupEventListeners();
    updateCredentialsList();
    updateSeedSwitchList();
    updateBaseConfigSelect();
    populateConfigForm();
    
    // Start status updates if on monitoring tab
    if (currentTab === 'monitoring') {
        startStatusUpdates();
    }
}

function setupEventListeners() {
    // Tab navigation
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            switchTab(e.target.dataset.tab);
        });
    });
    
    // Base config selection
    document.getElementById('base-config-select').addEventListener('change', updateConfigPreview);
    
    // File upload
    document.getElementById('config-file').addEventListener('change', handleFileSelect);
    
    // Auto-refresh for monitoring tab
    setInterval(async () => {
        if (currentTab === 'monitoring') {
            await updateStatus();
            await updateDeviceList();
        }
    }, 5000);
}

// Tab Management
function switchTab(tabName) {
    // Update tab buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');
    
    // Update tab content
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.remove('active');
    });
    document.getElementById(tabName).classList.add('active');
    
    currentTab = tabName;
    
    // Start/stop status updates
    if (tabName === 'monitoring') {
        startStatusUpdates();
        stopTopologyUpdates(); // Stop topology updates when switching away
    } else {
        stopStatusUpdates();
    }
    
    // Load topology if switching to topology tab
    if (tabName === 'topology') {
        refreshTopology();
        startTopologyUpdates(); // Start auto-refresh for topology
    } else {
        stopTopologyUpdates(); // Stop topology updates when switching away
    }
    
    // Load logs if switching to logs tab
    if (tabName === 'logs') {
        refreshLogs();
    }
}

// Configuration Management
async function loadConfig() {
    try {
        const response = await fetch('/api/config');
        config = await response.json();
        credentials = config.credentials || [];
        seedSwitches = config.seed_switches || [];
    } catch (error) {
        console.error('Failed to load config:', error);
        showNotification('Failed to load configuration', 'error');
    }
}

async function saveConfig() {
    try {
        // Collect form data
        const formConfig = {
            credentials: credentials,
            preferred_password: document.getElementById('preferred-password').value,
            seed_switches: seedSwitches,
            base_config_name: document.getElementById('base-config-select').value,
            openrouter_api_key: document.getElementById('openrouter-key').value,
            model: document.getElementById('model-select').value,
            management_vlan: parseInt(document.getElementById('management-vlan').value),
            wireless_vlans: document.getElementById('wireless-vlans').value.split(',').map(v => parseInt(v.trim())),
            ip_pool: document.getElementById('ip-pool').value,
            gateway: document.getElementById('gateway').value,
            dns_server: document.getElementById('dns-server').value,
            poll_interval: parseInt(document.getElementById('poll-interval').value)
        };
        
        const response = await fetch('/api/config', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(formConfig)
        });
        
        if (response.ok) {
            config = formConfig;
            showNotification('Configuration saved successfully', 'success');
        } else {
            throw new Error('Failed to save configuration');
        }
    } catch (error) {
        console.error('Failed to save config:', error);
        showNotification('Failed to save configuration', 'error');
    }
}

function populateConfigForm() {
    document.getElementById('preferred-password').value = config.preferred_password || '';
    document.getElementById('openrouter-key').value = config.openrouter_api_key || '';
    document.getElementById('model-select').value = config.model || 'anthropic/claude-3-5-haiku';
    document.getElementById('management-vlan').value = config.management_vlan || 10;
    document.getElementById('wireless-vlans').value = (config.wireless_vlans || [20, 30, 40]).join(',');
    document.getElementById('ip-pool').value = config.ip_pool || '192.168.10.0/24';
    document.getElementById('gateway').value = config.gateway || '192.168.10.1';
    document.getElementById('dns-server').value = config.dns_server || '192.168.10.2';
    document.getElementById('poll-interval').value = config.poll_interval || 60;
}

// Credential Management
function addCredential() {
    showModal('credential-modal');
}

function saveCredential() {
    const username = document.getElementById('modal-username').value;
    const password = document.getElementById('modal-password').value;
    
    if (!username || !password) {
        showNotification('Please enter both username and password', 'error');
        return;
    }
    
    credentials.push({ username, password });
    updateCredentialsList();
    closeModal('credential-modal');
    
    showNotification('Credential added successfully', 'success');
}

function removeCredential(index) {
    if (index === 0) return; // Can't remove default credential
    
    credentials.splice(index, 1);
    updateCredentialsList();
    showNotification('Credential removed', 'success');
}

function updateCredentialsList() {
    const container = document.querySelector('.credential-list');
    container.innerHTML = '';
    
    // Always show default credential first
    const defaultCred = document.createElement('div');
    defaultCred.className = 'credential-item default-credential';
    defaultCred.innerHTML = `
        <span class="credential-display">super / sp-admin (default)</span>
    `;
    container.appendChild(defaultCred);
    
    credentials.forEach((cred, index) => {
        if (index === 0 && cred.username === 'super' && cred.password === 'sp-admin') {
            return; // Skip if it's the default credential in the array
        }
        
        const credDiv = document.createElement('div');
        credDiv.className = 'credential-item';
        credDiv.innerHTML = `
            <span class="credential-display">${cred.username} / ${cred.password}</span>
            <button class="btn-small" onclick="removeCredential(${index})">Remove</button>
        `;
        container.appendChild(credDiv);
    });
}

// Seed Switch Management
function addSeedSwitch() {
    showModal('switch-modal');
}

function saveSeedSwitch() {
    const ip = document.getElementById('modal-switch-ip').value;
    
    if (!ip) {
        showNotification('Please enter an IP address', 'error');
        return;
    }
    
    // Validate IP address format
    const ipPattern = /^(\d{1,3}\.){3}\d{1,3}$/;
    if (!ipPattern.test(ip)) {
        showNotification('Please enter a valid IP address', 'error');
        return;
    }
    
    // Check for duplicates
    if (seedSwitches.find(sw => sw.ip === ip)) {
        showNotification('This IP address is already added', 'error');
        return;
    }
    
    // No credentials_id needed - will cycle through available credentials automatically
    seedSwitches.push({ ip });
    updateSeedSwitchList();
    closeModal('switch-modal');
    
    showNotification('Seed switch added successfully', 'success');
}

function removeSeedSwitch(index) {
    seedSwitches.splice(index, 1);
    updateSeedSwitchList();
    showNotification('Seed switch removed', 'success');
}

function updateSeedSwitchList() {
    const container = document.querySelector('.seed-switch-list');
    container.innerHTML = '';
    
    seedSwitches.forEach((switchConfig, index) => {
        const switchDiv = document.createElement('div');
        switchDiv.className = 'seed-switch-item';
        switchDiv.innerHTML = `
            <span class="credential-display">${switchConfig.ip} (auto-detect credentials)</span>
            <button class="btn-small" onclick="removeSeedSwitch(${index})">Remove</button>
        `;
        container.appendChild(switchDiv);
    });
}


function getCredentialName(credentialsId) {
    if (credentialsId === 0 || !credentials[credentialsId]) {
        return 'super / sp-admin (default)';
    }
    return `${credentials[credentialsId].username} / ${credentials[credentialsId].password}`;
}

// Base Configuration Management
async function loadBaseConfigs() {
    try {
        const response = await fetch('/api/base-configs');
        baseConfigs = await response.json();
        updateBaseConfigSelect();
        updateConfigPreview();
    } catch (error) {
        console.error('Failed to load base configs:', error);
        showNotification('Failed to load base configurations', 'error');
    }
}

function updateBaseConfigSelect() {
    const select = document.getElementById('base-config-select');
    select.innerHTML = '';
    
    Object.keys(baseConfigs).forEach(name => {
        const option = document.createElement('option');
        option.value = name;
        option.textContent = name;
        select.appendChild(option);
    });
    
    // Set selected value from config
    if (config.base_config_name && baseConfigs[config.base_config_name]) {
        select.value = config.base_config_name;
    }
}

function updateConfigPreview() {
    const selectedConfig = document.getElementById('base-config-select').value;
    const preview = document.getElementById('config-preview');
    
    if (selectedConfig && baseConfigs[selectedConfig]) {
        preview.value = baseConfigs[selectedConfig];
    } else {
        preview.value = '';
    }
}

function handleFileSelect(event) {
    const file = event.target.files[0];
    if (file) {
        document.getElementById('config-name').value = file.name.replace('.txt', '');
    }
}

async function uploadBaseConfig() {
    const nameInput = document.getElementById('config-name');
    const fileInput = document.getElementById('config-file');
    
    const name = nameInput.value.trim();
    const file = fileInput.files[0];
    
    if (!name || !file) {
        showNotification('Please enter a name and select a file', 'error');
        return;
    }
    
    try {
        const formData = new FormData();
        formData.append('file', file);
        
        const response = await fetch(`/api/base-configs?name=${encodeURIComponent(name)}`, {
            method: 'POST',
            body: formData
        });
        
        if (response.ok) {
            await loadBaseConfigs();
            document.getElementById('base-config-select').value = name;
            updateConfigPreview();
            
            // Clear form
            nameInput.value = '';
            fileInput.value = '';
            
            showNotification('Base configuration uploaded successfully', 'success');
        } else {
            throw new Error('Upload failed');
        }
    } catch (error) {
        console.error('Failed to upload base config:', error);
        showNotification('Failed to upload base configuration', 'error');
    }
}

// ZTP Process Management
async function startZTP() {
    try {
        // Save config first
        await saveConfig();
        
        // Switch to monitoring tab immediately and set starting state locally
        switchTab('monitoring');
        
        // Set UI to starting state immediately
        const statusElement = document.getElementById('ztp-status');
        const toggleButton = document.getElementById('ztp-toggle');
        if (statusElement && toggleButton) {
            statusElement.textContent = 'Starting...';
            statusElement.className = 'status-indicator starting';
            toggleButton.textContent = 'Starting...';
            toggleButton.disabled = true;
        }
        
        const response = await fetch('/api/ztp/start', {
            method: 'POST'
        });
        
        if (response.ok) {
            const result = await response.json();
            
            // Display the main message
            const notificationType = result.success ? 'success' : 'error';
            showNotification(result.message, notificationType);
            
            // Display connection errors if any
            if (result.errors && result.errors.length > 0) {
                // Show errors in the monitoring tab's error section
                const errorContainer = document.getElementById('error-messages') || createErrorContainer();
                errorContainer.innerHTML = '';
                
                result.errors.forEach(error => {
                    const errorDiv = document.createElement('div');
                    errorDiv.className = 'error-message';
                    errorDiv.textContent = error;
                    errorContainer.appendChild(errorDiv);
                });
                
                // Show notification for errors
                showNotification(`${result.errors.length} seed switch connection error(s) - check monitoring tab`, 'warning');
            }
        } else {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to start ZTP process');
        }
    } catch (error) {
        console.error('Failed to start ZTP:', error);
        showNotification(`Failed to start ZTP process: ${error.message}`, 'error');
    }
}

async function stopZTP() {
    try {
        const response = await fetch('/api/ztp/stop', {
            method: 'POST'
        });
        
        if (response.ok) {
            showNotification('ZTP process stopped', 'success');
        } else {
            throw new Error('Failed to stop ZTP process');
        }
    } catch (error) {
        console.error('Failed to stop ZTP:', error);
        showNotification('Failed to stop ZTP process', 'error');
    }
}

async function toggleZTP() {
    const statusElement = document.getElementById('ztp-status');
    const isRunning = statusElement.textContent.includes('Running');
    
    if (isRunning) {
        await stopZTP();
    } else {
        await startZTP();
    }
}

// Status Updates
function startStatusUpdates() {
    if (statusUpdateInterval) return;
    
    statusUpdateInterval = setInterval(async () => {
        await updateStatus();
        await updateDeviceList();
    }, 2000);
    
    // Update immediately
    updateStatus();
    updateDeviceList();
}

function stopStatusUpdates() {
    if (statusUpdateInterval) {
        clearInterval(statusUpdateInterval);
        statusUpdateInterval = null;
    }
}

// Topology auto-refresh functions
function startTopologyUpdates() {
    // Check if auto-refresh is enabled
    const autoRefreshToggle = document.getElementById('auto-refresh-toggle');
    if (!autoRefreshToggle || !autoRefreshToggle.checked) return;
    
    if (topologyUpdateInterval) return;
    
    topologyUpdateInterval = setInterval(async () => {
        refreshTopology();
    }, 10000); // Refresh every 10 seconds (less frequent than monitoring)
}

function stopTopologyUpdates() {
    if (topologyUpdateInterval) {
        clearInterval(topologyUpdateInterval);
        topologyUpdateInterval = null;
    }
}

function toggleAutoRefresh() {
    const autoRefreshToggle = document.getElementById('auto-refresh-toggle');
    if (autoRefreshToggle.checked) {
        // Auto-refresh enabled - start if on topology tab
        if (currentTab === 'topology') {
            startTopologyUpdates();
        }
    } else {
        // Auto-refresh disabled - stop updates
        stopTopologyUpdates();
    }
}

async function updateStatus() {
    try {
        const response = await fetch('/api/status');
        const status = await response.json();
        
        // Update status indicator
        const statusElement = document.getElementById('ztp-status');
        const toggleButton = document.getElementById('ztp-toggle');
        
        if (status.running) {
            statusElement.textContent = 'Running';
            statusElement.className = 'status-indicator running';
            toggleButton.textContent = 'Stop';
        } else if (status.starting) {
            statusElement.textContent = 'Starting...';
            statusElement.className = 'status-indicator starting';
            toggleButton.textContent = 'Starting...';
            toggleButton.disabled = true;
        } else {
            statusElement.textContent = 'Stopped';
            statusElement.className = 'status-indicator stopped';
            toggleButton.textContent = 'Start';
            toggleButton.disabled = false;
        }
        
        // Update counters
        document.getElementById('switches-discovered').textContent = status.switches_discovered;
        document.getElementById('switches-configured').textContent = status.switches_configured;
        document.getElementById('aps-discovered').textContent = status.aps_discovered;
        
    } catch (error) {
        console.error('Failed to update status:', error);
    }
}

async function updateDeviceList() {
    try {
        const response = await fetch('/api/devices');
        const devices = await response.json();
        
        const tbody = document.querySelector('#device-table tbody');
        tbody.innerHTML = '';
        
        devices.forEach(device => {
            const row = document.createElement('tr');
            
            // Format IP with seed indicator
            const ipDisplay = device.is_seed ? `${device.ip} (SEED)` : device.ip;
            
            // Format MAC address
            const macDisplay = device.mac || 'Unknown';
            
            // Format device type with seed indicator - properly capitalize AP
            let deviceType = device.device_type === 'ap' ? 'AP' : device.device_type.charAt(0).toUpperCase() + device.device_type.slice(1);
            const typeDisplay = deviceType + (device.is_seed ? ' (seed)' : '');
            
            // Format connection info (for APs)
            const connectionDisplay = device.device_type === 'ap' && device.connected_switch
                ? `${device.connected_switch}:${device.connected_port || '?'}`
                : 'N/A';
            
            // Format tasks/ports column
            let tasksPortsDisplay = '';
            if (device.device_type === 'switch') {
                // For switches, show AP ports and tasks
                const parts = [];
                if (device.ap_ports.length > 0) {
                    parts.push(`AP Ports: ${device.ap_ports.join(', ')}`);
                }
                if (device.tasks_completed.length > 0) {
                    parts.push(device.tasks_completed.join('; '));
                }
                tasksPortsDisplay = parts.length > 0 ? parts.join(' | ') : 'Ready';
            } else {
                // For APs, show tasks
                tasksPortsDisplay = device.tasks_completed.length > 0
                    ? device.tasks_completed.join('; ')
                    : 'Ready';
            }
            
            row.innerHTML = `
                <td><strong>${ipDisplay}</strong></td>
                <td>${macDisplay}</td>
                <td>${typeDisplay}</td>
                <td>${device.model || 'Unknown'}</td>
                <td>${device.serial || 'Unknown'}</td>
                <td><span class="status-${device.status}">${device.status}</span></td>
                <td>${connectionDisplay}</td>
                <td class="tasks-cell">${tasksPortsDisplay}</td>
            `;
            
            // Add special styling for seed switches
            if (device.is_seed) {
                row.classList.add('seed-device');
            }
            
            // Add SSH activity highlighting
            if (device.ssh_active) {
                row.classList.add('ssh-active');
            }
            
            tbody.appendChild(row);
        });
        
    } catch (error) {
        console.error('Failed to update device list:', error);
    }
}

// Helper function to normalize interface names to x/y/z format
function normalizeInterfaceName(interfaceName) {
    if (!interfaceName) return '';
    
    // Match pattern like "GigabitEthernet1/1/7", "10GigabitEthernet1/1/1", "FastEthernet1/1/1", etc.
    // and extract just the numeric portion (x/y/z)
    const match = interfaceName.match(/(?:\d*[Gg]igabit[Ee]thernet|[Ff]ast[Ee]thernet|[Ee]thernet)?(\d+\/\d+\/\d+)/);
    if (match) {
        return match[1]; // Return just the x/y/z portion
    }
    
    // If no match, return the original (might already be in x/y/z format)
    return interfaceName;
}

// Topology Visualization
function refreshTopology() {
    // Clear existing topology
    const svg = d3.select('#topology-svg');
    svg.selectAll('*').remove();
    
    // Get devices and create topology
    fetch('/api/devices')
        .then(response => response.json())
        .then(devices => {
            createTopologyDiagram(devices);
        })
        .catch(error => {
            console.error('Failed to load devices for topology:', error);
        });
}

function createTopologyDiagram(devices) {
    const svg = d3.select('#topology-svg');
    
    // Get dimensions from CSS or set defaults
    let width = svg.node().getBoundingClientRect().width;
    let height = svg.node().getBoundingClientRect().height;
    
    // Set minimum dimensions if container is not sized properly
    if (width < 100) width = 800;
    if (height < 100) height = 500;
    
    // Set SVG dimensions explicitly
    svg.attr('width', width).attr('height', height);
    
    // Create nodes and links
    const nodes = devices.map(device => {
        // Debug: Check what hostname data we're receiving
        if (device.device_type === 'switch') {
            console.log(`Switch ${device.ip}: hostname="${device.hostname}", model="${device.model}"`);
        }
        return {
            id: device.ip,
            type: device.device_type,
            hostname: device.hostname,
            model: device.model,
            status: device.status,
            mac: device.mac
        };
    });
    
    const links = [];
    
    // Create links based on AP-to-switch connections
    devices.forEach(device => {
        if (device.device_type === 'ap' && device.connected_switch) {
            // Find the switch device
            const switchDevice = devices.find(d => d.ip === device.connected_switch);
            if (switchDevice) {
                const normalizedConnectedPort = normalizeInterfaceName(device.connected_port);
                links.push({
                    source: device.ip,
                    target: device.connected_switch,
                    localPort: null, // APs don't have local port concept in this context
                    remotePort: normalizedConnectedPort,
                    sourceLabel: '', // APs don't have source interface label
                    targetLabel: normalizedConnectedPort || ''
                });
            }
        }
    });
    
    // Also look for switch-to-switch connections in neighbor data
    devices.forEach(device => {
        if (device.device_type === 'switch' && device.neighbors) {
            Object.entries(device.neighbors).forEach(([localPort, neighbor]) => {
                if (neighbor.type === 'switch' && neighbor.mgmt_address) {
                    const targetDevice = devices.find(d => d.ip === neighbor.mgmt_address);
                    if (targetDevice) {
                        // Check if link already exists (avoid duplicates)
                        const linkExists = links.some(link => 
                            (link.source === device.ip && link.target === neighbor.mgmt_address) ||
                            (link.source === neighbor.mgmt_address && link.target === device.ip)
                        );
                        if (!linkExists) {
                            // Get remote port, preferring port_description over port_id (which can be MAC)
                            let remotePort = neighbor.port_description || neighbor.port_id || neighbor.port || '';
                            
                            // If remotePort looks like a MAC address, try to use a cleaner fallback
                            if (remotePort && remotePort.includes(':') && remotePort.length >= 12) {
                                remotePort = neighbor.port || 'Unknown';
                            }
                            
                            // Normalize both interface names to x/y/z format
                            const normalizedLocalPort = normalizeInterfaceName(localPort);
                            const normalizedRemotePort = normalizeInterfaceName(remotePort);
                            
                            links.push({
                                source: device.ip,
                                target: neighbor.mgmt_address,
                                sourcePort: normalizedLocalPort,  // Interface on source switch
                                targetPort: normalizedRemotePort, // Interface on target switch
                                sourceLabel: normalizedLocalPort || '',
                                targetLabel: normalizedRemotePort || ''
                            });
                        }
                    }
                }
            });
        }
    });
    
    // Use the links as-is since we already check for duplicates above
    const uniqueLinks = links;
    
    // Create force simulation
    const simulation = d3.forceSimulation(nodes)
        .force('link', d3.forceLink(uniqueLinks).id(d => d.id).distance(100))
        .force('charge', d3.forceManyBody().strength(-300))
        .force('center', d3.forceCenter(width / 2, height / 2));
    
    // Add links
    const link = svg.append('g')
        .selectAll('line')
        .data(uniqueLinks)
        .enter().append('line')
        .attr('stroke', '#00ff88')
        .attr('stroke-opacity', 0.6)
        .attr('stroke-width', 2);
    
    // Add port labels on links - source side labels
    const sourceLinkLabels = svg.append('g')
        .selectAll('text')
        .data(uniqueLinks)
        .enter().append('text')
        .text(d => d.sourceLabel || '')
        .attr('font-family', 'Courier New, monospace')
        .attr('font-size', '10px')
        .attr('fill', '#00ff88')
        .attr('text-anchor', 'middle')
        .attr('dy', -5);
    
    // Add port labels on links - target side labels
    const targetLinkLabels = svg.append('g')
        .selectAll('text')
        .data(uniqueLinks)
        .enter().append('text')
        .text(d => d.targetLabel || '')
        .attr('font-family', 'Courier New, monospace')
        .attr('font-size', '10px')
        .attr('fill', '#00ff88')
        .attr('text-anchor', 'middle')
        .attr('dy', -5);
    
    // Create node groups for different shapes
    const nodeGroups = svg.append('g')
        .selectAll('g')
        .data(nodes)
        .enter().append('g')
        .call(d3.drag()
            .on('start', dragstarted)
            .on('drag', dragged)
            .on('end', dragended));
    
    // Add shapes based on device type
    nodeGroups.each(function(d) {
        const group = d3.select(this);
        const fillColor = d.status === 'configured' ? '#00ff88' : 
                         d.status === 'configuring' ? '#0088ff' :
                         d.status === 'discovered' ? '#ffaa00' : '#ff4444';
        
        if (d.type === 'switch') {
            // Rectangle for switches
            group.append('rect')
                .attr('width', 30)
                .attr('height', 20)
                .attr('x', -15)
                .attr('y', -10)
                .attr('fill', fillColor)
                .attr('stroke', '#ffffff')
                .attr('stroke-width', 2)
                .attr('rx', 3);
        } else {
            // Circle for APs
            group.append('circle')
                .attr('r', 12)
                .attr('fill', fillColor)
                .attr('stroke', '#ffffff')
                .attr('stroke-width', 2);
        }
    });
    
    // Store node groups for position updates
    const node = nodeGroups;
    
    // Add labels (hostname on top, IP below)
    const hostnameLabel = svg.append('g')
        .selectAll('text')
        .data(nodes)
        .enter().append('text')
        .text(d => {
            // Only show hostname if it exists and is not just the literal string "hostname"
            const hostname = d.hostname;
            if (hostname && hostname !== 'hostname' && hostname !== 'unknown' && hostname.trim() !== '') {
                return hostname;
            }
            return d.id; // Fallback to IP address
        })
        .attr('font-family', 'Courier New, monospace')
        .attr('font-size', '11px')
        .attr('fill', '#ffffff')
        .attr('text-anchor', 'middle')
        .attr('dy', -25);
        
    const ipLabel = svg.append('g')
        .selectAll('text')
        .data(nodes)
        .enter().append('text')
        .text(d => {
            // Only show IP if we have a real hostname (not just IP or literal "hostname")
            const hostname = d.hostname;
            if (hostname && hostname !== 'hostname' && hostname !== 'unknown' && hostname.trim() !== '' && hostname !== d.id) {
                return d.id;
            }
            return ''; // Don't show IP if hostname is missing or same as IP
        })
        .attr('font-family', 'Courier New, monospace')
        .attr('font-size', '9px')
        .attr('fill', '#cccccc')
        .attr('text-anchor', 'middle')
        .attr('dy', -12);
    
    // Add tooltips
    node.append('title')
        .text(d => `${d.hostname ? `Hostname: ${d.hostname}\n` : ''}IP: ${d.id}\nMAC: ${d.mac || 'Unknown'}\nType: ${d.type.toUpperCase()}\nModel: ${d.model || 'Unknown'}\nStatus: ${d.status}`);
    
    // Update positions on simulation tick
    simulation.on('tick', () => {
        link
            .attr('x1', d => d.source.x)
            .attr('y1', d => d.source.y)
            .attr('x2', d => d.target.x)
            .attr('y2', d => d.target.y);
        
        // Position source labels closer to source node
        sourceLinkLabels
            .attr('x', d => d.source.x + (d.target.x - d.source.x) * 0.25)
            .attr('y', d => d.source.y + (d.target.y - d.source.y) * 0.25);
        
        // Position target labels closer to target node  
        targetLinkLabels
            .attr('x', d => d.source.x + (d.target.x - d.source.x) * 0.75)
            .attr('y', d => d.source.y + (d.target.y - d.source.y) * 0.75);
        
        node
            .attr('transform', d => `translate(${d.x},${d.y})`);
        
        hostnameLabel
            .attr('x', d => d.x)
            .attr('y', d => d.y);
            
        ipLabel
            .attr('x', d => d.x)
            .attr('y', d => d.y);
    });
    
    // Drag functions
    function dragstarted(event, d) {
        if (!event.active) simulation.alphaTarget(0.3).restart();
        d.fx = d.x;
        d.fy = d.y;
    }
    
    function dragged(event, d) {
        d.fx = event.x;
        d.fy = event.y;
    }
    
    function dragended(event, d) {
        if (!event.active) simulation.alphaTarget(0);
        d.fx = null;
        d.fy = null;
    }
}

function exportTopology() {
    const svg = document.getElementById('topology-svg');
    const serializer = new XMLSerializer();
    const source = serializer.serializeToString(svg);
    
    const blob = new Blob([source], { type: 'image/svg+xml' });
    const url = URL.createObjectURL(blob);
    
    const a = document.createElement('a');
    a.href = url;
    a.download = 'network-topology.svg';
    a.click();
    
    URL.revokeObjectURL(url);
    showNotification('Topology diagram exported', 'success');
}

// AI Agent Functions
function handleChatKeyPress(event) {
    if (event.key === 'Enter') {
        sendChatMessage();
    }
}

async function sendChatMessage() {
    const input = document.getElementById('chat-input');
    const message = input.value.trim();
    
    if (!message) return;
    
    // Clear input
    input.value = '';
    
    // Add user message to chat
    addChatMessage(message, 'user');
    
    // Try WebSocket first, fallback to SSE
    try {
        await sendChatMessageWebSocket(message);
    } catch (error) {
        console.log('WebSocket failed, falling back to SSE:', error);
        await sendChatMessageSSE(message);
    }
}

async function sendChatMessageWebSocket(message) {
    // Create a streaming message container for the assistant response
    const streamingMessageId = 'streaming-' + Date.now();
    const messagesContainer = document.getElementById('chat-messages');
    
    const streamingDiv = document.createElement('div');
    streamingDiv.id = streamingMessageId;
    streamingDiv.className = 'chat-message assistant';
    
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    contentDiv.innerHTML = '<strong>AI Assistant:</strong><br><span class="streaming-content"></span>';
    
    streamingDiv.appendChild(contentDiv);
    messagesContainer.appendChild(streamingDiv);
    
    const streamingContent = streamingDiv.querySelector('.streaming-content');
    
    // Scroll to bottom
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
    
    return new Promise((resolve, reject) => {
        let isResolved = false; // Flag to prevent multiple resolve/reject calls
        
        // Create WebSocket connection
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const ws = new WebSocket(`${protocol}//${window.location.host}/ws/chat`);
        
        // Helper function to safely resolve/reject
        const safeResolve = () => {
            if (!isResolved) {
                isResolved = true;
                resolve();
            }
        };
        
        const safeReject = (error) => {
            if (!isResolved) {
                isResolved = true;
                reject(error);
            }
        };
        
        ws.onopen = function() {
            console.log('WebSocket connected');
            // Send the message
            ws.send(JSON.stringify({ message: message }));
        };
        
        ws.onmessage = function(event) {
            try {
                const data = JSON.parse(event.data);
                console.log('WebSocket received:', data.type, data.content ? data.content.substring(0, 100) + '...' : '');
                
                if (data.type === 'final') {
                    console.log('Received final answer, length:', data.content?.length);
                    handleStreamingMessage(data, streamingContent);
                    ws.close(1000, 'Normal closure'); // Close with normal code
                    safeResolve();
                } else if (data.type === 'error') {
                    console.error('Received error:', data.content);
                    appendStreamingContent(streamingContent, `<div class="agent-error">Error: ${data.content}</div>`);
                    ws.close(1000, 'Error received');
                    safeReject(new Error(data.content));
                } else if (data.type === 'heartbeat') {
                    console.debug('Received heartbeat:', data.content);
                    // Do nothing for heartbeat - just keep connection alive
                } else {
                    // Handle intermediate steps
                    handleStreamingMessage(data, streamingContent);
                }
                
                // Scroll to bottom after each message
                messagesContainer.scrollTop = messagesContainer.scrollHeight;
                
            } catch (e) {
                console.error('Error parsing WebSocket message:', e);
                safeReject(new Error('Failed to parse WebSocket message'));
            }
        };
        
        ws.onerror = function(error) {
            console.error('WebSocket error:', error);
            safeReject(new Error('WebSocket connection error'));
        };
        
        ws.onclose = function(event) {
            console.log('WebSocket closed - code:', event.code, 'reason:', event.reason, 'wasClean:', event.wasClean);
            
            // If WebSocket closes unexpectedly without receiving 'final', reject the promise
            if (!isResolved && event.code !== 1000) {
                console.error('WebSocket closed unexpectedly - code:', event.code, 'reason:', event.reason);
                appendStreamingContent(streamingContent, `<div class="agent-error">Connection lost (code ${event.code}). Please try again.</div>`);
                safeReject(new Error(`WebSocket closed unexpectedly: ${event.code} ${event.reason}`));
            }
        };
        
        // Timeout after 45 seconds (increased from 30 to give more time)
        setTimeout(() => {
            if (!isResolved && ws.readyState !== WebSocket.CLOSED) {
                console.warn('WebSocket timeout after 45 seconds');
                ws.close(1000, 'Timeout');
                appendStreamingContent(streamingContent, `<div class="agent-error">Request timed out. Please try again.</div>`);
                safeReject(new Error('WebSocket timeout'));
            }
        }, 45000);
    });
}

async function sendChatMessageSSE(message) {
    // Create a streaming message container for the assistant response
    const streamingMessageId = 'streaming-' + Date.now();
    const messagesContainer = document.getElementById('chat-messages');
    
    const streamingDiv = document.createElement('div');
    streamingDiv.id = streamingMessageId;
    streamingDiv.className = 'chat-message assistant';
    
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    contentDiv.innerHTML = '<strong>AI Assistant:</strong><br><span class="streaming-content"></span>';
    
    streamingDiv.appendChild(contentDiv);
    messagesContainer.appendChild(streamingDiv);
    
    const streamingContent = streamingDiv.querySelector('.streaming-content');
    
    // Scroll to bottom
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
    
    try {
        const response = await fetch('/api/chat/stream', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ message: message })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        
        let buffer = '';
        let hasContent = false;
        
        while (true) {
            const { done, value } = await reader.read();
            
            if (done) break;
            
            buffer += decoder.decode(value, { stream: true });
            
            // Process complete lines
            const lines = buffer.split('\n');
            buffer = lines.pop(); // Keep incomplete line in buffer
            
            for (const line of lines) {
                if (line.trim() === '') continue;
                
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        
                        // Show content immediately as it comes in
                        if (data.type !== 'heartbeat') {
                            handleStreamingMessage(data, streamingContent);
                            hasContent = true;
                            
                            // Scroll to bottom after each update
                            messagesContainer.scrollTop = messagesContainer.scrollHeight;
                        }
                        
                    } catch (e) {
                        console.error('Error parsing SSE data:', e, 'Line:', line);
                    }
                }
            }
        }
        
        // If no content was streamed, show an error
        if (!hasContent) {
            streamingContent.innerHTML = 'No response received from AI agent.';
        }
        
    } catch (error) {
        console.error('Streaming error:', error);
        streamingContent.innerHTML = `<div class="agent-error">Error: ${error.message}</div>`;
    }
}

function handleStreamingMessage(data, contentElement) {
    const { type, content } = data;
    
    switch (type) {
        case 'thinking':
            appendStreamingContent(contentElement, `<div class='agent-thinking'>${content}</div>`);
            break;
        case 'invoking':
            appendStreamingContent(contentElement, `<div class='agent-invoking'>${content}</div>`);
            break;
        case 'responded':
            // Skip the final "responded" message if it's the final answer
            // The final answer will be sent as type 'final' instead
            break;
        case 'result':
            appendStreamingContent(contentElement, `<div class='agent-result'>${content}</div>`);
            break;
        case 'final':
            // Style the final answer distinctively with proper formatting
            const finalContent = content.replace(/\n/g, '<br>'); // Preserve line breaks
            appendStreamingContent(contentElement, `<div class='agent-final'><strong>Final Answer:</strong><br>${finalContent}</div>`);
            break;
        case 'error':
            appendStreamingContent(contentElement, `<div class='agent-error'>Error: ${content}</div>`);
            break;
        case 'heartbeat':
            // Do nothing for heartbeat
            break;
        default:
            console.log('Unknown message type:', type, content);
    }
}

function appendStreamingContent(contentElement, htmlContent) {
    contentElement.innerHTML += htmlContent + '<br>';
    
    // Scroll to bottom
    const messagesContainer = document.getElementById('chat-messages');
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

function addChatMessage(message, type) {
    const messagesContainer = document.getElementById('chat-messages');
    const messageDiv = document.createElement('div');
    messageDiv.className = `chat-message ${type}`;
    
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    
    if (type === 'user') {
        contentDiv.innerHTML = `<strong>You:</strong> ${escapeHtml(message)}`;
    } else if (type === 'assistant') {
        contentDiv.innerHTML = `<strong>AI Assistant:</strong> ${formatAssistantMessage(message)}`;
    } else if (type === 'error') {
        contentDiv.innerHTML = `<strong>Error:</strong> ${escapeHtml(message)}`;
    }
    
    messageDiv.appendChild(contentDiv);
    messagesContainer.appendChild(messageDiv);
    
    // Scroll to bottom
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

function addThinkingIndicator() {
    const messagesContainer = document.getElementById('chat-messages');
    const thinkingDiv = document.createElement('div');
    const thinkingId = 'thinking-' + Date.now();
    thinkingDiv.id = thinkingId;
    thinkingDiv.className = 'chat-message assistant';
    
    thinkingDiv.innerHTML = `
        <div class="message-content">
            <div class="thinking-indicator">
                <strong>AI Assistant:</strong> Thinking
                <div class="thinking-dots">
                    <span></span>
                    <span></span>
                    <span></span>
                </div>
            </div>
        </div>
    `;
    
    messagesContainer.appendChild(thinkingDiv);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
    
    return thinkingId;
}

function removeThinkingIndicator(thinkingId) {
    const thinkingDiv = document.getElementById(thinkingId);
    if (thinkingDiv) {
        thinkingDiv.remove();
    }
}

function formatAssistantMessage(message) {
    console.log('Formatting message:', message.substring(0, 200) + '...');
    
    // Check if the message contains agent intermediate steps (HTML divs with single quotes)
    if (message.includes("<div class='agent-thinking'>") || 
        message.includes("<div class='agent-invoking'>") || 
        message.includes("<div class='agent-responded'>") || 
        message.includes("<div class='agent-step'>") || 
        message.includes("<div class='agent-result'>") || 
        message.includes("<div class='agent-final'>")) {
        
        console.log('Message contains HTML divs - rendering as HTML');
        // Message contains intermediate steps HTML - return as-is but convert newlines
        return message.replace(/\n\n/g, '<br><br>').replace(/\n/g, '<br>');
    }
    
    console.log('Message does not contain HTML divs - escaping HTML');
    // Basic formatting for regular AI responses
    let formatted = escapeHtml(message);
    
    // Convert newlines to <br>
    formatted = formatted.replace(/\n/g, '<br>');
    
    // Format code blocks (basic)
    formatted = formatted.replace(/`([^`]+)`/g, '<code style="background: rgba(0,255,136,0.1); padding: 2px 4px; border-radius: 3px;">$1</code>');
    
    return formatted;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Logs Management
async function refreshLogs() {
    try {
        const response = await fetch('/api/logs');
        const logs = await response.json();
        
        const logOutput = document.getElementById('log-output');
        logOutput.innerHTML = '';
        
        logs.forEach(log => {
            const logEntry = document.createElement('div');
            logEntry.className = `log-entry log-level-${log.level}`;
            logEntry.innerHTML = `
                <span class="log-timestamp">[${new Date(log.timestamp).toLocaleString()}]</span>
                <span class="log-message">${log.message}</span>
            `;
            logOutput.appendChild(logEntry);
        });
        
        // Scroll to bottom
        logOutput.scrollTop = logOutput.scrollHeight;
        
    } catch (error) {
        console.error('Failed to load logs:', error);
    }
}

function clearLogs() {
    // Note: This would need a backend endpoint to actually clear logs
    document.getElementById('log-output').innerHTML = '';
    showNotification('Logs cleared (frontend only)', 'success');
}

// Modal Management
function showModal(modalId) {
    const modal = document.getElementById(modalId);
    modal.style.display = 'block';
    
    // Focus on the first input field
    setTimeout(() => {
        const firstInput = modal.querySelector('input[type="text"], input[type="password"]');
        if (firstInput) {
            firstInput.focus();
        }
    }, 100);
    
    // Add keydown event listener for Enter key and Escape key
    const handleKeyDown = (event) => {
        if (event.key === 'Enter') {
            event.preventDefault();
            // Find and click the primary save/submit button
            const saveButton = modal.querySelector('.btn:not(.secondary)');
            if (saveButton) {
                saveButton.click();
            }
        } else if (event.key === 'Escape') {
            event.preventDefault();
            closeModal(modalId);
        }
    };
    
    // Add event listener to modal
    modal.addEventListener('keydown', handleKeyDown);
    
    // Store the handler so we can remove it later
    modal._keydownHandler = handleKeyDown;
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    modal.style.display = 'none';
    
    // Remove keydown event listener
    if (modal._keydownHandler) {
        modal.removeEventListener('keydown', modal._keydownHandler);
        delete modal._keydownHandler;
    }
    
    // Clear form fields
    const inputs = modal.querySelectorAll('input[type="text"], input[type="password"]');
    inputs.forEach(input => {
        input.value = '';
    });
}

// Click outside modal to close
window.onclick = function(event) {
    const modals = document.querySelectorAll('.modal');
    modals.forEach(modal => {
        if (event.target === modal) {
            modal.style.display = 'none';
        }
    });
}

// Notification System
function showNotification(message, type = 'info') {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    
    // Style the notification
    Object.assign(notification.style, {
        position: 'fixed',
        top: '20px',
        right: '20px',
        padding: '15px 20px',
        borderRadius: '5px',
        color: '#ffffff',
        fontFamily: 'Courier New, monospace',
        fontSize: '14px',
        zIndex: '10000',
        maxWidth: '400px',
        boxShadow: '0 4px 10px rgba(0, 0, 0, 0.3)',
        animation: 'slideInRight 0.3s ease-out'
    });
    
    // Set background color based on type
    const colors = {
        success: '#00ff88',
        error: '#ff4444',
        warning: '#ffaa00',
        info: '#0088ff'
    };
    notification.style.backgroundColor = colors[type] || colors.info;
    
    // Add to document
    document.body.appendChild(notification);
    
    // Remove after 5 seconds
    setTimeout(() => {
        notification.style.animation = 'slideOutRight 0.3s ease-in';
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 300);
    }, 5000);
}

// Add CSS animations for notifications
const style = document.createElement('style');
style.textContent = `
    @keyframes slideInRight {
        from { transform: translateX(100%); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
    }
    
    @keyframes slideOutRight {
        from { transform: translateX(0); opacity: 1; }
        to { transform: translateX(100%); opacity: 0; }
    }
    
    .status-configured { color: var(--success); font-weight: bold; }
    .status-discovered { color: var(--warning); font-weight: bold; }
    .status-configuring { color: #0088ff; font-weight: bold; }
    .status-error { color: var(--error); font-weight: bold; }
    
    .error-message {
        background: rgba(255, 69, 58, 0.1);
        border: 1px solid var(--error);
        border-radius: 4px;
        padding: 8px 12px;
        margin: 4px 0;
        color: var(--error);
        font-size: 14px;
    }
    
    #error-messages {
        margin-top: 16px;
    }
    
    .seed-device {
        background-color: rgba(0, 255, 136, 0.1);
        border-left: 3px solid var(--accent);
    }
    
    .tasks-cell {
        font-size: 12px;
        max-width: 200px;
        word-wrap: break-word;
    }
    
    .ssh-active {
        background-color: rgba(255, 255, 0, 0.2) !important;
        animation: sshPulse 1.5s ease-in-out infinite;
    }
    
    @keyframes sshPulse {
        0% { background-color: rgba(255, 255, 0, 0.2); }
        50% { background-color: rgba(255, 255, 0, 0.4); }
        100% { background-color: rgba(255, 255, 0, 0.2); }
    }
    
    .ssh-active td:first-child {
        position: relative;
    }
    
    .ssh-active td:first-child::after {
        content: "● SSH";
        position: absolute;
        right: 5px;
        top: 50%;
        transform: translateY(-50%);
        color: #ffff00;
        font-size: 10px;
        font-weight: bold;
        animation: blink 1s ease-in-out infinite;
    }
    
    @keyframes blink {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.3; }
    }
    
    .agent-final {
        background: linear-gradient(135deg, rgba(0, 255, 136, 0.1), rgba(0, 255, 136, 0.05));
        border: 1px solid var(--accent);
        border-radius: 8px;
        padding: 16px;
        margin: 12px 0;
        color: #ffffff;
        font-family: 'Courier New', monospace;
        line-height: 1.6;
    }
    
    .agent-final strong {
        color: var(--accent);
        font-size: 16px;
        display: block;
        margin-bottom: 8px;
        border-bottom: 1px solid rgba(0, 255, 136, 0.3);
        padding-bottom: 4px;
    }
    
    .agent-thinking {
        color: #999;
        font-style: italic;
        padding: 4px 8px;
        margin: 2px 0;
        border-left: 2px solid #666;
        background: rgba(255, 255, 255, 0.05);
    }
    
    .agent-invoking {
        color: var(--accent);
        font-family: 'Courier New', monospace;
        padding: 4px 8px;
        margin: 4px 0;
        background: rgba(0, 255, 136, 0.1);
        border-radius: 4px;
    }
    
    .agent-result {
        color: #00ff88;
        padding: 4px 8px;
        margin: 2px 0;
        font-size: 14px;
    }
    
    .agent-error {
        color: var(--error);
        background: rgba(255, 69, 58, 0.1);
        border: 1px solid var(--error);
        border-radius: 4px;
        padding: 8px 12px;
        margin: 8px 0;
    }
`;
document.head.appendChild(style);

// Helper function to create error container
function createErrorContainer() {
    const container = document.createElement('div');
    container.id = 'error-messages';
    
    // Add a title
    const title = document.createElement('h4');
    title.textContent = 'Connection Errors:';
    title.style.color = 'var(--error)';
    title.style.marginBottom = '8px';
    
    container.appendChild(title);
    
    // Insert it after the status section in monitoring tab
    const statusSection = document.querySelector('#monitoring .status-grid');
    if (statusSection && statusSection.parentNode) {
        statusSection.parentNode.insertBefore(container, statusSection.nextSibling);
    }
    
    return container;
}