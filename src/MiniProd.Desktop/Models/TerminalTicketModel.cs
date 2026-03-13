using System.Text.Json.Serialization;

namespace MiniProd.Desktop.Models;

public sealed class TerminalTicketModel
{
    [JsonPropertyName("server_id")]
    public int? ServerId { get; init; }

    [JsonPropertyName("ws_token")]
    public string WsToken { get; init; } = string.Empty;

    public string Path { get; init; } = string.Empty;

    [JsonPropertyName("ws_url")]
    public string WsUrl { get; init; } = string.Empty;
}
