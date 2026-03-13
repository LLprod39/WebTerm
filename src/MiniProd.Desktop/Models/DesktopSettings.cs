namespace MiniProd.Desktop.Models;

public sealed class DesktopSettings
{
    public string Theme { get; set; } = "Dark";

    public bool DiagnosticsEnabled { get; set; } = true;

    public string AiEndpoint { get; set; } = ResolveDefaultAiEndpoint();

    public string AiModel { get; set; } = ResolveDefaultAiModel();

    public string AiApiKey { get; set; } = ResolveDefaultAiApiKey();

    public string AiSystemPrompt { get; set; } =
        "You are an SSH terminal assistant. Read the recent terminal transcript, answer briefly, and suggest one safe next shell command when useful. Avoid destructive commands unless the operator explicitly asks for them.";

    public bool AutoApproveAiCommands { get; set; }

    private static string ResolveDefaultAiEndpoint()
    {
        var explicitEndpoint = Environment.GetEnvironmentVariable("MINIPROD_AI_ENDPOINT");
        if (!string.IsNullOrWhiteSpace(explicitEndpoint))
        {
            return explicitEndpoint;
        }

        return string.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable("OPENAI_API_KEY"))
            ? "http://127.0.0.1:11434/v1/chat/completions"
            : "https://api.openai.com/v1/chat/completions";
    }

    private static string ResolveDefaultAiModel()
    {
        var explicitModel = Environment.GetEnvironmentVariable("MINIPROD_AI_MODEL");
        if (!string.IsNullOrWhiteSpace(explicitModel))
        {
            return explicitModel;
        }

        return string.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable("OPENAI_API_KEY"))
            ? "qwen2.5-coder:7b"
            : "gpt-4.1-mini";
    }

    private static string ResolveDefaultAiApiKey()
    {
        return Environment.GetEnvironmentVariable("MINIPROD_AI_API_KEY")
            ?? Environment.GetEnvironmentVariable("OPENAI_API_KEY")
            ?? string.Empty;
    }
}
