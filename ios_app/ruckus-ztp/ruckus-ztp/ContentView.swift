import SwiftUI

struct ContentView: View {
    @State private var selectedTab = 0
    
    var body: some View {
        TabView(selection: $selectedTab) {
            ConfigurationView()
                .tabItem {
                    Label("Configuration", systemImage: "gear")
                }
                .tag(0)
            
            MonitoringView()
                .tabItem {
                    Label("Monitoring", systemImage: "chart.line.uptrend.xyaxis")
                }
                .tag(1)
            
            TopologyView()
                .tabItem {
                    Label("Topology", systemImage: "network")
                }
                .tag(2)
            
            ChatView()
                .tabItem {
                    Label("AI Agent", systemImage: "message.bubble")
                }
                .tag(3)
            
            LogsView()
                .tabItem {
                    Label("Logs", systemImage: "doc.text")
                }
                .tag(4)
        }
    }
}

struct ContentView_Previews: PreviewProvider {
    static var previews: some View {
        ContentView()
            .environmentObject(NetworkManager())
            .environmentObject(ConfigurationManager())
    }
}