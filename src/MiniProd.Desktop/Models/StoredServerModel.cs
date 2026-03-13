namespace MiniProd.Desktop.Models;

public sealed class StoredServerModel
{
    public int Id { get; set; }

    public string Name { get; set; } = string.Empty;

    public string Host { get; set; } = string.Empty;

    public int Port { get; set; } = 22;

    public string Username { get; set; } = "root";

    public string ServerType { get; set; } = "ssh";

    public string AuthMethod { get; set; } = "password";

    public string ProtectedSecret { get; set; } = string.Empty;

    public string KeyPath { get; set; } = string.Empty;

    public string Notes { get; set; } = string.Empty;

    public DateTimeOffset? LastConnectedAt { get; set; }

    public string LastError { get; set; } = string.Empty;

    public ServerSummaryModel ToSummary()
    {
        return new ServerSummaryModel
        {
            Id = Id,
            Name = Name,
            Host = Host,
            Port = Port,
            Username = Username,
            Status = BuildStatus(),
            GroupName = "Local",
            ServerType = ServerType,
            LastConnected = LastConnectedAt?.ToLocalTime().ToString("g") ?? string.Empty,
        };
    }

    public ServerDraftModel ToDraft()
    {
        return new ServerDraftModel
        {
            Id = Id,
            Name = Name,
            Host = Host,
            Port = Port,
            Username = Username,
            ServerType = ServerType,
            AuthMethod = AuthMethod,
            KeyPath = KeyPath,
            Notes = Notes,
            HasSavedSecret = !string.IsNullOrWhiteSpace(ProtectedSecret),
        };
    }

    public StoredServerModel Clone()
    {
        return new StoredServerModel
        {
            Id = Id,
            Name = Name,
            Host = Host,
            Port = Port,
            Username = Username,
            ServerType = ServerType,
            AuthMethod = AuthMethod,
            ProtectedSecret = ProtectedSecret,
            KeyPath = KeyPath,
            Notes = Notes,
            LastConnectedAt = LastConnectedAt,
            LastError = LastError,
        };
    }

    private string BuildStatus()
    {
        if (!string.IsNullOrWhiteSpace(LastError))
        {
            return "error";
        }

        return LastConnectedAt is null ? "new" : "ready";
    }
}
