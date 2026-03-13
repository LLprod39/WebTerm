using CommunityToolkit.Mvvm.ComponentModel;

namespace MiniProd.Desktop.ViewModels;

public sealed class McpViewModel : ObservableObject
{
    private McpServerModel? _selectedServer;

    public McpViewModel()
    {
        Servers = new ObservableCollection<McpServerModel>
        {
            new() { Id = 1, Name = "github", Transport = "stdio", Description = "GitHub tools", LastTestOk = true },
            new() { Id = 2, Name = "keycloak", Transport = "sse", Description = "Keycloak admin tools", LastTestOk = false },
        };

        SelectedServer = Servers.FirstOrDefault();
    }

    public ObservableCollection<McpServerModel> Servers { get; }

    public McpServerModel? SelectedServer
    {
        get => _selectedServer;
        set => SetProperty(ref _selectedServer, value);
    }
}
