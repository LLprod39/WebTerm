namespace MiniProd.Desktop.Models;

public sealed class McpServerModel
{
    public int Id { get; init; }

    public string Name { get; init; } = string.Empty;

    public string Transport { get; init; } = "stdio";

    public string Description { get; init; } = string.Empty;

    public bool LastTestOk { get; init; }
}
