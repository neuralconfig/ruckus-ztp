import Foundation

// MARK: - Configuration Models

struct CredentialPair: Codable, Identifiable {
    var id = UUID()
    let username: String
    let password: String
    
    enum CodingKeys: String, CodingKey {
        case username, password
    }
}

struct SeedSwitch: Codable, Identifiable {
    var id = UUID()
    let ip: String
    let credentialsId: Int?
    
    enum CodingKeys: String, CodingKey {
        case ip
        case credentialsId = "credentials_id"
    }
}

struct ZTPConfiguration: Codable {
    let credentials: [CredentialPair]
    let preferredPassword: String
    let seedSwitches: [SeedSwitch]
    let baseConfigName: String
    let openrouterApiKey: String?
    let model: String
    let managementVlan: Int
    let wirelessVlans: [Int]
    let ipPool: String
    let gateway: String
    let dnsServer: String
    let pollInterval: Int
    
    enum CodingKeys: String, CodingKey {
        case credentials
        case preferredPassword = "preferred_password"
        case seedSwitches = "seed_switches"
        case baseConfigName = "base_config_name"
        case openrouterApiKey = "openrouter_api_key"
        case model
        case managementVlan = "management_vlan"
        case wirelessVlans = "wireless_vlans"
        case ipPool = "ip_pool"
        case gateway
        case dnsServer = "dns_server"
        case pollInterval = "poll_interval"
    }
}

// MARK: - Status Models

struct ZTPStatus: Codable {
    let running: Bool
    let starting: Bool
    let switchesDiscovered: Int
    let switchesConfigured: Int
    let apsDiscovered: Int
    let lastPoll: String?
    let errors: [String]
    
    enum CodingKeys: String, CodingKey {
        case running, starting
        case switchesDiscovered = "switches_discovered"
        case switchesConfigured = "switches_configured"
        case apsDiscovered = "aps_discovered"
        case lastPoll = "last_poll"
        case errors
    }
}

// MARK: - Device Models

struct DeviceInfo: Codable, Identifiable {
    var id: String { ip }
    let ip: String
    let mac: String?
    let hostname: String?
    let model: String?
    let serial: String?
    let status: String
    let deviceType: String
    let neighbors: [String: String]
    let tasksCompleted: [String]
    let tasksFailed: [String]
    let isSeed: Bool
    let apPorts: [String]
    let connectedSwitch: String?
    let connectedPort: String?
    let sshActive: Bool
    
    enum CodingKeys: String, CodingKey {
        case ip, mac, hostname, model, serial, status
        case deviceType = "device_type"
        case neighbors
        case tasksCompleted = "tasks_completed"
        case tasksFailed = "tasks_failed"
        case isSeed = "is_seed"
        case apPorts = "ap_ports"
        case connectedSwitch = "connected_switch"
        case connectedPort = "connected_port"
        case sshActive = "ssh_active"
    }
}

// MARK: - Chat Models

struct ChatMessage: Codable {
    let message: String
}

struct ChatResponse: Codable {
    let response: String
}

// MARK: - Topology Models

struct TopologyNode: Identifiable {
    let id: String
    let label: String
    let type: String
    let x: Double
    let y: Double
}

struct TopologyLink: Identifiable {
    let id: String
    let source: String
    let target: String
    let sourcePort: String?
    let targetPort: String?
}