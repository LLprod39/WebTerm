namespace MiniProd.Desktop.Models;

public sealed class ServerDraftModel
{
    public int? Id { get; set; }

    public string Name { get; set; } = string.Empty;

    public string Host { get; set; } = string.Empty;

    public int Port { get; set; } = 22;

    public string Username { get; set; } = "root";

    public string ServerType { get; set; } = "ssh";

    public string AuthMethod { get; set; } = "password";

    public string Password { get; set; } = string.Empty;

    public string KeyPath { get; set; } = string.Empty;

    public string Notes { get; set; } = string.Empty;

    public bool HasSavedSecret { get; set; }
}
