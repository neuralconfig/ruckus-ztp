import Foundation
import Combine

class NetworkManager: ObservableObject {
    @Published var ztpStatus = ZTPStatus(
        running: false,
        starting: false,
        switchesDiscovered: 0,
        switchesConfigured: 0,
        apsDiscovered: 0,
        lastPoll: nil,
        errors: []
    )
    
    @Published var devices: [DeviceInfo] = []
    @Published var isConnected = false
    @Published var connectionError: String?
    
    private var cancellables = Set<AnyCancellable>()
    private var statusTimer: Timer?
    private var webSocketTask: URLSessionWebSocketTask?
    
    init() {
        startStatusUpdates()
    }
    
    func startStatusUpdates() {
        statusTimer?.invalidate()
        statusTimer = Timer.scheduledTimer(withTimeInterval: 5.0, repeats: true) { _ in
            Task { @MainActor in
                await self.fetchStatus()
                await self.fetchDevices()
            }
        }
    }
    
    func stopStatusUpdates() {
        statusTimer?.invalidate()
        statusTimer = nil
    }
    
    @MainActor
    func fetchStatus() async {
        guard let url = URL(string: "\(Config.baseURL)/api/status") else { return }
        
        do {
            let (data, _) = try await URLSession.shared.data(from: url)
            let status = try JSONDecoder().decode(ZTPStatus.self, from: data)
            self.ztpStatus = status
            self.connectionError = nil
            self.isConnected = true
        } catch {
            self.connectionError = "Failed to fetch status: \(error.localizedDescription)"
            self.isConnected = false
        }
    }
    
    @MainActor
    func fetchDevices() async {
        guard let url = URL(string: "\(Config.baseURL)/api/devices") else { return }
        
        do {
            let (data, _) = try await URLSession.shared.data(from: url)
            let devices = try JSONDecoder().decode([DeviceInfo].self, from: data)
            self.devices = devices
        } catch {
            print("Failed to fetch devices: \(error)")
        }
    }
    
    @MainActor
    func startZTP() async {
        guard let url = URL(string: "\(Config.baseURL)/api/ztp/start") else { return }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        
        do {
            let (_, _) = try await URLSession.shared.data(for: request)
            await fetchStatus()
        } catch {
            self.connectionError = "Failed to start ZTP: \(error.localizedDescription)"
        }
    }
    
    @MainActor
    func stopZTP() async {
        guard let url = URL(string: "\(Config.baseURL)/api/ztp/stop") else { return }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        
        do {
            let (_, _) = try await URLSession.shared.data(for: request)
            await fetchStatus()
        } catch {
            self.connectionError = "Failed to stop ZTP: \(error.localizedDescription)"
        }
    }
    
    // WebSocket connection for real-time updates
    func connectWebSocket() {
        guard let url = URL(string: Config.wsURL) else { return }
        
        let session = URLSession(configuration: .default)
        webSocketTask = session.webSocketTask(with: url)
        webSocketTask?.resume()
        
        receiveWebSocketMessage()
    }
    
    func disconnectWebSocket() {
        webSocketTask?.cancel(with: .goingAway, reason: nil)
        webSocketTask = nil
    }
    
    private func receiveWebSocketMessage() {
        webSocketTask?.receive { result in
            switch result {
            case .success(let message):
                switch message {
                case .string(let text):
                    self.handleWebSocketMessage(text)
                case .data(let data):
                    if let text = String(data: data, encoding: .utf8) {
                        self.handleWebSocketMessage(text)
                    }
                @unknown default:
                    break
                }
                
                // Continue receiving messages
                self.receiveWebSocketMessage()
                
            case .failure(let error):
                print("WebSocket error: \(error)")
                self.isConnected = false
            }
        }
    }
    
    private func handleWebSocketMessage(_ message: String) {
        // Parse and handle WebSocket messages
        // This would typically update the UI with real-time data
        print("WebSocket message: \(message)")
    }
    
    deinit {
        stopStatusUpdates()
        disconnectWebSocket()
    }
}