using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;

namespace MiniProd.Desktop.Services;

public sealed class AiAssistantService
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web)
    {
        PropertyNameCaseInsensitive = true,
    };

    private readonly HttpClient _httpClient = new()
    {
        Timeout = TimeSpan.FromSeconds(90),
    };

    private readonly SettingsService _settingsService;

    public AiAssistantService(SettingsService settingsService)
    {
        _settingsService = settingsService;
    }

    public bool IsConfigured =>
        !string.IsNullOrWhiteSpace(_settingsService.Current.AiEndpoint) &&
        !string.IsNullOrWhiteSpace(_settingsService.Current.AiModel);

    public async Task<AiAssistantResultModel> AskAsync(
        ServerSummaryModel server,
        string transcript,
        string operatorRequest,
        CancellationToken cancellationToken = default)
    {
        if (!IsConfigured)
        {
            throw new InvalidOperationException("Configure an AI endpoint and model in Settings before using the assistant.");
        }

        if (string.IsNullOrWhiteSpace(operatorRequest))
        {
            throw new InvalidOperationException("Describe what the assistant should do.");
        }

        var settings = _settingsService.Current;
        using var request = new HttpRequestMessage(HttpMethod.Post, settings.AiEndpoint);
        if (!string.IsNullOrWhiteSpace(settings.AiApiKey))
        {
            request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", settings.AiApiKey);
        }

        request.Content = new StringContent(
            JsonSerializer.Serialize(BuildRequestBody(settings, server, transcript, operatorRequest), JsonOptions),
            Encoding.UTF8,
            "application/json");

        using var response = await _httpClient.SendAsync(request, cancellationToken);
        var payload = await response.Content.ReadAsStringAsync(cancellationToken);
        if (!response.IsSuccessStatusCode)
        {
            throw new InvalidOperationException(ReadError(payload, response.StatusCode));
        }

        var assistantContent = ExtractAssistantContent(payload);
        return ParseAssistantResponse(assistantContent);
    }

    private static object BuildRequestBody(
        DesktopSettings settings,
        ServerSummaryModel server,
        string transcript,
        string operatorRequest)
    {
        var trimmedTranscript = transcript.Length > 12_000
            ? transcript[^12_000..]
            : transcript;

        return new
        {
            model = settings.AiModel,
            temperature = 0.2,
            messages = new object[]
            {
                new
                {
                    role = "system",
                    content =
                        (string.IsNullOrWhiteSpace(settings.AiSystemPrompt)
                            ? "You are an SSH assistant."
                            : settings.AiSystemPrompt.Trim()) +
                        " Return valid JSON only with keys: answer, command, risk, runRecommended. " +
                        "Set command to an empty string when no shell command should run next.",
                },
                new
                {
                    role = "user",
                    content =
                        $"Server: {server.Name} ({server.Username}@{server.Host}:{server.Port})\n" +
                        $"User request: {operatorRequest.Trim()}\n" +
                        "Recent terminal transcript:\n" +
                        trimmedTranscript,
                },
            },
        };
    }

    private static string ExtractAssistantContent(string payload)
    {
        using var document = JsonDocument.Parse(payload);
        var root = document.RootElement;
        if (!root.TryGetProperty("choices", out var choices) || choices.GetArrayLength() == 0)
        {
            throw new InvalidOperationException("AI response did not contain any choices.");
        }

        var message = choices[0].GetProperty("message");
        var content = message.GetProperty("content");
        return content.ValueKind switch
        {
            JsonValueKind.String => content.GetString() ?? string.Empty,
            JsonValueKind.Array => string.Join(
                "",
                content.EnumerateArray()
                    .Where(item => item.TryGetProperty("text", out _))
                    .Select(item => item.GetProperty("text").GetString() ?? string.Empty)),
            _ => throw new InvalidOperationException("AI response returned an unsupported content shape."),
        };
    }

    private static AiAssistantResultModel ParseAssistantResponse(string content)
    {
        var json = ExtractJsonObject(content);
        using var document = JsonDocument.Parse(json);
        var root = document.RootElement;

        return new AiAssistantResultModel
        {
            Answer = root.TryGetProperty("answer", out var answer) ? answer.GetString() ?? string.Empty : string.Empty,
            Command = root.TryGetProperty("command", out var command) ? command.GetString() ?? string.Empty : string.Empty,
            Risk = root.TryGetProperty("risk", out var risk) ? risk.GetString() ?? string.Empty : string.Empty,
            RunRecommended =
                root.TryGetProperty("runRecommended", out var runRecommended) &&
                runRecommended.ValueKind == JsonValueKind.True,
        };
    }

    private static string ExtractJsonObject(string text)
    {
        var trimmed = text.Trim();
        if (trimmed.StartsWith('{') && trimmed.EndsWith('}'))
        {
            return trimmed;
        }

        var start = trimmed.IndexOf('{');
        var end = trimmed.LastIndexOf('}');
        if (start >= 0 && end > start)
        {
            return trimmed[start..(end + 1)];
        }

        throw new InvalidOperationException("AI response did not return JSON.");
    }

    private static string ReadError(string payload, System.Net.HttpStatusCode statusCode)
    {
        if (!string.IsNullOrWhiteSpace(payload))
        {
            try
            {
                using var document = JsonDocument.Parse(payload);
                if (document.RootElement.TryGetProperty("error", out var error))
                {
                    if (error.ValueKind == JsonValueKind.String)
                    {
                        return error.GetString() ?? $"AI request failed with HTTP {(int)statusCode}.";
                    }

                    if (error.TryGetProperty("message", out var message))
                    {
                        return message.GetString() ?? $"AI request failed with HTTP {(int)statusCode}.";
                    }
                }
            }
            catch
            {
            }
        }

        return $"AI request failed with HTTP {(int)statusCode}.";
    }
}
