using System.Text.Json.Serialization;

namespace MiniProd.Desktop.Models;

public sealed class ServerDetailModel
{
    public int Id { get; init; }

    public string Name { get; init; } = string.Empty;

    public string Host { get; init; } = string.Empty;

    public int Port { get; init; } = 22;

    public string Username { get; init; } = "root";

    [JsonPropertyName("server_type")]
    public string ServerType { get; init; } = "ssh";

    [JsonPropertyName("auth_method")]
    public string AuthMethod { get; init; } = "password";

    [JsonPropertyName("key_path")]
    public string KeyPath { get; init; } = string.Empty;

    public string Tags { get; init; } = string.Empty;

    public string Notes { get; init; } = string.Empty;

    [JsonPropertyName("corporate_context")]
    public string CorporateContext { get; init; } = string.Empty;

    [JsonPropertyName("group_id")]
    public int? GroupId { get; init; }

    [JsonPropertyName("group_name")]
    public string GroupName { get; init; } = string.Empty;

    [JsonPropertyName("is_active")]
    public bool IsActive { get; init; } = true;

    [JsonPropertyName("has_saved_secret")]
    public bool HasSavedSecret { get; init; }

    [JsonPropertyName("can_edit")]
    public bool CanEdit { get; init; }

    [JsonPropertyName("is_shared_server")]
    public bool IsSharedServer { get; init; }
}
