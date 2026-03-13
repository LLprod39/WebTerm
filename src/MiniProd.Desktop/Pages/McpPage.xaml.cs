using Microsoft.UI.Xaml.Controls;
using MiniProd.Desktop.ViewModels;

namespace MiniProd.Desktop.Pages;

public sealed partial class McpPage : Page
{
    public McpPage()
    {
        InitializeComponent();
        ViewModel = new McpViewModel();
        McpServersList.ItemsSource = ViewModel.Servers;
        McpServersList.SelectedItem = ViewModel.SelectedServer;
        UpdateSelectedServer(ViewModel.SelectedServer);
    }

    public McpViewModel ViewModel { get; }

    private void OnServerSelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        _ = sender;
        _ = e;
        ViewModel.SelectedServer = McpServersList.SelectedItem as McpServerModel;
        UpdateSelectedServer(ViewModel.SelectedServer);
    }

    private void UpdateSelectedServer(McpServerModel? server)
    {
        if (server is null)
        {
            McpServerNameText.Text = "No MCP server selected";
            McpTransportText.Text = string.Empty;
            McpHealthText.Text = string.Empty;
            return;
        }

        McpServerNameText.Text = server.Name;
        McpTransportText.Text = $"Transport: {server.Transport}";
        McpHealthText.Text = server.LastTestOk ? "Last test: healthy" : "Last test: requires attention";
    }
}
