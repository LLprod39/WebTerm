using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using MiniProd.Desktop.ViewModels;

namespace MiniProd.Desktop.Pages;

public sealed partial class SettingsPage : Page
{
    private readonly Services.AppServices? _services;

    public SettingsPage()
    {
        InitializeComponent();
        _services = App.TryGetServices();
        ViewModel = new SettingsViewModel(_services?.Settings ?? new Services.SettingsService(new Services.ProtectedSecretService()));
        ThemeSelector.SelectedItem = ViewModel.Theme;
        DiagnosticsToggle.IsOn = ViewModel.DiagnosticsEnabled;
        AiEndpointInput.Text = ViewModel.AiEndpoint;
        AiModelInput.Text = ViewModel.AiModel;
        AiApiKeyInput.Password = ViewModel.AiApiKey;
        AutoApproveToggle.IsOn = ViewModel.AutoApproveAiCommands;
        AiSystemPromptInput.Text = ViewModel.AiSystemPrompt;
        SettingsStatusText.Text = ViewModel.SaveStatus;
    }

    public SettingsViewModel ViewModel { get; }

    private async void OnSaveClicked(object sender, RoutedEventArgs e)
    {
        _ = sender;
        _ = e;
        ViewModel.Theme = ThemeSelector.SelectedItem as string ?? "System";
        ViewModel.DiagnosticsEnabled = DiagnosticsToggle.IsOn;
        ViewModel.AiEndpoint = AiEndpointInput.Text;
        ViewModel.AiModel = AiModelInput.Text;
        ViewModel.AiApiKey = AiApiKeyInput.Password;
        ViewModel.AutoApproveAiCommands = AutoApproveToggle.IsOn;
        ViewModel.AiSystemPrompt = AiSystemPromptInput.Text;
        await ViewModel.SaveAsync();
        App.ApplyRequestedTheme(App.TryGetMainWindow());
        SettingsStatusText.Text = ViewModel.SaveStatus;
    }

    private void OnApiKeyChanged(object sender, RoutedEventArgs e)
    {
        if (sender is PasswordBox passwordBox)
        {
            ViewModel.AiApiKey = passwordBox.Password;
        }
    }
}
