using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace MiniProd.Desktop.Services;

public sealed class DesktopApiClient
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web)
    {
        PropertyNameCaseInsensitive = true,
    };

    private readonly HttpClient _httpClient = new();
    private readonly SettingsService _settingsService;

    public DesktopApiClient(SettingsService settingsService)
    {
        _settingsService = settingsService;
        SetBaseUri(settingsService.Current.BackendBaseUrl);
    }

    public void SetBaseUri(string baseUrl)
    {
        if (Uri.TryCreate(baseUrl, UriKind.Absolute, out var uri))
        {
            _httpClient.BaseAddress = uri;
        }
    }

    public async Task<DesktopSessionModel?> SignInAsync(string username, string password, CancellationToken cancellationToken = default)
    {
        EnsureBaseUri();

        var response = await SendAsync<LoginResponse>(
            HttpMethod.Post,
            "/api/desktop/v1/auth/login/",
            new { username, password, device_name = "MiniProd Desktop" },
            cancellationToken);

        if (response.Session is null || string.IsNullOrWhiteSpace(response.Session.AccessToken))
        {
            return null;
        }

        return new DesktopSessionModel
        {
            AccessToken = response.Session.AccessToken,
            RefreshToken = response.Session.RefreshToken,
            Username = response.User?.Username ?? username,
        };
    }

    public void SetAccessToken(string accessToken)
    {
        _httpClient.DefaultRequestHeaders.Authorization = string.IsNullOrWhiteSpace(accessToken)
            ? null
            : new AuthenticationHeaderValue("Bearer", accessToken);
    }

    public async Task<IReadOnlyList<ServerSummaryModel>> GetServersAsync(CancellationToken cancellationToken = default)
    {
        EnsureBaseUri();
        var response = await SendAsync<ServerListResponse>(HttpMethod.Get, "/api/desktop/v1/servers/", null, cancellationToken);
        return response.Items ?? [];
    }

    public async Task<ServerDetailModel> CreateServerAsync(ServerDraftModel draft, CancellationToken cancellationToken = default)
    {
        EnsureBaseUri();
        var response = await SendAsync<ServerDetailResponse>(
            HttpMethod.Post,
            "/api/desktop/v1/servers/",
            BuildServerPayload(draft, isUpdate: false),
            cancellationToken);
        return response.Item ?? throw new InvalidOperationException("Desktop API returned an empty server payload.");
    }

    public async Task<ServerDetailModel> UpdateServerAsync(ServerDraftModel draft, CancellationToken cancellationToken = default)
    {
        EnsureBaseUri();
        if (draft.Id is null)
        {
            throw new InvalidOperationException("Server ID is required for update.");
        }

        var response = await SendAsync<ServerDetailResponse>(
            HttpMethod.Put,
            $"/api/desktop/v1/servers/{draft.Id}/",
            BuildServerPayload(draft, isUpdate: true),
            cancellationToken);
        return response.Item ?? throw new InvalidOperationException("Desktop API returned an empty server payload.");
    }

    public async Task<ServerDetailModel> GetServerDetailAsync(int serverId, CancellationToken cancellationToken = default)
    {
        EnsureBaseUri();
        var response = await SendAsync<ServerDetailResponse>(
            HttpMethod.Get,
            $"/api/desktop/v1/servers/{serverId}/",
            null,
            cancellationToken);
        return response.Item ?? throw new InvalidOperationException("Desktop API returned an empty server payload.");
    }

    public async Task<TerminalTicketModel> CreateTerminalTicketAsync(int serverId, CancellationToken cancellationToken = default)
    {
        EnsureBaseUri();
        var response = await SendAsync<TerminalTicketResponse>(
            HttpMethod.Post,
            "/api/desktop/v1/terminal/ws-ticket/",
            new { server_id = serverId },
            cancellationToken);
        return response.Terminal ?? throw new InvalidOperationException("Desktop API returned an empty terminal ticket.");
    }

    public string CurrentBaseUrl =>
        _httpClient.BaseAddress?.ToString().TrimEnd('/') ?? _settingsService.Current.BackendBaseUrl.TrimEnd('/');

    private async Task<TResponse> SendAsync<TResponse>(
        HttpMethod method,
        string path,
        object? payload,
        CancellationToken cancellationToken)
    {
        using var request = new HttpRequestMessage(method, path);
        if (payload is not null)
        {
            var json = JsonSerializer.Serialize(payload, JsonOptions);
            request.Content = new StringContent(json, Encoding.UTF8, "application/json");
        }

        using var response = await _httpClient.SendAsync(request, cancellationToken);
        if (!response.IsSuccessStatusCode)
        {
            throw new InvalidOperationException(await ReadErrorAsync(response, cancellationToken));
        }

        await using var stream = await response.Content.ReadAsStreamAsync(cancellationToken);
        var model = await JsonSerializer.DeserializeAsync<TResponse>(stream, JsonOptions, cancellationToken);
        return model ?? throw new InvalidOperationException("Desktop API returned an empty response.");
    }

    private Dictionary<string, object?> BuildServerPayload(ServerDraftModel draft, bool isUpdate)
    {
        var payload = new Dictionary<string, object?>
        {
            ["name"] = draft.Name.Trim(),
            ["host"] = draft.Host.Trim(),
            ["port"] = draft.Port,
            ["username"] = draft.Username.Trim(),
            ["server_type"] = draft.ServerType.Trim().ToLowerInvariant(),
            ["auth_method"] = draft.AuthMethod.Trim().ToLowerInvariant(),
            ["key_path"] = draft.KeyPath.Trim(),
            ["notes"] = draft.Notes.Trim(),
        };

        if (!isUpdate || !string.IsNullOrWhiteSpace(draft.Password))
        {
            payload["password"] = draft.Password;
        }

        return payload;
    }

    private void EnsureBaseUri()
    {
        if (_httpClient.BaseAddress is null)
        {
            throw new InvalidOperationException("Backend base URL is not configured.");
        }
    }

    private static async Task<string> ReadErrorAsync(HttpResponseMessage response, CancellationToken cancellationToken)
    {
        try
        {
            await using var stream = await response.Content.ReadAsStreamAsync(cancellationToken);
            var error = await JsonSerializer.DeserializeAsync<ApiErrorResponse>(stream, JsonOptions, cancellationToken);
            if (!string.IsNullOrWhiteSpace(error?.Error?.Message))
            {
                return error.Error.Message;
            }
        }
        catch
        {
            // Ignore payload parse issues and fall back to status code.
        }

        return $"Desktop API request failed with HTTP {(int)response.StatusCode}.";
    }

    private sealed class ApiErrorResponse
    {
        public ApiErrorBody? Error { get; init; }
    }

    private sealed class ApiErrorBody
    {
        public string Message { get; init; } = string.Empty;
    }

    private sealed class DesktopSessionEnvelope
    {
        [JsonPropertyName("access_token")]
        public string AccessToken { get; init; } = string.Empty;

        [JsonPropertyName("refresh_token")]
        public string RefreshToken { get; init; } = string.Empty;
    }

    private sealed class DesktopUserEnvelope
    {
        public string Username { get; init; } = string.Empty;
    }

    private sealed class LoginResponse
    {
        public DesktopUserEnvelope? User { get; init; }

        public DesktopSessionEnvelope? Session { get; init; }
    }

    private sealed class ServerListResponse
    {
        public List<ServerSummaryModel>? Items { get; init; }
    }

    private sealed class ServerDetailResponse
    {
        public ServerDetailModel? Item { get; init; }
    }

    private sealed class TerminalTicketResponse
    {
        public TerminalTicketModel? Terminal { get; init; }
    }
}
