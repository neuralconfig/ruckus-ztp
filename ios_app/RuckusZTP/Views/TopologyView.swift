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
        
        guard let url = URL(string: "\(Config.baseURL)/api/topology") else { return }
        
        do {
            let (data, _) = try await URLSession.shared.data(from: url)
            let topology = try JSONDecoder().decode(TopologyData.self, from: data)
            
            self.topologyNodes = topology.nodes.map { node in
                TopologyNode(
                    id: node.id,
                    label: node.label,
                    type: node.type,
                    x: node.x,
                    y: node.y
                )
            }
            
            self.topologyLinks = topology.links.map { link in
                TopologyLink(
                    id: "\(link.source)-\(link.target)",
                    source: link.source,
                    target: link.target,
                    sourcePort: link.sourcePort,
                    targetPort: link.targetPort
                )
            }
        } catch {
            print("Failed to load topology: \(error)")
        }
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
    let nodes: [TopologyNode]
    let links: [TopologyLink]
    
    var body: some View {
        GeometryReader { geometry in
            ZStack {
                // Draw links
                ForEach(links) { link in
                    if let sourceNode = nodes.first(where: { $0.id == link.source }),
                       let targetNode = nodes.first(where: { $0.id == link.target }) {
                        Path { path in
                            path.move(to: CGPoint(
                                x: sourceNode.x * geometry.size.width,
                                y: sourceNode.y * geometry.size.height
                            ))
                            path.addLine(to: CGPoint(
                                x: targetNode.x * geometry.size.width,
                                y: targetNode.y * geometry.size.height
                            ))
                        }
                        .stroke(Color.gray, lineWidth: 2)
                        
                        // Port labels
                        if let sourcePort = link.sourcePort {
                            Text(sourcePort)
                                .font(.caption2)
                                .padding(2)
                                .background(Color(.systemBackground))
                                .position(
                                    x: (sourceNode.x * 0.7 + targetNode.x * 0.3) * geometry.size.width,
                                    y: (sourceNode.y * 0.7 + targetNode.y * 0.3) * geometry.size.height
                                )
                        }
                        
                        if let targetPort = link.targetPort {
                            Text(targetPort)
                                .font(.caption2)
                                .padding(2)
                                .background(Color(.systemBackground))
                                .position(
                                    x: (sourceNode.x * 0.3 + targetNode.x * 0.7) * geometry.size.width,
                                    y: (sourceNode.y * 0.3 + targetNode.y * 0.7) * geometry.size.height
                                )
                        }
                    }
                }
                
                // Draw nodes
                ForEach(nodes) { node in
                    NodeView(node: node)
                        .position(
                            x: node.x * geometry.size.width,
                            y: node.y * geometry.size.height
                        )
                }
            }
        }
        .padding()
    }
}

// MARK: - Node View
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