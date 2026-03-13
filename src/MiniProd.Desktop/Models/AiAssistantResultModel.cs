namespace MiniProd.Desktop.Models;

public sealed class AiAssistantResultModel
{
    public string Answer { get; init; } = string.Empty;

    public string Command { get; init; } = string.Empty;

    public string Risk { get; init; } = string.Empty;

    public bool RunRecommended { get; init; }
}
