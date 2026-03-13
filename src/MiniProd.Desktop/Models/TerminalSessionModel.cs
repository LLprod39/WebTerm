namespace MiniProd.Desktop.Models;

public sealed class TerminalSessionModel
{
    public string Theme { get; set; } = "System";

    public string ActiveServerName { get; set; } = "No server selected";

    public string ConnectionState { get; set; } = "disconnected";
}
