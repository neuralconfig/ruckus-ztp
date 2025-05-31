import SwiftUI

struct TopologyView: View {
    @State private var topologyNodes: [TopologyNode] = []
    @State private var topologyLinks: [TopologyLink] = []
    @State private var isLoading = false
    @State private var autoRefresh = true
    @State private var refreshTimer: Timer?
    
    var body: some View {
        NavigationView {
            ZStack {
                if isLoading && topologyNodes.isEmpty {
                    ProgressView("Loading topology...")
                        .progressViewStyle(CircularProgressViewStyle())
                } else if topologyNodes.isEmpty {
                    VStack(spacing: 20) {
                        Image(systemName: "network.slash")
                            .font(.system(size: 60))
                            .foregroundColor(.gray)
                        Text("No topology data available")
                            .font(.headline)
                            .foregroundColor(.secondary)
                        Button("Refresh") {
                            Task {
                                await loadTopology()
                            }
                        }
                        .buttonStyle(BorderedButtonStyle())
                    }
                } else {
                    TopologyCanvas(nodes: topologyNodes, links: topologyLinks)
                }
                
                VStack {
                    HStack {
                        Toggle("Auto-refresh", isOn: $autoRefresh)
                            .toggleStyle(SwitchToggleStyle())
                            .onChange(of: autoRefresh) { value in
                                if value {
                                    startAutoRefresh()
                                } else {
                                    stopAutoRefresh()
                                }
                            }
                        
                        Spacer()
                        
                        Button(action: {
                            Task {
                                await loadTopology()
                            }
                        }) {
                            Image(systemName: "arrow.clockwise")
                        }
                        .buttonStyle(BorderedButtonStyle())
                    }
                    .padding()
                    .background(Color(.systemBackground).opacity(0.9))
                    
                    Spacer()
                }
            }
            .navigationTitle("Network Topology")
            .navigationBarItems(trailing: Button(action: exportTopology) {
                Image(systemName: "square.and.arrow.up")
            })
        }
        .task {
            await loadTopology()
            if autoRefresh {
                startAutoRefresh()
            }
        }
        .onDisappear {
            stopAutoRefresh()
        }
    }
    
    @MainActor
    private func loadTopology() async {
        isLoading = true
        defer { isLoading = false }
        
        // Use device data to build topology since /api/topology doesn't exist
        guard let url = URL(string: "\(Config.baseURL)/api/devices") else { return }
        
        do {
            let (data, _) = try await URLSession.shared.data(from: url)
            let devices = try JSONDecoder().decode([DeviceInfo].self, from: data)
            
            // Build nodes from devices
            var nodes: [TopologyNode] = []
            var links: [TopologyLink] = []
            
            // Create nodes for each device
            for (index, device) in devices.enumerated() {
                let x = Double.random(in: 0.2...0.8) // Random positioning
                let y = Double.random(in: 0.2...0.8)
                
                let node = TopologyNode(
                    id: device.ip,
                    label: device.hostname ?? device.ip,
                    type: device.isSeed ? "seed" : device.deviceType,
                    x: x,
                    y: y
                )
                nodes.append(node)
            }
            
            // Create links based on device relationships
            for device in devices {
                // Create links for APs connected to switches
                if device.deviceType == "ap", let connectedSwitch = device.connectedSwitch {
                    let link = TopologyLink(
                        id: "\(connectedSwitch)-\(device.ip)",
                        source: connectedSwitch,
                        target: device.ip,
                        sourcePort: device.connectedPort,
                        targetPort: nil
                    )
                    links.append(link)
                }
                
                // Create switch-to-switch links from neighbors data
                if device.deviceType == "switch" {
                    for (port, neighborData) in device.neighbors {
                        // Debug: Print neighbor data structure
                        print("Debug - Switch \(device.ip) port \(port) neighbor data: \(neighborData.value)")
                        
                        // Try different possible structures for neighbor data
                        var neighborIP: String?
                        
                        // Try as direct string (simple case)
                        if let ipString = neighborData.value as? String {
                            neighborIP = ipString
                        }
                        // Try as dictionary with "ip" key
                        else if let neighborDict = neighborData.value as? [String: Any],
                           let ip = neighborDict["ip"] as? String {
                            neighborIP = ip
                        }
                        // Try as dictionary with other possible keys
                        else if let neighborDict = neighborData.value as? [String: Any] {
                            // Look for any IP-like values in the dictionary
                            for (key, value) in neighborDict {
                                if let stringValue = value as? String,
                                   isValidIP(stringValue) {
                                    neighborIP = stringValue
                                    break
                                }
                            }
                        }
                        
                        if let ip = neighborIP {
                            print("Debug - Found neighbor IP: \(ip)")
                            // Only create link if target switch exists and avoid duplicates
                            if devices.contains(where: { $0.ip == ip && $0.deviceType == "switch" }) {
                                let linkId = [device.ip, ip].sorted().joined(separator: "-")
                                // Check if this link already exists (avoid duplicates)
                                if !links.contains(where: { $0.id == linkId }) {
                                    let link = TopologyLink(
                                        id: linkId,
                                        source: device.ip,
                                        target: ip,
                                        sourcePort: port,
                                        targetPort: nil
                                    )
                                    links.append(link)
                                    print("Debug - Created link: \(device.ip) -> \(ip)")
                                }
                            } else {
                                print("Debug - No matching switch found for IP: \(ip)")
                            }
                        } else {
                            print("Debug - Could not extract IP from neighbor data")
                        }
                    }
                }
            }
            
            self.topologyNodes = nodes
            self.topologyLinks = links
            
        } catch {
            print("Failed to load topology: \(error)")
        }
    }
    
    private func isValidIP(_ string: String) -> Bool {
        let ipRegex = "^(?:[0-9]{1,3}\\.){3}[0-9]{1,3}$"
        return NSPredicate(format: "SELF MATCHES %@", ipRegex).evaluate(with: string)
    }
    
    private func startAutoRefresh() {
        stopAutoRefresh()
        refreshTimer = Timer.scheduledTimer(withTimeInterval: 10.0, repeats: true) { _ in
            Task {
                await loadTopology()
            }
        }
    }
    
    private func stopAutoRefresh() {
        refreshTimer?.invalidate()
        refreshTimer = nil
    }
    
    private func exportTopology() {
        // TODO: Implement export functionality
        print("Export topology")
    }
}

// MARK: - Topology Data Model
struct TopologyData: Codable {
    let nodes: [Node]
    let links: [Link]
    
    struct Node: Codable {
        let id: String
        let label: String
        let type: String
        let x: Double
        let y: Double
    }
    
    struct Link: Codable {
        let source: String
        let target: String
        let sourcePort: String?
        let targetPort: String?
        
        enum CodingKeys: String, CodingKey {
            case source, target
            case sourcePort = "source_port"
            case targetPort = "target_port"
        }
    }
}

// MARK: - Topology Canvas View
struct TopologyCanvas: View {
    @State private var nodePositions: [String: CGPoint] = [:]
    let nodes: [TopologyNode]
    let links: [TopologyLink]
    
    var body: some View {
        GeometryReader { geometry in
            ZStack {
                // Draw links
                ForEach(links) { link in
                    if let sourcePos = nodePositions[link.source],
                       let targetPos = nodePositions[link.target] {
                        Path { path in
                            path.move(to: sourcePos)
                            path.addLine(to: targetPos)
                        }
                        .stroke(Color.gray, lineWidth: 2)
                        
                        // Port labels
                        if let sourcePort = link.sourcePort {
                            Text(sourcePort)
                                .font(.caption2)
                                .padding(4)
                                .background(Color(.systemBackground))
                                .cornerRadius(4)
                                .position(
                                    x: (sourcePos.x * 0.7 + targetPos.x * 0.3),
                                    y: (sourcePos.y * 0.7 + targetPos.y * 0.3)
                                )
                        }
                    }
                }
                
                // Draw nodes (draggable)
                ForEach(nodes) { node in
                    DraggableNodeView(
                        node: node,
                        position: nodePositions[node.id] ?? defaultPosition(for: node, in: geometry),
                        onPositionChanged: { newPosition in
                            nodePositions[node.id] = newPosition
                        }
                    )
                }
            }
            .onAppear {
                // Initialize positions if not set
                for node in nodes {
                    if nodePositions[node.id] == nil {
                        nodePositions[node.id] = defaultPosition(for: node, in: geometry)
                    }
                }
            }
        }
        .padding()
    }
    
    private func defaultPosition(for node: TopologyNode, in geometry: GeometryProxy) -> CGPoint {
        // Better initial positioning logic
        let centerX = geometry.size.width / 2
        let centerY = geometry.size.height / 2
        
        switch node.type {
        case "seed":
            return CGPoint(x: centerX, y: centerY - 100)
        case "switch":
            // Arrange switches in a circle around center
            let switchNodes = nodes.filter { $0.type == "switch" || $0.type == "seed" }
            let switchIndex = switchNodes.firstIndex(where: { $0.id == node.id }) ?? 0
            let angle = Double(switchIndex) * 2 * Double.pi / Double(max(switchNodes.count, 1))
            let radius: Double = 120
            return CGPoint(
                x: centerX + cos(angle) * radius,
                y: centerY + sin(angle) * radius
            )
        case "ap":
            // Position APs around their connected switches
            return CGPoint(x: centerX + Double.random(in: -80...80), y: centerY + 150)
        default:
            return CGPoint(x: centerX, y: centerY)
        }
    }
}

// MARK: - Draggable Node View
struct DraggableNodeView: View {
    let node: TopologyNode
    let position: CGPoint
    let onPositionChanged: (CGPoint) -> Void
    
    @State private var dragOffset = CGSize.zero
    
    var nodeColor: Color {
        switch node.type {
        case "switch":
            return .blue
        case "ap":
            return .purple
        case "seed":
            return .green
        default:
            return .gray
        }
    }
    
    var nodeIcon: String {
        switch node.type {
        case "switch", "seed":
            return "network"
        case "ap":
            return "wifi"
        default:
            return "questionmark.circle"
        }
    }
    
    var body: some View {
        VStack(spacing: 4) {
            ZStack {
                Circle()
                    .fill(nodeColor.opacity(0.2))
                    .stroke(nodeColor, lineWidth: 2)
                    .frame(width: 60, height: 60)
                
                Image(systemName: nodeIcon)
                    .foregroundColor(nodeColor)
                    .font(.title2)
            }
            
            Text(node.label)
                .font(.caption)
                .fontWeight(.medium)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 100)
                .background(Color(.systemBackground).opacity(0.8))
                .cornerRadius(4)
        }
        .position(x: position.x + dragOffset.width, y: position.y + dragOffset.height)
        .gesture(
            DragGesture()
                .onChanged { value in
                    dragOffset = value.translation
                }
                .onEnded { value in
                    let newPosition = CGPoint(
                        x: position.x + value.translation.width,
                        y: position.y + value.translation.height
                    )
                    onPositionChanged(newPosition)
                    dragOffset = .zero
                }
        )
    }
}

// MARK: - Static Node View (for reference)
struct NodeView: View {
    let node: TopologyNode
    
    var nodeColor: Color {
        switch node.type {
        case "switch":
            return .blue
        case "ap":
            return .purple
        case "seed":
            return .green
        default:
            return .gray
        }
    }
    
    var nodeIcon: String {
        switch node.type {
        case "switch", "seed":
            return "network"
        case "ap":
            return "wifi"
        default:
            return "questionmark.circle"
        }
    }
    
    var body: some View {
        VStack(spacing: 4) {
            ZStack {
                Circle()
                    .fill(nodeColor.opacity(0.2))
                    .frame(width: 50, height: 50)
                
                Image(systemName: nodeIcon)
                    .foregroundColor(nodeColor)
                    .font(.title2)
            }
            
            Text(node.label)
                .font(.caption)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 80)
        }
    }
}

struct TopologyView_Previews: PreviewProvider {
    static var previews: some View {
        TopologyView()
    }
}