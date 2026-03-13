using CommunityToolkit.Mvvm.ComponentModel;
using MiniProd.Desktop.Services;

namespace MiniProd.Desktop.ViewModels;

public sealed class TerminalViewModel : ObservableObject
{
    private string _selectedServer = string.Empty;

    public TerminalViewModel(SettingsService settingsService, SessionService sessionService)
    {
        Session = new TerminalSessionModel
        {
            BackendBaseUrl = settingsService.Current.BackendBaseUrl,
            AccessToken = sessionService.Current.AccessToken,
            Theme = settingsService.Current.Theme,
            ActiveServerName = "prod-web-01",
        };

        AvailableServers = new ObservableCollection<string>
        {
            "prod-web-01",
            "stage-api-01",
            "dev-tools-01",
        };

        SelectedServer = AvailableServers.FirstOrDefault() ?? "prod-web-01";
    }

    public ObservableCollection<string> AvailableServers { get; }

    public TerminalSessionModel Session { get; }

    public string SelectedServer
    {
        get => _selectedServer;
        set
        {
            if (SetProperty(ref _selectedServer, value))
            {
                Session.ActiveServerName = value;
            }
        }
    }
}
