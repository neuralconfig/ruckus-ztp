// RUCKUS ZTP Agent Web Interface JavaScript

// Global state
let currentTab = 'configuration';  // Start with configuration

// Agent-specific state (initialized when agent UUID is available)
let agentConfig = {
    credentials: [],
    seedSwitches: [],
    baseConfigs: {},
    config: {}
};
let statusUpdateInterval;
let topologyUpdateInterval;
let dashboardUpdateInterval;
let eventsUpdateInterval;
let availableEdgeAgents = [];
let selectedEdgeAgentId = null;
let edgeAgentAuthToken = null;
let ztpEvents = [];
let deviceInventory = {};

// Helper function to get agent-scoped API URL
function getAgentApiUrl(endpoint) {
    const agentUuid = window.AGENT_UUID;
    if (!agentUuid) {
        throw new Error('Agent UUID not available');
    }
    return `/api/${agentUuid}${endpoint}`;
}

// Initialize the application
document.addEventListener('DOMContentLoaded', function() {
    initializeApp();
});

async function initializeApp() {
    await loadAgentConfig();
    await loadBaseConfigs();
    await checkAIConfiguration();
    setupEventListeners();
    
    // Start with configuration tab active
    switchTab('configuration');
}

function setupEventListeners() {
    // Tab navigation
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            await switchTab(e.target.dataset.tab);
        });
    });
    
    // Auto-refresh for monitoring tab
    setInterval(async () => {
        if (currentTab === 'monitoring') {
            await updateStatus();
            await updateDeviceList();
        }
    }, 5000);
}

// Tab Management
async function switchTab(tabName) {
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
    
    // Load configuration if switching to configuration tab
    if (tabName === 'configuration') {
        await loadAgentConfig();
        populateConfigForm();
        updateBaseConfigSelect();
    }
    
    // Load events if switching to events tab
    if (tabName === 'events') {
        updateEvents();
    }
    
    // Load logs if switching to logs tab
    if (tabName === 'logs') {
        refreshLogs();
    }
}

// Configuration Management
async function loadAgentConfig() {
    try {
        const response = await fetch(getAgentApiUrl('/config'));
        agentConfig.config = await response.json();
        agentConfig.credentials = agentConfig.config.credentials || [];
        agentConfig.seedSwitches = agentConfig.config.seed_switches || [];
    } catch (error) {
        console.error('Failed to load agent config:', error);
        // Initialize empty state for this agent
        agentConfig.credentials = [];
        agentConfig.seedSwitches = [];
        agentConfig.config = {};
    }
}

async function saveConfig() {
    try {
        // Validate required fields
        const preferredPassword = document.getElementById('preferred-password').value.trim();
        if (!preferredPassword) {
            showNotification('New Super Password is required for first-time switch setup', 'error');
            document.getElementById('preferred-password').focus();
            return;
        }
        
        // Always include default credentials, but avoid duplicates
        const allCredentials = [
            { username: 'super', password: 'sp-admin' }
        ];
        
        // Add user-defined credentials, avoiding duplicates
        agentConfig.credentials.forEach(cred => {
            const isDuplicate = allCredentials.some(existing => 
                existing.username === cred.username && existing.password === cred.password
            );
            if (!isDuplicate) {
                allCredentials.push(cred);
            }
        });
        
        console.log('Sending credentials to agent:', allCredentials);
        
        // Get the selected base configuration content
        const selectedBaseConfigName = document.getElementById('base-config-select').value;
        const baseConfigContent = agentConfig.baseConfigs[selectedBaseConfigName] || '';
        
        // Collect form data
        const formConfig = {
            credentials: allCredentials,
            preferred_password: document.getElementById('preferred-password').value,
            seed_switches: agentConfig.seedSwitches,
            base_config_name: selectedBaseConfigName,
            base_config_content: baseConfigContent,
            management_vlan: parseInt(document.getElementById('management-vlan').value),
            wireless_vlans: document.getElementById('wireless-vlans').value.split(',').map(v => parseInt(v.trim())),
            ip_pool: document.getElementById('ip-pool').value,
            gateway: document.getElementById('gateway').value,
            dns_server: document.getElementById('dns-server').value,
            poll_interval: parseInt(document.getElementById('poll-interval').value),
            fast_discovery: document.getElementById('fast-discovery').checked
        };
        
        console.log('Sending config with seed_switches:', formConfig.seed_switches);
        
        const response = await fetch(getAgentApiUrl('/config'), {
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
    // Basic form fields
    document.getElementById('preferred-password').value = agentConfig.config.preferred_password || 'admin123';
    document.getElementById('management-vlan').value = agentConfig.config.management_vlan || 10;
    document.getElementById('wireless-vlans').value = (agentConfig.config.wireless_vlans || [20, 30, 40]).join(',');
    document.getElementById('ip-pool').value = agentConfig.config.ip_pool || '192.168.10.0/24';
    document.getElementById('gateway').value = agentConfig.config.gateway || '192.168.10.1';
    document.getElementById('dns-server').value = agentConfig.config.dns_server || '192.168.10.2';
    document.getElementById('poll-interval').value = agentConfig.config.poll_interval || 15;
    document.getElementById('fast-discovery').checked = agentConfig.config.fast_discovery !== false;
    
    // Update agent UUID display
    document.getElementById('agent-uuid-display').value = window.AGENT_UUID;
    
    // Populate credentials (excluding the default one that's already shown)
    populateCredentialsList();
    
    // Populate seed switches
    populateSeedSwitchesList();
    
    // Update base config dropdown first
    updateBaseConfigSelect();
    
    // Set base config selection and preview
    if (agentConfig.config.base_config_name && agentConfig.baseConfigs[agentConfig.config.base_config_name]) {
        document.getElementById('base-config-select').value = agentConfig.config.base_config_name;
        updateConfigPreview();
    }
}

// Configuration Form Management
function populateCredentialsList() {
    const container = document.getElementById('credential-list');
    // Clear existing credentials (except default)
    const defaultCred = container.querySelector('.default-credential');
    container.innerHTML = '';
    if (defaultCred) {
        container.appendChild(defaultCred);
    }
    
    // Add other credentials
    if (agentConfig.credentials && agentConfig.credentials.length > 0) {
        agentConfig.credentials.forEach((cred, index) => {
            if (cred.username !== 'super' || cred.password !== 'sp-admin') {
                const credDiv = document.createElement('div');
                credDiv.className = 'credential-item';
                credDiv.innerHTML = `
                    <span class="credential-display">${cred.username} / ${cred.password}</span>
                    <button class="btn-small" onclick="removeCredential(${index})">Remove</button>
                `;
                container.appendChild(credDiv);
            }
        });
    }
}

function populateSeedSwitchesList() {
    const container = document.getElementById('seed-switch-list');
    container.innerHTML = '';
    
    if (agentConfig.seedSwitches && agentConfig.seedSwitches.length > 0) {
        agentConfig.seedSwitches.forEach((switchConfig, index) => {
            const switchDiv = document.createElement('div');
            switchDiv.className = 'seed-switch-item';
            switchDiv.innerHTML = `
                <span class="switch-display">${switchConfig.ip}</span>
                <button class="btn-small" onclick="removeSeedSwitch(${index})">Remove</button>
            `;
            container.appendChild(switchDiv);
        });
    }
}

function addSeedSwitch() {
    const ipInput = document.getElementById('new-seed-switch-ip');
    const ip = ipInput.value.trim();
    
    if (!ip) {
        showNotification('Please enter an IP address', 'error');
        return;
    }
    
    // Simple IP validation
    const ipRegex = /^(\d{1,3}\.){3}\d{1,3}$/;
    if (!ipRegex.test(ip)) {
        showNotification('Please enter a valid IP address', 'error');
        return;
    }
    
    // Check if already exists
    if (agentConfig.seedSwitches.some(sw => sw.ip === ip)) {
        showNotification('IP address already exists', 'warning');
        return;
    }
    
    // Add to agent's seed switches (all credentials will be tried automatically)
    agentConfig.seedSwitches.push({ ip: ip });
    console.log('Added seed switch, current list:', agentConfig.seedSwitches);
    populateSeedSwitchesList();
    ipInput.value = '';
    showNotification('Seed switch added successfully', 'success');
}

function handleSeedSwitchKeyPress(event) {
    if (event.key === 'Enter') {
        addSeedSwitch();
    }
}

function handleCredentialKeyPress(event) {
    if (event.key === 'Enter') {
        addCredential();
    }
}

function removeSeedSwitch(index) {
    agentConfig.seedSwitches.splice(index, 1);
    populateSeedSwitchesList();
    showNotification('Seed switch removed', 'success');
}

function removeCredential(index) {
    credentials.splice(index, 1);
    populateCredentialsList();
    showNotification('Credential removed', 'success');
}

// Credential Management
function addCredential() {
    const usernameInput = document.getElementById('new-credential-username');
    const passwordInput = document.getElementById('new-credential-password');
    const username = usernameInput.value.trim();
    const password = passwordInput.value.trim();
    
    if (!username || !password) {
        showNotification('Please enter both username and password', 'error');
        return;
    }
    
    // Check for duplicates
    if (agentConfig.credentials.some(cred => cred.username === username && cred.password === password)) {
        showNotification('This credential already exists', 'warning');
        return;
    }
    
    // Also check against default credential
    if (username === 'super' && password === 'sp-admin') {
        showNotification('Default credential already exists', 'warning');
        return;
    }
    
    agentConfig.credentials.push({ username, password });
    populateCredentialsList();
    
    // Clear inputs
    usernameInput.value = '';
    passwordInput.value = '';
    
    showNotification('Credential added successfully', 'success');
}

function removeCredential(index) {
    agentConfig.credentials.splice(index, 1);
    populateCredentialsList();
    showNotification('Credential removed', 'success');
}

// Use populateCredentialsList() consistently instead of updateCredentialsList()

// Seed Switch Management - modal functions removed, using inline form only

function removeSeedSwitch(index) {
    seedSwitches.splice(index, 1);
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
        agentConfig.baseConfigs = await response.json();
    } catch (error) {
        console.error('Failed to load base configs:', error);
        agentConfig.baseConfigs = {};
    }
}

function updateBaseConfigSelect() {
    const select = document.getElementById('base-config-select');
    select.innerHTML = '';
    
    // Add existing configurations
    Object.keys(agentConfig.baseConfigs).forEach(name => {
        const option = document.createElement('option');
        option.value = name;
        option.textContent = name;
        select.appendChild(option);
    });
    
    // Add separator
    const separator = document.createElement('option');
    separator.disabled = true;
    separator.textContent = '────────────────';
    select.appendChild(separator);
    
    // Add upload option
    const uploadOption = document.createElement('option');
    uploadOption.value = '__upload__';
    uploadOption.textContent = '📤 Upload Custom Configuration...';
    select.appendChild(uploadOption);
    
    // Set selected value from config
    if (agentConfig.config.base_config_name && agentConfig.baseConfigs[agentConfig.config.base_config_name]) {
        select.value = agentConfig.config.base_config_name;
    }
}

function updateConfigPreview() {
    const selectedConfig = document.getElementById('base-config-select').value;
    const preview = document.getElementById('config-preview');
    
    if (selectedConfig === '__upload__') {
        // Show upload modal
        showModal('config-upload-modal');
        // Reset to previous selection or first option
        const select = document.getElementById('base-config-select');
        const firstConfig = Object.keys(agentConfig.baseConfigs)[0];
        if (firstConfig) {
            select.value = firstConfig;
            preview.value = agentConfig.baseConfigs[firstConfig];
        }
    } else if (selectedConfig && agentConfig.baseConfigs[selectedConfig]) {
        preview.value = agentConfig.baseConfigs[selectedConfig];
    } else {
        preview.value = '';
    }
}

function handleUploadFileSelect(event) {
    const file = event.target.files[0];
    if (file) {
        document.getElementById('upload-config-filename').value = file.name;
        // Auto-fill name if empty
        const nameInput = document.getElementById('upload-config-name');
        if (!nameInput.value) {
            nameInput.value = file.name.replace('.txt', '');
        }
    }
}

async function uploadBaseConfigFromModal() {
    const nameInput = document.getElementById('upload-config-name');
    const fileInput = document.getElementById('upload-config-file');
    
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
            
            // Update base configs in agentConfig
            agentConfig.baseConfigs[name] = await file.text();
            
            // Update the dropdown
            updateBaseConfigSelect();
            
            // Select the newly uploaded config
            document.getElementById('base-config-select').value = name;
            updateConfigPreview();
            
            // Clear form and close modal
            nameInput.value = '';
            fileInput.value = '';
            document.getElementById('upload-config-filename').value = '';
            closeModal('config-upload-modal');
            
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
        // Validate required fields before starting
        const preferredPassword = document.getElementById('preferred-password').value.trim();
        if (!preferredPassword) {
            showNotification('Cannot start ZTP: New Super Password is required', 'error');
            switchTab('configuration');  // Switch to config tab
            document.getElementById('preferred-password').focus();
            return;
        }
        
        // Save config first
        await saveConfig();
        
        // Set UI to starting state immediately
        const statusElement = document.getElementById('ztp-status');
        const toggleButton = document.getElementById('ztp-toggle');
        if (statusElement && toggleButton) {
            statusElement.textContent = 'Starting...';
            statusElement.className = 'status-indicator starting';
            toggleButton.textContent = 'Starting...';
            toggleButton.disabled = true;
        }
        
        const response = await fetch(getAgentApiUrl('/ztp/start'), {
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
        const response = await fetch(getAgentApiUrl('/ztp/stop'), {
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
    }, 1000);  // Faster UI updates - every 1 second
    
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
        const response = await fetch(getAgentApiUrl('/status'));
        const status = await response.json();
        
        // Update status indicator (check if elements exist)
        const statusElement = document.getElementById('ztp-status');
        const statusDisplay = document.getElementById('ztp-status-display');
        const toggleButton = document.getElementById('ztp-toggle');
        
        if (statusElement) {
            if (status.running) {
                statusElement.textContent = 'Running';
                statusElement.className = 'status-indicator running';
            } else if (status.starting) {
                statusElement.textContent = 'Starting...';
                statusElement.className = 'status-indicator starting';
            } else {
                statusElement.textContent = 'Stopped';
                statusElement.className = 'status-indicator stopped';
            }
        }
        
        // Update dashboard status display
        if (statusDisplay) {
            statusDisplay.textContent = status.running ? 'Running' : 'Stopped';
        }
        
        // Update start/stop button visibility
        const startBtn = document.getElementById('start-ztp-btn');
        const stopBtn = document.getElementById('stop-ztp-btn');
        
        if (startBtn && stopBtn) {
            if (status.running) {
                startBtn.style.display = 'none';
                stopBtn.style.display = 'block';
            } else {
                startBtn.style.display = 'block';
                stopBtn.style.display = 'none';
            }
        }
        
        if (toggleButton) {
            if (status.running) {
                toggleButton.textContent = 'Stop';
                toggleButton.disabled = false;
            } else if (status.starting) {
                toggleButton.textContent = 'Starting...';
                toggleButton.disabled = true;
            } else {
                toggleButton.textContent = 'Start';
                toggleButton.disabled = false;
            }
        }
        
        // Update counters (check if elements exist)
        const totalSwitches = document.getElementById('total-switches');
        const totalAps = document.getElementById('total-aps');
        const configuredDevices = document.getElementById('configured-devices');
        
        if (totalSwitches) totalSwitches.textContent = status.switches_discovered || 0;
        if (totalAps) totalAps.textContent = status.aps_discovered || 0;
        if (configuredDevices) configuredDevices.textContent = (status.switches_configured || 0) + (status.aps_configured || 0);
        
    } catch (error) {
        console.error('Failed to update status:', error);
    }
}

async function updateDeviceList() {
    try {
        const response = await fetch(getAgentApiUrl('/devices'));
        const devices = await response.json();
        
        const tbody = document.querySelector('#device-table tbody');
        
        if (tbody) {
            tbody.innerHTML = '';
        }
        
        devices.forEach(device => {
            const row = document.createElement('tr');
            
            // Format IP with seed indicator
            const ipDisplay = device.is_seed ? `${device.ip} (SEED)` : device.ip;
            
            // Format MAC address
            const macDisplay = device.mac || 'Unknown';
            
            // Format device type with seed indicator - properly capitalize AP
            let deviceType = device.device_type === 'ap' ? 'AP' : device.device_type.charAt(0).toUpperCase() + device.device_type.slice(1);
            const typeDisplay = deviceType + (device.is_seed ? ' (seed)' : '');
            
            // Create configuration progress indicator
            function createProgressIndicator(device) {
                if (device.device_type === 'ap') {
                    // APs have only 1 configuration phase: port configuration
                    const steps = [
                        { name: 'port_config', completed: device.configured === true }
                    ];
                    
                    return steps.map(step => 
                        step.completed ? '<span style="color: #00ff88;">●</span>' : '<span style="color: #666666;">●</span>'
                    ).join(' ');
                } else {
                    // Switches have 2 configuration phases
                    const steps = [
                        { name: 'base_config', completed: device.base_config_applied === true },
                        { name: 'device_config', completed: device.configured === true }
                    ];
                    
                    return steps.map(step => 
                        step.completed ? '<span style="color: #00ff88;">●</span>' : '<span style="color: #666666;">●</span>'
                    ).join(' ');
                }
            }
            
            const progressDisplay = createProgressIndicator(device);
            
            // Create row first, then set innerHTML for most cells and use DOM manipulation for progress
            row.innerHTML = `
                <td><strong>${ipDisplay}</strong></td>
                <td>${macDisplay}</td>
                <td>${typeDisplay}</td>
                <td>${device.model || 'Unknown'}</td>
                <td>${device.serial || 'Unknown'}</td>
                <td class="progress-cell"></td>
            `;
            
            // Set progress display with HTML
            const progressCell = row.querySelector('.progress-cell');
            progressCell.innerHTML = progressDisplay;
            
            // Add special styling for seed switches
            if (device.is_seed) {
                row.classList.add('seed-device');
            }
            
            // Add SSH activity highlighting
            if (device.ssh_active) {
                row.classList.add('ssh-active');
            }
            
            if (tbody) {
                tbody.appendChild(row);
            }
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
    fetch(getAgentApiUrl('/devices'))
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
    
    // Add labels (hostname on top, IP/MAC below based on device type)
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
        
    const secondLabel = svg.append('g')
        .selectAll('text')
        .data(nodes)
        .enter().append('text')
        .text(d => {
            if (d.type === 'ap') {
                // For APs, show MAC address instead of IP
                return d.mac || 'Unknown MAC';
            } else {
                // For switches, only show IP if we have a real hostname (not just IP or literal "hostname")
                const hostname = d.hostname;
                if (hostname && hostname !== 'hostname' && hostname !== 'unknown' && hostname.trim() !== '' && hostname !== d.id) {
                    return d.id;
                }
                return ''; // Don't show IP if hostname is missing or same as IP
            }
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
            
        secondLabel
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
async function saveOpenRouterKey() {
    const apiKey = document.getElementById('openrouter-api-key').value.trim();
    
    if (!apiKey) {
        showNotification('Please enter an OpenRouter API key', 'error');
        return;
    }
    
    try {
        const response = await fetch(`/api/${window.AGENT_UUID}/openrouter-key`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ api_key: apiKey })
        });
        
        if (response.ok) {
            showNotification('OpenRouter API key saved successfully', 'success');
            updateAIStatus(true);
            enableChatInput();
        } else {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Failed to save API key');
        }
    } catch (error) {
        console.error('Error saving OpenRouter API key:', error);
        showNotification(`Error saving API key: ${error.message}`, 'error');
    }
}

function updateAIStatus(online) {
    const indicator = document.getElementById('ai-status-indicator');
    const text = document.getElementById('ai-status-text');
    
    if (online) {
        indicator.className = 'status-indicator online';
        indicator.textContent = 'Online';
        text.textContent = 'AI assistant ready';
    } else {
        indicator.className = 'status-indicator offline';
        indicator.textContent = 'Offline';
        text.textContent = 'Configure API key to enable AI assistant';
    }
}

function enableChatInput() {
    const chatInput = document.getElementById('chat-input');
    const sendBtn = document.getElementById('chat-send-btn');
    
    chatInput.disabled = false;
    sendBtn.disabled = false;
    chatInput.placeholder = 'Ask me anything about your network...';
}

function disableChatInput() {
    const chatInput = document.getElementById('chat-input');
    const sendBtn = document.getElementById('chat-send-btn');
    
    chatInput.disabled = true;
    sendBtn.disabled = true;
    chatInput.placeholder = 'Configure OpenRouter API key to enable chat...';
}

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
        const ws = new WebSocket(`${protocol}//${window.location.host}/ws/${window.AGENT_UUID}/chat`);
        
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
        const response = await fetch(`/api/${window.AGENT_UUID}/chat/stream`, {
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

// Edge Agent Functions for Configuration
async function refreshEdgeAgents() {
    try {
        console.log('Refreshing edge agents for dropdown...');
        const response = await fetch('/api/edge-agents');
        if (response.ok) {
            availableEdgeAgents = await response.json();
            console.log('Available edge agents:', availableEdgeAgents);
            updateEdgeAgentSelect();
            updateEdgeAgentStatus();
        } else {
            console.error('Failed to fetch edge agents:', response.status);
        }
    } catch (error) {
        console.error('Failed to fetch edge agents:', error);
    }
}

function updateEdgeAgentSelect() {
    const select = document.getElementById('edge-agent-select');
    if (!select) {
        console.error('edge-agent-select element not found in DOM');
        return;
    }
    console.log('Updating edge agent select dropdown with', availableEdgeAgents.length, 'agents');
    select.innerHTML = '<option value="">Select an edge agent...</option>';
    
    availableEdgeAgents.forEach(agent => {
        const option = document.createElement('option');
        option.value = agent.agent_id;
        option.textContent = `${agent.hostname} (${agent.agent_id}) - ${agent.network_subnet}`;
        if (agent.agent_id === selectedEdgeAgentId) {
            option.selected = true;
        }
        select.appendChild(option);
        console.log('Added agent to dropdown:', agent.agent_id);
    });
    
    if (availableEdgeAgents.length === 0) {
        select.innerHTML = '<option value="">No edge agents connected</option>';
        console.log('No edge agents available for dropdown');
    }
}

function updateEdgeAgentStatus() {
    const statusDiv = document.getElementById('edge-agent-status');
    if (!statusDiv) {
        console.error('edge-agent-status element not found in DOM');
        return;
    }
    
    const selectedAgent = availableEdgeAgents.find(p => p.agent_id === selectedEdgeAgentId);
    
    if (!selectedAgent) {
        statusDiv.className = 'agent-status disconnected';
        statusDiv.innerHTML = 'No edge agent selected';
        return;
    }
    
    const statusClass = selectedAgent.status === 'online' ? 'connected' : 'disconnected';
    statusDiv.className = `agent-status ${statusClass}`;
    
    const lastSeen = new Date(selectedAgent.last_seen).toLocaleString();
    statusDiv.innerHTML = `
        <div>Status: <strong>${selectedAgent.status}</strong></div>
        <div class="agent-info">
            <div>Host: ${selectedAgent.hostname}</div>
            <div>Network: ${selectedAgent.network_subnet}</div>
            <div>Last seen: ${lastSeen}</div>
        </div>
    `;
}

function toggleAgentSettings() {
    // Edge agents are now always enabled - this function is kept for compatibility
    // Automatically refresh agents when called
    refreshEdgeAgents();
}



// Dashboard Functions
function startDashboardUpdates() {
    // Update dashboard every 10 seconds
    dashboardUpdateInterval = setInterval(async () => {
        if (currentTab === 'monitoring') {
            await updateDashboard();
        }
    }, 10000);
    
    // Update events every 5 seconds  
    eventsUpdateInterval = setInterval(async () => {
        if (currentTab === 'events') {
            await updateEvents();
        }
    }, 5000);
    
    // Initial load
    updateDashboard();
}

async function updateDashboard() {
    try {
        // Get ZTP status summary
        const ztpResponse = await fetch('/api/ztp/status');
        if (!ztpResponse.ok) {
            console.error('Failed to fetch ZTP status:', ztpResponse.status);
            return;
        }
        const ztpStatus = await ztpResponse.json();
        console.log('ZTP Status:', ztpStatus);
        
        // Update dashboard stats
        const totalSwitches = document.getElementById('total-switches');
        const totalAps = document.getElementById('total-aps');
        const configuredDevices = document.getElementById('configured-devices');
        
        if (totalSwitches) totalSwitches.textContent = ztpStatus.switches_discovered || 0;
        if (totalAps) totalAps.textContent = ztpStatus.aps_discovered || 0;
        if (configuredDevices) configuredDevices.textContent = ztpStatus.total_devices_configured || 0;
        
        // Get recent events
        const eventsResponse = await fetch('/api/ztp/events?limit=5');
        const recentEvents = await eventsResponse.json();
        updateRecentEvents(recentEvents);
        
        // Get device inventory
        const inventoryResponse = await fetch('/api/ztp/inventory');
        const inventory = await inventoryResponse.json();
        updateDashboardDeviceTable(inventory);
        
    } catch (error) {
        console.error('Error updating dashboard:', error);
    }
}

function updateRecentEvents(events) {
    const container = document.getElementById('recent-events');
    if (!events || events.length === 0) {
        container.innerHTML = '<div class="no-events">No recent events</div>';
        return;
    }
    
    container.innerHTML = events.map(event => {
        const time = new Date(event.timestamp).toLocaleTimeString();
        return `
            <div class="event-item ${event.event_type}">
                <span class="event-type">${event.event_type}</span>
                <span class="event-timestamp">${time}</span>
                <div class="event-details">
                    ${formatEventData(event.data)}
                </div>
            </div>
        `;
    }).join('');
}

function formatEventData(data) {
    if (data.mac_address) {
        return `Device: ${data.ip_address || 'Unknown IP'} (${data.device_type || 'Unknown'})`;
    }
    if (data.message) {
        return data.message;
    }
    return JSON.stringify(data);
}

function updateDashboardDeviceTable(inventory) {
    const tbody = document.querySelector('#dashboard-device-table tbody');
    if (!inventory || Object.keys(inventory).length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="no-data">No devices discovered</td></tr>';
        return;
    }
    
    tbody.innerHTML = Object.entries(inventory).map(([mac, device]) => {
        const lastSeen = device.last_seen ? new Date(device.last_seen).toLocaleString() : 'Unknown';
        const statusClass = device.status === 'configured' ? 'success' : device.status === 'discovered' ? 'warning' : 'muted';
        
        return `
            <tr>
                <td>${device.ip_address || 'Unknown'}</td>
                <td><code>${mac}</code></td>
                <td>${device.device_type || 'Unknown'}</td>
                <td>${device.model || 'Unknown'}</td>
                <td><span class="status ${statusClass}">${device.status || 'Unknown'}</span></td>
                <td>${device.agent_hostname || 'Unknown'}</td>
                <td>${lastSeen}</td>
            </tr>
        `;
    }).join('');
}

// Edge Agents Functions
async function refreshAgents() {
    try {
        console.log('Fetching edge agents...');
        const response = await fetch('/api/edge-agents');
        const agents = await response.json();
        console.log('Received edge agents:', agents.length, 'agents');
        availableAgents = agents;
        
        // Always update the display when we have new agent data
        // The updateAgentsDisplay function will handle cases where the tab isn't active
        updateAgentsDisplay(agents);
        
    } catch (error) {
        console.error('Error fetching edge agents:', error);
    }
}

function updateAgentsDisplay(agents) {
    const container = document.getElementById('agents-grid');
    
    // Only update if the container exists (agents tab is in DOM)
    if (!container) {
        console.log('Agents container not found - tab not active');
        return;
    }
    
    console.log('Updating agents display with', agents ? agents.length : 0, 'agents');
    
    if (!agents || agents.length === 0) {
        container.innerHTML = '<div class="no-agents">No edge agents connected</div>';
        return;
    }
    
    container.innerHTML = agents.map(agent => {
        const statusClass = agent.status === 'online' ? 'online' : 'offline';
        const ztpRunning = agent.ztp_status?.running ? 'Running' : 'Stopped';
        const ztpStatusClass = agent.ztp_status?.running ? 'ztp-status-running' : 'ztp-status-stopped';
        const connectedAt = new Date(agent.connected_at).toLocaleString();
        
        return `
            <div class="agent-card ${statusClass}">
                <div class="agent-header">
                    <div class="agent-id">${agent.agent_id}</div>
                    <div class="agent-status ${statusClass}">${agent.status}</div>
                </div>
                
                <div class="agent-info">
                    <div class="agent-info-row">
                        <span class="agent-info-label">Hostname:</span>
                        <span class="agent-info-value">${agent.hostname}</span>
                    </div>
                    <div class="agent-info-row">
                        <span class="agent-info-label">Network:</span>
                        <span class="agent-info-value">${agent.network_subnet}</span>
                    </div>
                    <div class="agent-info-row">
                        <span class="agent-info-label">Version:</span>
                        <span class="agent-info-value">${agent.version}</span>
                    </div>
                    <div class="agent-info-row">
                        <span class="agent-info-label">Connected:</span>
                        <span class="agent-info-value">${connectedAt}</span>
                    </div>
                </div>
                
                <div class="agent-ztp-status">
                    <div class="agent-info-row">
                        <span class="agent-info-label">ZTP Status:</span>
                        <span class="agent-info-value ${ztpStatusClass}">${ztpRunning}</span>
                    </div>
                    <div class="agent-info-row">
                        <span class="agent-info-label">Devices:</span>
                        <span class="agent-info-value">${agent.ztp_status?.devices_discovered || 0}</span>
                    </div>
                    <div class="agent-info-row">
                        <span class="agent-info-label">Configured:</span>
                        <span class="agent-info-value">${(agent.ztp_status?.switches_configured || 0) + (agent.ztp_status?.aps_configured || 0)}</span>
                    </div>
                </div>
                
                <div class="agent-actions">
                    <button class="btn btn-primary" onclick="openAgentConfig('${agent.agent_id}')">Configure</button>
                    <button class="btn btn-secondary" onclick="viewAgentLogs('${agent.agent_id}')">Logs</button>
                </div>
            </div>
        `;
    }).join('');
}

// Events Functions
async function updateEvents() {
    try {
        const limit = 50;
        const filter = document.getElementById('event-filter')?.value || 'all';
        const url = filter === 'all' ? `/api/ztp/events?limit=${limit}` : `/api/ztp/events?limit=${limit}&type=${filter}`;
        
        const response = await fetch(url);
        const events = await response.json();
        ztpEvents = events;
        
        displayEvents(events);
    } catch (error) {
        console.error('Error fetching events:', error);
    }
}

function displayEvents(events) {
    const container = document.getElementById('events-list');
    
    if (!events || events.length === 0) {
        container.innerHTML = '<div class="no-events">No events found</div>';
        return;
    }
    
    container.innerHTML = events.map(event => {
        const timestamp = new Date(event.timestamp).toLocaleString();
        
        return `
            <div class="event-item-detailed ${event.event_type}">
                <div class="event-header">
                    <div>
                        <span class="event-type">${event.event_type}</span>
                        <span class="agent-id">Agent: ${event.agent_id}</span>
                    </div>
                    <span class="event-timestamp">${timestamp}</span>
                </div>
                <div class="event-data">
                    ${JSON.stringify(event.data, null, 2)}
                </div>
            </div>
        `;
    }).join('');
}

function refreshEvents() {
    updateEvents();
}

function clearEvents() {
    // This would need a backend endpoint to clear events
    console.log('Clear events - not implemented');
}

// Update existing functions to use edge agents instead of proxies
function toggleAgentSettings() {
    const enabled = document.getElementById('edge-agent-enabled').checked;
    const settings = document.getElementById('agent-settings');
    settings.style.display = enabled ? 'block' : 'none';
    
    if (enabled) {
        refreshAgents();
    }
}

// Per-Agent Configuration Functions
function openAgentConfig(agentId) {
    const agent = availableAgents.find(a => a.agent_id === agentId);
    if (!agent) {
        showNotification('Agent not found', 'error');
        return;
    }
    
    // Populate agent configuration modal
    document.getElementById('agent-config-title').textContent = `Configure Agent: ${agent.agent_id}`;
    document.getElementById('agent-config-hostname').textContent = agent.hostname;
    document.getElementById('agent-config-network').textContent = agent.network_subnet;
    document.getElementById('agent-config-status').textContent = agent.status;
    
    // Set current agent ID for configuration
    document.getElementById('agent-config-modal').dataset.agentId = agentId;
    
    // Load current configuration for this agent (if any)
    loadAgentConfiguration(agentId);
    
    showModal('agent-config-modal');
}

function viewAgentLogs(agentId) {
    const agent = availableAgents.find(a => a.agent_id === agentId);
    if (!agent) {
        showNotification('Agent not found', 'error');
        return;
    }
    
    // Populate agent logs modal
    document.getElementById('agent-logs-title').textContent = `Logs: ${agent.agent_id} (${agent.hostname})`;
    document.getElementById('agent-logs-output').innerHTML = '<div class="loading">Loading agent logs...</div>';
    
    // Store agent ID for refresh functionality
    document.getElementById('agent-logs-modal').dataset.agentId = agentId;
    
    showModal('agent-logs-modal');
    
    // Load logs for this specific agent
    loadAgentLogs(agentId);
}

async function loadAgentConfiguration(agentId) {
    // For now, use the global configuration as a starting point
    // In the future, this could load agent-specific configuration from the backend
    try {
        const response = await fetch('/api/config');
        const config = await response.json();
        
        // Populate the agent configuration form with current global settings
        document.getElementById('agent-preferred-password').value = config.preferred_password || '';
        document.getElementById('agent-management-vlan').value = config.management_vlan || 10;
        document.getElementById('agent-wireless-vlans').value = (config.wireless_vlans || [20, 30, 40]).join(',');
        document.getElementById('agent-ip-pool').value = config.ip_pool || '192.168.10.0/24';
        document.getElementById('agent-gateway').value = config.gateway || '192.168.10.1';
        document.getElementById('agent-dns-server').value = config.dns_server || '192.168.10.2';
        document.getElementById('agent-poll-interval').value = config.poll_interval || 300;
        
        // Populate credentials for this agent
        updateAgentCredentials(config.credentials || []);
        
        // Populate seed switches for this agent
        updateAgentSeedSwitches(config.seed_switches || []);
        
        // Populate base configuration for this agent
        updateAgentBaseConfigSelect();
        if (config.base_config_name) {
            document.getElementById('agent-base-config-select').value = config.base_config_name;
            updateAgentConfigPreview();
        }
        
    } catch (error) {
        console.error('Failed to load agent configuration:', error);
        showNotification('Failed to load agent configuration', 'error');
    }
}

function updateAgentCredentials(credentials) {
    const container = document.querySelector('.agent-credential-list');
    
    // Clear existing credentials except default
    const existingCredentials = container.querySelectorAll('.credential-item:not(.default-credential)');
    existingCredentials.forEach(item => item.remove());
    
    // Add additional credentials
    credentials.forEach((cred, index) => {
        // Skip default credential if it exists in the array
        if (cred.username === 'super' && cred.password === 'sp-admin') {
            return;
        }
        
        const credDiv = document.createElement('div');
        credDiv.className = 'credential-item';
        credDiv.innerHTML = `
            <span class="credential-display">${cred.username} / ${cred.password}</span>
            <button class="btn-small" onclick="removeAgentCredential(this)">Remove</button>
        `;
        container.appendChild(credDiv);
    });
}

function addAgentCredential() {
    showModal('agent-credential-modal');
}

function saveAgentCredential() {
    const username = document.getElementById('agent-modal-username').value;
    const password = document.getElementById('agent-modal-password').value;
    
    if (!username || !password) {
        showNotification('Please enter both username and password', 'error');
        return;
    }
    
    // Add credential to the list
    const container = document.querySelector('.agent-credential-list');
    const credDiv = document.createElement('div');
    credDiv.className = 'credential-item';
    credDiv.innerHTML = `
        <span class="credential-display">${username} / ${password}</span>
        <button class="btn-small" onclick="removeAgentCredential(this)">Remove</button>
    `;
    container.appendChild(credDiv);
    
    closeModal('agent-credential-modal');
    showNotification('Credential added successfully', 'success');
}

function removeAgentCredential(button) {
    button.parentElement.remove();
    showNotification('Credential removed', 'success');
}

function updateAgentSeedSwitches(seedSwitches) {
    const container = document.querySelector('#agent-seed-switches .agent-seed-switch-list');
    container.innerHTML = '';
    
    seedSwitches.forEach((switchConfig, index) => {
        const switchDiv = document.createElement('div');
        switchDiv.className = 'seed-switch-item';
        switchDiv.innerHTML = `
            <span class="credential-display">${switchConfig.ip}</span>
            <button class="btn-small" onclick="removeAgentSeedSwitch(${index})">Remove</button>
        `;
        container.appendChild(switchDiv);
    });
}

function addAgentSeedSwitch() {
    const ipInput = document.getElementById('agent-seed-switch-ip');
    const ip = ipInput.value.trim();
    
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
    
    // Get current switches and add new one
    const container = document.querySelector('#agent-seed-switches .agent-seed-switch-list');
    const switchDiv = document.createElement('div');
    switchDiv.className = 'seed-switch-item';
    switchDiv.innerHTML = `
        <span class="credential-display">${ip}</span>
        <button class="btn-small" onclick="this.parentElement.remove()">Remove</button>
    `;
    container.appendChild(switchDiv);
    
    // Clear input
    ipInput.value = '';
    showNotification('Seed switch added', 'success');
}

function updateAgentBaseConfigSelect() {
    const select = document.getElementById('agent-base-config-select');
    if (!select) return;
    
    select.innerHTML = '';
    
    Object.keys(baseConfigs).forEach(name => {
        const option = document.createElement('option');
        option.value = name;
        option.textContent = name;
        select.appendChild(option);
    });
    
    // Auto-select the first option if available
    if (Object.keys(baseConfigs).length > 0) {
        select.selectedIndex = 0;
        updateAgentConfigPreview();
    }
}

function updateAgentConfigPreview() {
    const selectedConfig = document.getElementById('agent-base-config-select').value;
    const preview = document.getElementById('agent-config-preview');
    
    if (selectedConfig && baseConfigs[selectedConfig]) {
        preview.value = baseConfigs[selectedConfig];
    } else {
        preview.value = '';
    }
}

async function uploadAgentBaseConfig() {
    const nameInput = document.getElementById('agent-config-name');
    const fileInput = document.getElementById('agent-config-file');
    
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
            // Reload base configs to include the new one
            await loadBaseConfigs();
            updateAgentBaseConfigSelect();
            document.getElementById('agent-base-config-select').value = name;
            updateAgentConfigPreview();
            
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

// Handle file selection for agent config upload
document.addEventListener('DOMContentLoaded', function() {
    const fileInput = document.getElementById('agent-config-file');
    if (fileInput) {
        fileInput.addEventListener('change', function(event) {
            const file = event.target.files[0];
            if (file) {
                document.getElementById('agent-config-name').value = file.name.replace('.txt', '');
            }
        });
    }
});

async function checkAIConfiguration() {
    try {
        const response = await fetch(`/api/${window.AGENT_UUID}/config`);
        if (response.ok) {
            const config = await response.json();
            const apiKey = config.openrouter_api_key;
            
            if (apiKey) {
                // Mask the API key for display
                const maskedKey = apiKey.substring(0, 8) + '...' + apiKey.substring(apiKey.length - 4);
                document.getElementById('openrouter-api-key').value = maskedKey;
                updateAIStatus(true);
                enableChatInput();
            } else {
                updateAIStatus(false);
                disableChatInput();
            }
        }
    } catch (error) {
        console.log('Could not load AI configuration:', error);
        updateAIStatus(false);
        disableChatInput();
    }
}

async function saveAgentConfiguration() {
    const modal = document.getElementById('agent-config-modal');
    const agentId = modal.dataset.agentId;
    
    if (!agentId) {
        showNotification('No agent selected', 'error');
        return;
    }
    
    try {
        // Collect credentials
        const credentials = [{ username: 'super', password: 'sp-admin' }]; // Always include default
        const credentialElements = document.querySelectorAll('.agent-credential-list .credential-item:not(.default-credential) .credential-display');
        credentialElements.forEach(element => {
            const credText = element.textContent.trim();
            const [username, password] = credText.split(' / ');
            if (username && password) {
                credentials.push({ username, password });
            }
        });
        
        // Collect seed switches
        const seedSwitches = [];
        const seedElements = document.querySelectorAll('#agent-seed-switches .seed-switch-item .credential-display');
        seedElements.forEach(element => {
            const ip = element.textContent.trim();
            if (ip) {
                seedSwitches.push({ ip });
            }
        });
        
        // Build configuration for this agent
        const agentConfig = {
            agent_id: agentId,
            credentials: credentials,
            preferred_password: document.getElementById('agent-preferred-password').value,
            seed_switches: seedSwitches,
            base_config_name: document.getElementById('agent-base-config-select').value,
            management_vlan: parseInt(document.getElementById('agent-management-vlan').value),
            wireless_vlans: document.getElementById('agent-wireless-vlans').value.split(',').map(v => parseInt(v.trim())),
            ip_pool: document.getElementById('agent-ip-pool').value,
            gateway: document.getElementById('agent-gateway').value,
            dns_server: document.getElementById('agent-dns-server').value,
            poll_interval: parseInt(document.getElementById('agent-poll-interval').value)
        };
        
        // Send configuration to the specific agent
        const response = await fetch(`/api/edge-agents/${agentId}/config`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(agentConfig)
        });
        
        if (!response.ok) {
            throw new Error('Failed to send configuration to agent');
        }
        
        showNotification(`Configuration sent to agent ${agentId}`, 'success');
        closeModal('agent-config-modal');
        
    } catch (error) {
        console.error('Failed to save agent configuration:', error);
        showNotification('Failed to save agent configuration', 'error');
    }
}

async function startAgentZTP() {
    const modal = document.getElementById('agent-config-modal');
    const agentId = modal.dataset.agentId;
    
    if (!agentId) {
        showNotification('No agent selected', 'error');
        return;
    }
    
    try {
        // First save the configuration
        await saveAgentConfiguration();
        
        // Then start ZTP on this specific agent
        const response = await fetch(`/api/edge-agents/${agentId}/start-ztp`, {
            method: 'POST'
        });
        
        if (response.ok) {
            showNotification(`ZTP started on agent ${agentId}`, 'success');
            closeModal('agent-config-modal');
        } else {
            throw new Error('Failed to start ZTP on agent');
        }
        
    } catch (error) {
        console.error('Failed to start agent ZTP:', error);
        showNotification('Failed to start ZTP on agent', 'error');
    }
}

async function loadAgentLogs(agentId) {
    try {
        // Load logs specific to this agent
        const response = await fetch(`/api/edge-agents/${agentId}/logs`);
        const logs = await response.json();
        
        const logOutput = document.getElementById('agent-logs-output');
        logOutput.innerHTML = '';
        
        if (!logs || logs.length === 0) {
            logOutput.innerHTML = '<div class="no-logs">No logs available for this agent</div>';
            return;
        }
        
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
        console.error('Failed to load agent logs:', error);
        const logOutput = document.getElementById('agent-logs-output');
        logOutput.innerHTML = '<div class="error">Failed to load agent logs</div>';
    }
}

// Dashboard Functions
function startDashboardUpdates() {
    if (dashboardUpdateInterval) return;
    
    dashboardUpdateInterval = setInterval(async () => {
        if (currentTab === 'monitoring') {
            await updateDashboardStatus();
            await updateDashboardEvents();
            await updateDashboardDevices();
        }
    }, 5000);
    
    // Update immediately
    updateDashboardStatus();
    updateDashboardEvents();
    updateDashboardDevices();
}

async function updateDashboardStatus() {
    try {
        const response = await fetch(getAgentApiUrl('/status'));
        const status = await response.json();
        
        // Update ZTP status display
        const statusDisplay = document.getElementById('ztp-status-display');
        const controlStatus = document.getElementById('ztp-control-status');
        
        if (status.running) {
            statusDisplay.textContent = 'Running';
            statusDisplay.className = 'stat-number status-running';
            if (controlStatus) {
                controlStatus.textContent = 'Active';
                controlStatus.className = 'stat-number status-running';
            }
        } else if (status.starting) {
            statusDisplay.textContent = 'Starting...';
            statusDisplay.className = 'stat-number status-starting';
            if (controlStatus) {
                controlStatus.textContent = 'Starting';
                controlStatus.className = 'stat-number status-starting';
            }
        } else {
            statusDisplay.textContent = 'Stopped';
            statusDisplay.className = 'stat-number status-stopped';
            if (controlStatus) {
                controlStatus.textContent = 'Ready';
                controlStatus.className = 'stat-number status-stopped';
            }
        }
        
        // Update device counters
        const totalSwitches = document.getElementById('total-switches');
        const totalAps = document.getElementById('total-aps');
        const configuredDevices = document.getElementById('configured-devices');
        
        if (totalSwitches) totalSwitches.textContent = status.switches_discovered || 0;
        if (totalAps) totalAps.textContent = status.aps_discovered || 0;
        if (configuredDevices) configuredDevices.textContent = (status.switches_configured || 0) + (status.aps_configured || 0);
        
    } catch (error) {
        console.error('Failed to update dashboard status:', error);
    }
}

async function updateDashboardEvents() {
    try {
        const response = await fetch(getAgentApiUrl('/events?limit=5'));
        const events = await response.json();
        
        console.log('Dashboard events response:', events); // Debug log
        
        const eventsContainer = document.getElementById('recent-events');
        eventsContainer.innerHTML = '';
        
        events.slice(0, 5).forEach(event => {
            const eventDiv = document.createElement('div');
            eventDiv.className = `event-item ${event.event_type}`;
            
            const timestamp = new Date(event.timestamp).toLocaleTimeString();
            eventDiv.innerHTML = `
                <div class="event-timestamp">${timestamp}</div>
                <div class="event-type">${event.event_type}</div>
                <div>${event.message || JSON.stringify(event.data)}</div>
            `;
            
            eventsContainer.appendChild(eventDiv);
        });
        
        if (events.length === 0) {
            eventsContainer.innerHTML = '<div class="no-events">No recent events</div>';
        }
        
    } catch (error) {
        console.error('Failed to update dashboard events:', error);
    }
}

async function updateDashboardDevices() {
    try {
        const response = await fetch(getAgentApiUrl('/devices'));
        const devices = await response.json();
        
        const tbody = document.querySelector('#dashboard-device-table tbody');
        tbody.innerHTML = '';
        
        devices.forEach(device => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${device.ip}</td>
                <td>${device.mac || 'Unknown'}</td>
                <td>${device.device_type || 'Unknown'}</td>
                <td>${device.model || 'Unknown'}</td>
                <td class="status-${device.status}">${device.status}</td>
                <td>${new Date().toLocaleTimeString()}</td>
            `;
            tbody.appendChild(row);
        });
        
        if (devices.length === 0) {
            const row = document.createElement('tr');
            row.innerHTML = '<td colspan="6" style="text-align: center; color: #666;">No devices discovered</td>';
            tbody.appendChild(row);
        }
        
    } catch (error) {
        console.error('Failed to update dashboard devices:', error);
    }
}

// Events Functions
async function refreshEvents() {
    try {
        const response = await fetch(getAgentApiUrl('/events?limit=100'));
        const events = await response.json();
        
        console.log('Events page response:', events); // Debug log
        
        const eventsList = document.getElementById('events-list');
        eventsList.innerHTML = '';
        
        events.forEach(event => {
            const eventDiv = document.createElement('div');
            eventDiv.className = `event-item-detailed ${event.event_type}`;
            
            const timestamp = new Date(event.timestamp).toLocaleString();
            eventDiv.innerHTML = `
                <div class="event-header">
                    <div class="event-type">${event.event_type}</div>
                    <div class="event-timestamp">${timestamp}</div>
                </div>
                <div class="event-message">${event.message || ''}</div>
                <div class="event-data">${JSON.stringify(event.data, null, 2)}</div>
            `;
            
            eventsList.appendChild(eventDiv);
        });
        
        if (events.length === 0) {
            eventsList.innerHTML = '<div class="no-events">No events found</div>';
        }
        
    } catch (error) {
        console.error('Failed to refresh events:', error);
        showNotification('Failed to refresh events', 'error');
    }
}

function clearEvents() {
    const eventsList = document.getElementById('events-list');
    eventsList.innerHTML = '<div class="no-events">Events cleared</div>';
    showNotification('Events cleared', 'success');
}

function updateEvents() {
    refreshEvents();
}

// Logs Functions
async function refreshLogs() {
    try {
        const response = await fetch(getAgentApiUrl('/logs'));
        const logs = await response.json();
        
        const logOutput = document.getElementById('log-output');
        logOutput.innerHTML = '';
        
        logs.forEach(log => {
            const logDiv = document.createElement('div');
            logDiv.className = `log-entry log-level-${log.level}`;
            
            const timestamp = new Date(log.timestamp).toLocaleString();
            logDiv.innerHTML = `
                <span class="log-timestamp">[${timestamp}]</span>
                <span class="log-level">[${log.level.toUpperCase()}]</span>
                <span class="log-message">${log.message}</span>
            `;
            
            logOutput.appendChild(logDiv);
        });
        
        if (logs.length === 0) {
            logOutput.innerHTML = '<div class="no-logs">No logs available</div>';
        }
        
        // Scroll to bottom
        logOutput.scrollTop = logOutput.scrollHeight;
        
    } catch (error) {
        console.error('Failed to refresh logs:', error);
        showNotification('Failed to refresh logs', 'error');
    }
}

function clearLogs() {
    const logOutput = document.getElementById('log-output');
    logOutput.innerHTML = '<div class="no-logs">Logs cleared</div>';
    showNotification('Logs cleared', 'success');
}

// Single-agent specific functions
async function saveAndStartZTP() {
    await saveConfig();
    await startZTP();
}

async function toggleZTP() {
    const statusDisplay = document.getElementById('ztp-status-display');
    const isRunning = statusDisplay.textContent === 'Running';
    
    if (isRunning) {
        await stopZTP();
    } else {
        await startZTP();
    }
}

// Auto-refresh for different tabs (modified for single agent view)
setInterval(async () => {
    if (currentTab === 'monitoring') {
        await updateStatus();
        await updateDeviceList();
    } else if (currentTab === 'events') {
        await refreshEvents();
    } else if (currentTab === 'logs') {
        await refreshLogs();
    }
}, 10000); // Refresh every 10 seconds