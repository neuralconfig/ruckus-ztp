import SwiftUI

struct MonitoringView: View {
    @EnvironmentObject var networkManager: NetworkManager
    
    var body: some View {
        NavigationView {
            ScrollView {
                VStack(spacing: 20) {
                    // Status Cards
                    HStack(spacing: 16) {
                        StatusCard(
                            title: "ZTP Status",
                            value: networkManager.ztpStatus.starting ? "Starting..." : 
                                   (networkManager.ztpStatus.running ? "Running" : "Stopped"),
                            color: networkManager.ztpStatus.starting ? .orange :
                                   (networkManager.ztpStatus.running ? .green : .red),
                            icon: "power"
                        )
                        
                        StatusCard(
                            title: "Switches",
                            value: "\(networkManager.ztpStatus.switchesDiscovered)",
                            subtitle: "\(networkManager.ztpStatus.switchesConfigured) configured",
                            color: .blue,
                            icon: "network"
                        )
                        
                        StatusCard(
                            title: "Access Points",
                            value: "\(networkManager.ztpStatus.apsDiscovered)",
                            color: .purple,
                            icon: "wifi"
                        )
                    }
                    .padding(.horizontal)
                    
                    if let lastPoll = networkManager.ztpStatus.lastPoll {
                        Text("Last poll: \(lastPoll)")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                    
                    // Device List
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Discovered Devices")
                            .font(.headline)
                            .padding(.horizontal)
                        
                        if networkManager.devices.isEmpty {
                            Text("No devices discovered yet")
                                .foregroundColor(.secondary)
                                .frame(maxWidth: .infinity)
                                .padding()
                        } else {
                            ForEach(networkManager.devices) { device in
                                DeviceRow(device: device)
                            }
                        }
                    }
                    
                    // Connection Status
                    if !networkManager.isConnected {
                        VStack(spacing: 8) {
                            Image(systemName: "wifi.slash")
                                .font(.largeTitle)
                                .foregroundColor(.red)
                            Text("Not connected to backend")
                                .font(.headline)
                            if let error = networkManager.connectionError {
                                Text(error)
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                                    .multilineTextAlignment(.center)
                            }
                        }
                        .padding()
                        .background(Color(.systemGray6))
                        .cornerRadius(12)
                        .padding(.horizontal)
                    }
                }
                .padding(.vertical)
            }
            .navigationTitle("Monitoring")
            .navigationBarItems(trailing: Button(action: {
                Task {
                    await networkManager.fetchStatus()
                    await networkManager.fetchDevices()
                }
            }) {
                Image(systemName: "arrow.clockwise")
            })
        }
        .task {
            await networkManager.fetchStatus()
            await networkManager.fetchDevices()
        }
    }
}

struct StatusCard: View {
    let title: String
    let value: String
    var subtitle: String? = nil
    let color: Color
    let icon: String
    
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: icon)
                    .font(.title2)
                    .foregroundColor(color)
                Spacer()
            }
            
            Text(title)
                .font(.caption)
                .foregroundColor(.secondary)
            
            Text(value)
                .font(.title2)
                .fontWeight(.semibold)
            
            if let subtitle = subtitle {
                Text(subtitle)
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
        }
        .padding()
        .frame(maxWidth: .infinity)
        .background(Color(.systemGray6))
        .cornerRadius(12)
    }
}

struct DeviceRow: View {
    let device: DeviceInfo
    
    var deviceIcon: String {
        switch device.deviceType {
        case "switch":
            return "network"
        case "ap":
            return "wifi"
        default:
            return "questionmark.circle"
        }
    }
    
    var statusColor: Color {
        switch device.status {
        case "configured":
            return .green
        case "discovered":
            return .orange
        case "error":
            return .red
        default:
            return .gray
        }
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: deviceIcon)
                    .foregroundColor(.blue)
                
                VStack(alignment: .leading) {
                    Text(device.hostname ?? device.ip)
                        .font(.headline)
                    Text(device.ip)
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                
                Spacer()
                
                VStack(alignment: .trailing) {
                    HStack {
                        Circle()
                            .fill(statusColor)
                            .frame(width: 8, height: 8)
                        Text(device.status.capitalized)
                            .font(.caption)
                    }
                    
                    if device.sshActive {
                        Text("SSH Active")
                            .font(.caption2)
                            .foregroundColor(.green)
                    }
                }
            }
            
            // Additional device info
            HStack {
                if let mac = device.mac {
                    Label(mac, systemImage: "network")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                
                if let serial = device.serial {
                    Label(serial, systemImage: "number")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
            
            // AP connection info
            if device.deviceType == "ap", let connectedSwitch = device.connectedSwitch, let port = device.connectedPort {
                Label("Connected to \(connectedSwitch) port \(port)", systemImage: "link")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            
            // Switch AP ports
            if device.deviceType == "switch" && !device.apPorts.isEmpty {
                Label("APs on ports: \(device.apPorts.joined(separator: ", "))", systemImage: "wifi")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            
            // Task status with better labels
            if !device.tasksCompleted.isEmpty || !device.tasksFailed.isEmpty {
                HStack(spacing: 12) {
                    if !device.tasksCompleted.isEmpty {
                        HStack(spacing: 4) {
                            Image(systemName: "checkmark.circle.fill")
                                .foregroundColor(.green)
                            Text("\(device.tasksCompleted.count) tasks completed")
                                .font(.caption)
                                .foregroundColor(.green)
                        }
                    }
                    
                    if !device.tasksFailed.isEmpty {
                        HStack(spacing: 4) {
                            Image(systemName: "xmark.circle.fill")
                                .foregroundColor(.red)
                            Text("\(device.tasksFailed.count) tasks failed")
                                .font(.caption)
                                .foregroundColor(.red)
                        }
                    }
                }
            }
        }
        .padding()
        .background(Color(.systemGray6))
        .cornerRadius(8)
        .padding(.horizontal)
    }
}

struct MonitoringView_Previews: PreviewProvider {
    static var previews: some View {
        MonitoringView()
            .environmentObject(NetworkManager())
    }
}