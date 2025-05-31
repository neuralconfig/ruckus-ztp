import SwiftUI

struct LogsView: View {
    @State private var logs: [LogEntry] = []
    @State private var isLoading = false
    @State private var selectedLogLevel: LogLevel = .all
    @State private var searchText = ""
    
    var filteredLogs: [LogEntry] {
        logs.filter { log in
            let matchesLevel = selectedLogLevel == .all || log.level == selectedLogLevel
            let matchesSearch = searchText.isEmpty || 
                log.message.localizedCaseInsensitiveContains(searchText) ||
                log.timestamp.localizedCaseInsensitiveContains(searchText)
            return matchesLevel && matchesSearch
        }
    }
    
    var body: some View {
        NavigationView {
            VStack(spacing: 0) {
                // Filter controls
                VStack(spacing: 12) {
                    // Search bar
                    HStack {
                        Image(systemName: "magnifyingglass")
                            .foregroundColor(.secondary)
                        TextField("Search logs...", text: $searchText)
                    }
                    .padding(8)
                    .background(Color(.systemGray6))
                    .cornerRadius(8)
                    
                    // Log level filter
                    Picker("Log Level", selection: $selectedLogLevel) {
                        Text("All").tag(LogLevel.all)
                        Text("Info").tag(LogLevel.info)
                        Text("Warning").tag(LogLevel.warning)
                        Text("Error").tag(LogLevel.error)
                        Text("Debug").tag(LogLevel.debug)
                    }
                    .pickerStyle(SegmentedPickerStyle())
                }
                .padding()
                .background(Color(.systemBackground))
                
                Divider()
                
                // Logs list
                if isLoading {
                    Spacer()
                    ProgressView("Loading logs...")
                        .progressViewStyle(CircularProgressViewStyle())
                    Spacer()
                } else if filteredLogs.isEmpty {
                    Spacer()
                    VStack(spacing: 16) {
                        Image(systemName: "doc.text.magnifyingglass")
                            .font(.largeTitle)
                            .foregroundColor(.gray)
                        Text("No logs found")
                            .font(.headline)
                            .foregroundColor(.secondary)
                    }
                    Spacer()
                } else {
                    List(filteredLogs) { log in
                        LogEntryRow(log: log)
                    }
                    .listStyle(PlainListStyle())
                }
            }
            .navigationTitle("Logs")
            .navigationBarItems(
                trailing: HStack {
                    Button(action: clearLogs) {
                        Image(systemName: "trash")
                    }
                    Button(action: refreshLogs) {
                        Image(systemName: "arrow.clockwise")
                    }
                }
            )
        }
        .task {
            await loadLogs()
        }
    }
    
    @MainActor
    private func loadLogs() async {
        isLoading = true
        defer { isLoading = false }
        
        guard let url = URL(string: "\(Config.baseURL)/api/logs") else { return }
        
        do {
            let (data, _) = try await URLSession.shared.data(from: url)
            let logData = try JSONDecoder().decode(LogData.self, from: data)
            
            self.logs = logData.logs.map { logLine in
                // Parse log line format: [timestamp] [level] message
                let components = logLine.components(separatedBy: " ")
                let timestamp = components.first ?? ""
                let level = components.dropFirst().first ?? ""
                let message = components.dropFirst(2).joined(separator: " ")
                
                return LogEntry(
                    id: UUID(),
                    timestamp: timestamp,
                    level: LogLevel.from(string: level),
                    message: message
                )
            }
        } catch {
            print("Failed to load logs: \(error)")
        }
    }
    
    private func refreshLogs() {
        Task {
            await loadLogs()
        }
    }
    
    private func clearLogs() {
        logs = []
        // TODO: Call API to clear logs on server
    }
}

// MARK: - Log Models
struct LogData: Codable {
    let logs: [String]
}

struct LogEntry: Identifiable {
    let id: UUID
    let timestamp: String
    let level: LogLevel
    let message: String
}

enum LogLevel: String, CaseIterable {
    case all = "All"
    case info = "INFO"
    case warning = "WARNING"
    case error = "ERROR"
    case debug = "DEBUG"
    
    static func from(string: String) -> LogLevel {
        switch string.uppercased() {
        case "INFO":
            return .info
        case "WARNING", "WARN":
            return .warning
        case "ERROR":
            return .error
        case "DEBUG":
            return .debug
        default:
            return .info
        }
    }
    
    var color: Color {
        switch self {
        case .all:
            return .primary
        case .info:
            return .blue
        case .warning:
            return .orange
        case .error:
            return .red
        case .debug:
            return .gray
        }
    }
}

// MARK: - Log Entry Row
struct LogEntryRow: View {
    let log: LogEntry
    
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(log.timestamp)
                    .font(.caption)
                    .foregroundColor(.secondary)
                
                Text(log.level.rawValue)
                    .font(.caption)
                    .fontWeight(.semibold)
                    .foregroundColor(log.level.color)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(log.level.color.opacity(0.1))
                    .cornerRadius(4)
                
                Spacer()
            }
            
            Text(log.message)
                .font(.system(.caption, design: .monospaced))
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.vertical, 4)
    }
}

struct LogsView_Previews: PreviewProvider {
    static var previews: some View {
        LogsView()
    }
}