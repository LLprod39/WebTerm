using System.Text.Json;

namespace MiniProd.Desktop.Services;

public sealed class LocalServerStoreService
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true,
    };

    private readonly SemaphoreSlim _gate = new(1, 1);
    private readonly ProtectedSecretService _secretService;
    private readonly string _storePath;
    private ServerStoreEnvelope _store = new();
    private bool _loaded;

    public LocalServerStoreService(ProtectedSecretService secretService)
    {
        _secretService = secretService;
        var appData = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "MiniProd",
            "Desktop");
        Directory.CreateDirectory(appData);
        _storePath = Path.Combine(appData, "servers.json");
    }

    public event EventHandler? ServersChanged;

    public async Task LoadAsync()
    {
        await EnsureLoadedAsync();
    }

    public async Task<IReadOnlyList<ServerSummaryModel>> GetSummariesAsync()
    {
        await EnsureLoadedAsync();
        await _gate.WaitAsync();
        try
        {
            return _store.Servers
                .OrderBy(server => server.Name, StringComparer.OrdinalIgnoreCase)
                .Select(server => server.ToSummary())
                .ToList();
        }
        finally
        {
            _gate.Release();
        }
    }

    public async Task<StoredServerModel?> GetByIdAsync(int id)
    {
        await EnsureLoadedAsync();
        await _gate.WaitAsync();
        try
        {
            return _store.Servers.FirstOrDefault(server => server.Id == id)?.Clone();
        }
        finally
        {
            _gate.Release();
        }
    }

    public async Task<ServerDraftModel?> GetDraftAsync(int id)
    {
        await EnsureLoadedAsync();
        await _gate.WaitAsync();
        try
        {
            return _store.Servers.FirstOrDefault(server => server.Id == id)?.ToDraft();
        }
        finally
        {
            _gate.Release();
        }
    }

    public async Task<ServerSummaryModel> SaveAsync(ServerDraftModel draft)
    {
        ValidateDraft(draft);
        await EnsureLoadedAsync();

        ServerSummaryModel summary;

        await _gate.WaitAsync();
        try
        {
            var isNew = draft.Id is null;
            StoredServerModel record;

            if (isNew)
            {
                record = new StoredServerModel
                {
                    Id = _store.NextServerId++,
                };
                _store.Servers.Add(record);
            }
            else
            {
                record = _store.Servers.FirstOrDefault(server => server.Id == draft.Id)
                    ?? throw new InvalidOperationException("Selected server was not found.");
            }

            record.Name = draft.Name.Trim();
            record.Host = draft.Host.Trim();
            record.Port = draft.Port;
            record.Username = draft.Username.Trim();
            record.ServerType = "ssh";
            record.AuthMethod = NormalizeAuthMethod(draft.AuthMethod);
            record.KeyPath = draft.KeyPath.Trim();
            record.Notes = draft.Notes.Trim();

            if (!string.IsNullOrWhiteSpace(draft.Password))
            {
                record.ProtectedSecret = _secretService.Protect(draft.Password);
            }

            summary = record.ToSummary();
            await SaveUnsafeAsync();
        }
        finally
        {
            _gate.Release();
        }

        ServersChanged?.Invoke(this, EventArgs.Empty);
        return summary;
    }

    public async Task DeleteAsync(int id)
    {
        await EnsureLoadedAsync();
        var changed = false;

        await _gate.WaitAsync();
        try
        {
            var existing = _store.Servers.FirstOrDefault(server => server.Id == id);
            if (existing is not null)
            {
                _store.Servers.Remove(existing);
                await SaveUnsafeAsync();
                changed = true;
            }
        }
        finally
        {
            _gate.Release();
        }

        if (changed)
        {
            ServersChanged?.Invoke(this, EventArgs.Empty);
        }
    }

    public async Task MarkConnectionStateAsync(int id, bool succeeded, string? errorMessage = null)
    {
        await EnsureLoadedAsync();
        var changed = false;

        await _gate.WaitAsync();
        try
        {
            var existing = _store.Servers.FirstOrDefault(server => server.Id == id);
            if (existing is null)
            {
                return;
            }

            if (succeeded)
            {
                existing.LastConnectedAt = DateTimeOffset.Now;
                existing.LastError = string.Empty;
            }
            else
            {
                existing.LastError = errorMessage?.Trim() ?? "Connection failed.";
            }

            await SaveUnsafeAsync();
            changed = true;
        }
        finally
        {
            _gate.Release();
        }

        if (changed)
        {
            ServersChanged?.Invoke(this, EventArgs.Empty);
        }
    }

    public string RevealSecret(StoredServerModel server)
    {
        return _secretService.Unprotect(server.ProtectedSecret);
    }

    private async Task EnsureLoadedAsync()
    {
        if (_loaded)
        {
            return;
        }

        await _gate.WaitAsync();
        try
        {
            if (_loaded)
            {
                return;
            }

            if (File.Exists(_storePath))
            {
                await using var stream = File.OpenRead(_storePath);
                var envelope = await JsonSerializer.DeserializeAsync<ServerStoreEnvelope>(stream, JsonOptions);
                if (envelope is not null)
                {
                    _store = envelope;
                }
            }

            _loaded = true;
        }
        finally
        {
            _gate.Release();
        }
    }

    private async Task SaveUnsafeAsync()
    {
        await using var stream = File.Create(_storePath);
        await JsonSerializer.SerializeAsync(stream, _store, JsonOptions);
    }

    private static void ValidateDraft(ServerDraftModel draft)
    {
        if (string.IsNullOrWhiteSpace(draft.Name))
        {
            throw new InvalidOperationException("Server name is required.");
        }

        if (string.IsNullOrWhiteSpace(draft.Host))
        {
            throw new InvalidOperationException("Host is required.");
        }

        if (string.IsNullOrWhiteSpace(draft.Username))
        {
            throw new InvalidOperationException("Username is required.");
        }

        if (draft.Port is < 1 or > 65535)
        {
            throw new InvalidOperationException("Port must be between 1 and 65535.");
        }

        if (NormalizeAuthMethod(draft.AuthMethod) == "key" && string.IsNullOrWhiteSpace(draft.KeyPath))
        {
            throw new InvalidOperationException("Key path is required for key-based authentication.");
        }
    }

    private static string NormalizeAuthMethod(string authMethod)
    {
        return string.Equals(authMethod, "key", StringComparison.OrdinalIgnoreCase) ? "key" : "password";
    }

    private sealed class ServerStoreEnvelope
    {
        public int NextServerId { get; set; } = 1;

        public List<StoredServerModel> Servers { get; set; } = [];
    }
}
