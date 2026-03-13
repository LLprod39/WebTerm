namespace MiniProd.Desktop.Models;

public sealed class TerminalBridgePayload
{
    public string Theme { get; init; } = "System";

    public int ServerId { get; init; }

    public string ServerName { get; init; } = string.Empty;

    public string SessionState { get; init; } = "disconnected";

    public bool AiConfigured { get; init; }

    public bool AutoApproveAiCommands { get; init; }
}
