import Foundation
import Combine

class ConfigurationManager: ObservableObject {
    @Published var credentials: [CredentialPair] = [
        CredentialPair(username: "super", password: "sp-admin")
    ]
    @Published var preferredPassword = ""
    @Published var seedSwitches: [SeedSwitch] = []
    @Published var baseConfigName = "default"
    @Published var baseConfigs: [String: String] = [:]
    @Published var openrouterApiKey = ""
    @Published var selectedModel = "anthropic/claude-3-5-haiku"
    @Published var managementVlan = 10
    @Published var wirelessVlans = "20,30,40"
    @Published var ipPool = "192.168.10.0/24"
    @Published var gateway = "192.168.10.1"
    @Published var dnsServer = "192.168.10.2"
    @Published var pollInterval = 60
    
    private var cancellables = Set<AnyCancellable>()
    
    init() {
        Task {
            await loadConfiguration()
            await loadBaseConfigs()
        }
    }
    
    @MainActor
    func loadConfiguration() async {
        guard let url = URL(string: "\(Config.baseURL)/api/config") else { return }
        
        do {
            let (data, _) = try await URLSession.shared.data(from: url)
            let config = try JSONDecoder().decode(ZTPConfiguration.self, from: data)
            
            self.credentials = config.credentials
            self.preferredPassword = config.preferredPassword
            self.seedSwitches = config.seedSwitches
            self.baseConfigName = config.baseConfigName
            self.openrouterApiKey = config.openrouterApiKey ?? ""
            self.selectedModel = config.model
            self.managementVlan = config.managementVlan
            self.wirelessVlans = config.wirelessVlans.map(String.init).joined(separator: ",")
            self.ipPool = config.ipPool
            self.gateway = config.gateway
            self.dnsServer = config.dnsServer
            self.pollInterval = config.pollInterval
        } catch {
            print("Failed to load configuration: \(error)")
        }
    }
    
    @MainActor
    func loadBaseConfigs() async {
        guard let url = URL(string: "\(Config.baseURL)/api/base-configs") else { return }
        
        do {
            let (data, _) = try await URLSession.shared.data(from: url)
            self.baseConfigs = try JSONDecoder().decode([String: String].self, from: data)
        } catch {
            print("Failed to load base configs: \(error)")
        }
    }
    
    @MainActor
    func saveConfiguration() async throws {
        guard let url = URL(string: "\(Config.baseURL)/api/config") else { return }
        
        let vlans = wirelessVlans.split(separator: ",").compactMap { Int($0.trimmingCharacters(in: .whitespaces)) }
        
        let config = ZTPConfiguration(
            credentials: credentials,
            preferredPassword: preferredPassword,
            seedSwitches: seedSwitches,
            baseConfigName: baseConfigName,
            openrouterApiKey: openrouterApiKey.isEmpty ? nil : openrouterApiKey,
            model: selectedModel,
            managementVlan: managementVlan,
            wirelessVlans: vlans,
            ipPool: ipPool,
            gateway: gateway,
            dnsServer: dnsServer,
            pollInterval: pollInterval
        )
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(config)
        
        let (_, _) = try await URLSession.shared.data(for: request)
    }
    
    func addCredential(_ credential: CredentialPair) {
        credentials.append(credential)
    }
    
    func removeCredential(at index: Int) {
        guard index > 0 && index < credentials.count else { return }
        credentials.remove(at: index)
    }
    
    func addSeedSwitch(_ seedSwitch: SeedSwitch) {
        seedSwitches.append(seedSwitch)
    }
    
    func removeSeedSwitch(at index: Int) {
        guard index < seedSwitches.count else { return }
        seedSwitches.remove(at: index)
    }
    
    @MainActor
    func uploadBaseConfig(name: String, content: String) async throws {
        guard let url = URL(string: "\(Config.baseURL)/api/base-configs/upload") else { return }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        
        let boundary = UUID().uuidString
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        
        var body = Data()
        
        // Add name field
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"name\"\r\n\r\n".data(using: .utf8)!)
        body.append("\(name)\r\n".data(using: .utf8)!)
        
        // Add file field
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"file\"; filename=\"\(name).txt\"\r\n".data(using: .utf8)!)
        body.append("Content-Type: text/plain\r\n\r\n".data(using: .utf8)!)
        body.append(content.data(using: .utf8)!)
        body.append("\r\n".data(using: .utf8)!)
        
        body.append("--\(boundary)--\r\n".data(using: .utf8)!)
        
        request.httpBody = body
        
        let (_, _) = try await URLSession.shared.data(for: request)
        await loadBaseConfigs()
    }
}