using System.Text.Json;

namespace MiniProd.Desktop.Services;

public sealed class SettingsService
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true,
    };

    private readonly string _settingsPath;
    private readonly ProtectedSecretService _secretService;

    public SettingsService(ProtectedSecretService secretService)
    {
        _secretService = secretService;
        var appData = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "MiniProd",
            "Desktop");
        Directory.CreateDirectory(appData);
        _settingsPath = Path.Combine(appData, "settings.json");
        Current = new DesktopSettings();
    }

    public DesktopSettings Current { get; private set; }

    public async Task LoadAsync()
    {
        if (!File.Exists(_settingsPath))
        {
            return;
        }

        await using var stream = File.OpenRead(_settingsPath);
        var envelope = await JsonSerializer.DeserializeAsync<DesktopSettingsEnvelope>(stream, JsonOptions);
        if (envelope is not null)
        {
            Current = envelope.ToSettings(_secretService);
        }
    }

    public async Task SaveAsync(DesktopSettings settings)
    {
        Current = settings;
        await using var stream = File.Create(_settingsPath);
        await JsonSerializer.SerializeAsync(stream, DesktopSettingsEnvelope.FromSettings(settings, _secretService), JsonOptions);
    }

    private sealed class DesktopSettingsEnvelope
    {
        public string Theme { get; set; } = "System";

        public bool DiagnosticsEnabled { get; set; } = true;

        public string AiEndpoint { get; set; } = string.Empty;

        public string AiModel { get; set; } = string.Empty;

        public string ProtectedAiApiKey { get; set; } = string.Empty;

        public string AiSystemPrompt { get; set; } = string.Empty;

        public bool AutoApproveAiCommands { get; set; }

        public DesktopSettings ToSettings(ProtectedSecretService secretService)
        {
            var defaults = new DesktopSettings();
            return new DesktopSettings
            {
                Theme = string.IsNullOrWhiteSpace(Theme) ? defaults.Theme : Theme,
                DiagnosticsEnabled = DiagnosticsEnabled,
                AiEndpoint = string.IsNullOrWhiteSpace(AiEndpoint) ? defaults.AiEndpoint : AiEndpoint,
                AiModel = string.IsNullOrWhiteSpace(AiModel) ? defaults.AiModel : AiModel,
                AiApiKey = secretService.Unprotect(ProtectedAiApiKey),
                AiSystemPrompt = string.IsNullOrWhiteSpace(AiSystemPrompt) ? defaults.AiSystemPrompt : AiSystemPrompt,
                AutoApproveAiCommands = AutoApproveAiCommands,
            };
        }

        public static DesktopSettingsEnvelope FromSettings(DesktopSettings settings, ProtectedSecretService secretService)
        {
            return new DesktopSettingsEnvelope
            {
                Theme = settings.Theme,
                DiagnosticsEnabled = settings.DiagnosticsEnabled,
                AiEndpoint = settings.AiEndpoint,
                AiModel = settings.AiModel,
                ProtectedAiApiKey = secretService.Protect(settings.AiApiKey),
                AiSystemPrompt = settings.AiSystemPrompt,
                AutoApproveAiCommands = settings.AutoApproveAiCommands,
            };
        }
    }
}
