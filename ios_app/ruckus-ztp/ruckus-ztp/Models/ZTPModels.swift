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
    let neighbors: [String: AnyCodable]  // Changed to support complex objects
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

// MARK: - Log Models

struct LogResponse: Codable {
    let logs: [String]
}

// MARK: - Helper Types

struct AnyCodable: Codable {
    let value: Any
    
    init(_ value: Any) {
        self.value = value
    }
    
    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        
        if let intValue = try? container.decode(Int.self) {
            value = intValue
        } else if let doubleValue = try? container.decode(Double.self) {
            value = doubleValue
        } else if let boolValue = try? container.decode(Bool.self) {
            value = boolValue
        } else if let stringValue = try? container.decode(String.self) {
            value = stringValue
        } else if let arrayValue = try? container.decode([AnyCodable].self) {
            value = arrayValue.map { $0.value }
        } else if let dictionaryValue = try? container.decode([String: AnyCodable].self) {
            value = dictionaryValue.mapValues { $0.value }
        } else {
            throw DecodingError.dataCorruptedError(in: container, debugDescription: "Cannot decode value")
        }
    }
    
    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        
        switch value {
        case let intValue as Int:
            try container.encode(intValue)
        case let doubleValue as Double:
            try container.encode(doubleValue)
        case let boolValue as Bool:
            try container.encode(boolValue)
        case let stringValue as String:
            try container.encode(stringValue)
        case let arrayValue as [Any]:
            try container.encode(arrayValue.map { AnyCodable($0) })
        case let dictionaryValue as [String: Any]:
            try container.encode(dictionaryValue.mapValues { AnyCodable($0) })
        default:
            throw EncodingError.invalidValue(value, EncodingError.Context(codingPath: [], debugDescription: "Cannot encode value"))
        }
    }
}