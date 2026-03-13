using System.Text.Json.Serialization;

namespace MiniProd.Desktop.Models;

public sealed class ServerSummaryModel
{
    public int Id { get; init; }

    public string Name { get; init; } = string.Empty;

    public string Host { get; init; } = string.Empty;

    public int Port { get; init; } = 22;

    public string Username { get; init; } = "root";

    public string Status { get; init; } = "unknown";

    [JsonPropertyName("group_id")]
    public int? GroupId { get; init; }

    [JsonPropertyName("group_name")]
    public string GroupName { get; init; } = "Ungrouped";

    [JsonPropertyName("server_type")]
    public string ServerType { get; init; } = "ssh";

    [JsonPropertyName("is_shared")]
    public bool IsShared { get; init; }

    [JsonPropertyName("last_connected")]
    public string LastConnected { get; init; } = string.Empty;

    public string AddressLabel => $"{Username}@{Host}:{Port}";

    public string StatusLabel => $"{Status} · {ServerType.ToUpperInvariant()}";
}
