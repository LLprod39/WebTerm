using CommunityToolkit.Mvvm.ComponentModel;

namespace MiniProd.Desktop.ViewModels;

public sealed class ServersViewModel : ObservableObject
{
    private ServerSummaryModel? _selectedServer;
    private string _searchText = string.Empty;

    public ServersViewModel()
    {
        Servers = new ObservableCollection<ServerSummaryModel>
        {
            new() { Id = 1, Name = "prod-web-01", Host = "10.0.10.21", Port = 22, Username = "deploy", Status = "online", GroupName = "Production", ServerType = "ssh" },
            new() { Id = 2, Name = "stage-api-01", Host = "10.0.20.18", Port = 22, Username = "ops", Status = "unknown", GroupName = "Staging", ServerType = "ssh" },
        };

        SelectedServer = Servers.FirstOrDefault();
    }

    public ObservableCollection<ServerSummaryModel> Servers { get; }

    public ServerSummaryModel? SelectedServer
    {
        get => _selectedServer;
        set => SetProperty(ref _selectedServer, value);
    }

    public string SearchText
    {
        get => _searchText;
        set => SetProperty(ref _searchText, value);
    }
}
