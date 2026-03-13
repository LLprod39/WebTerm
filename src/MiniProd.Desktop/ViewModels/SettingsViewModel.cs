using CommunityToolkit.Mvvm.ComponentModel;
using MiniProd.Desktop.Services;

namespace MiniProd.Desktop.ViewModels;

public sealed class SettingsViewModel : ObservableObject
{
    private readonly SettingsService _settingsService;
    private string _theme = "System";
    private bool _diagnosticsEnabled = true;
    private string _aiEndpoint = string.Empty;
    private string _aiModel = string.Empty;
    private string _aiApiKey = string.Empty;
    private string _aiSystemPrompt = string.Empty;
    private bool _autoApproveAiCommands;
    private string _saveStatus = "Settings are stored locally per user profile.";

    public SettingsViewModel(SettingsService settingsService)
    {
        _settingsService = settingsService;
        Theme = settingsService.Current.Theme;
        DiagnosticsEnabled = settingsService.Current.DiagnosticsEnabled;
        AiEndpoint = settingsService.Current.AiEndpoint;
        AiModel = settingsService.Current.AiModel;
        AiApiKey = settingsService.Current.AiApiKey;
        AiSystemPrompt = settingsService.Current.AiSystemPrompt;
        AutoApproveAiCommands = settingsService.Current.AutoApproveAiCommands;
    }

    public string Theme
    {
        get => _theme;
        set => SetProperty(ref _theme, value);
    }

    public bool DiagnosticsEnabled
    {
        get => _diagnosticsEnabled;
        set => SetProperty(ref _diagnosticsEnabled, value);
    }

    public string AiEndpoint
    {
        get => _aiEndpoint;
        set => SetProperty(ref _aiEndpoint, value);
    }

    public string AiModel
    {
        get => _aiModel;
        set => SetProperty(ref _aiModel, value);
    }

    public string AiApiKey
    {
        get => _aiApiKey;
        set => SetProperty(ref _aiApiKey, value);
    }

    public string AiSystemPrompt
    {
        get => _aiSystemPrompt;
        set => SetProperty(ref _aiSystemPrompt, value);
    }

    public bool AutoApproveAiCommands
    {
        get => _autoApproveAiCommands;
        set => SetProperty(ref _autoApproveAiCommands, value);
    }

    public string SaveStatus
    {
        get => _saveStatus;
        set => SetProperty(ref _saveStatus, value);
    }

    public async Task SaveAsync()
    {
        await _settingsService.SaveAsync(new DesktopSettings
        {
            Theme = Theme,
            DiagnosticsEnabled = DiagnosticsEnabled,
            AiEndpoint = AiEndpoint,
            AiModel = AiModel,
            AiApiKey = AiApiKey,
            AiSystemPrompt = AiSystemPrompt,
            AutoApproveAiCommands = AutoApproveAiCommands,
        });

        SaveStatus = "Settings saved.";
    }
}
