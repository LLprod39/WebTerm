using Microsoft.UI.Xaml;
using MiniProd.Desktop.Services;

namespace MiniProd.Desktop.Pages;

public sealed partial class ServersPage : Page
{
    private readonly AppServices _services;
    private readonly LocalServerStoreService _serverStore;
    private readonly NavigationService _navigation;
    private readonly WorkspaceStateService _workspace;
    private IReadOnlyList<ServerSummaryModel> _allServers = [];
    private int? _selectedServerId;

    public ServersPage()
    {
        InitializeComponent();
        _services = App.TryGetServices() ?? new AppServices();
        _serverStore = _services.Servers;
        _navigation = _services.Navigation;
        _workspace = _services.Workspace;
        Loaded += OnLoaded;
        Unloaded += OnUnloaded;
        PortInput.Value = 22;
        AuthMethodSelector.SelectedItem = "password";
        StatusFilterSelector.SelectedItem = "all";
        UpdateAuthFields();
        ResetForm();
    }

    private async void OnLoaded(object sender, RoutedEventArgs e)
    {
        _ = sender;
        _ = e;
        _serverStore.ServersChanged += OnServersChanged;
        await RefreshAsync();
    }

    private void OnUnloaded(object sender, RoutedEventArgs e)
    {
        _ = sender;
        _ = e;
        _serverStore.ServersChanged -= OnServersChanged;
    }

    private void OnServersChanged(object? sender, EventArgs e)
    {
        _ = sender;
        DispatcherQueue.TryEnqueue(() => _ = RefreshAsync());
    }

    private async void OnServerSelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        _ = sender;
        _ = e;

        if (ServersList.SelectedItem is not ServerSummaryModel server)
        {
            _selectedServerId = null;
            ResetForm();
            return;
        }

        _selectedServerId = server.Id;
        _workspace.SetSelectedServer(server);
        await LoadDraftAsync(server.Id);
    }

    private void OnNewClicked(object sender, RoutedEventArgs e)
    {
        _ = sender;
        _ = e;
        ServersList.SelectedItem = null;
        _selectedServerId = null;
        ResetForm();
    }

    private async void OnSaveClicked(object sender, RoutedEventArgs e)
    {
        _ = sender;
        _ = e;

        try
        {
            var summary = await _serverStore.SaveAsync(BuildDraftFromForm());
            _selectedServerId = summary.Id;
            ServerFormStatusText.Text = $"Saved {summary.Name} locally.";
            _workspace.SetSelectedServer(summary);
            await RefreshAsync();
        }
        catch (Exception ex)
        {
            ServerFormStatusText.Text = ex.Message;
        }
    }

    private async void OnDeleteClicked(object sender, RoutedEventArgs e)
    {
        _ = sender;
        _ = e;

        if (_selectedServerId is null)
        {
            ServerFormStatusText.Text = "Select a server before deleting it.";
            return;
        }

        await _serverStore.DeleteAsync(_selectedServerId.Value);
        _selectedServerId = null;
        ResetForm();
        await RefreshAsync();
        ServerFormStatusText.Text = "Server removed from local storage.";
    }

    private void OnOpenTerminalClicked(object sender, RoutedEventArgs e)
    {
        _ = sender;
        _ = e;

        var selected = ServersList.SelectedItem as ServerSummaryModel;
        if (selected is null)
        {
            ServerFormStatusText.Text = "Select a server first.";
            return;
        }

        _workspace.SetSelectedServer(selected);
        _navigation.Navigate(typeof(TerminalPage));
    }

    private void OnAuthMethodChanged(object sender, SelectionChangedEventArgs e)
    {
        _ = sender;
        _ = e;
        UpdateAuthFields();
    }

    private async Task RefreshAsync()
    {
        _allServers = await _serverStore.GetSummariesAsync();
        UpdateMetrics(_allServers);
        var visibleServers = ApplyFilters(_allServers);
        ServersList.ItemsSource = visibleServers;

        if (_selectedServerId is not null)
        {
            var selected = visibleServers.FirstOrDefault(server => server.Id == _selectedServerId.Value);
            if (selected is not null)
            {
                ServersList.SelectedItem = selected;
                return;
            }
        }

        if (visibleServers.Count > 0)
        {
            ServersList.SelectedItem = visibleServers[0];
            return;
        }

        ResetForm();
    }

    private void OnSearchChanged(object sender, TextChangedEventArgs e)
    {
        _ = sender;
        _ = e;
        ApplyFiltersToList();
    }

    private void OnStatusFilterChanged(object sender, SelectionChangedEventArgs e)
    {
        _ = sender;
        _ = e;
        ApplyFiltersToList();
    }

    private async Task LoadDraftAsync(int serverId)
    {
        var draft = await _serverStore.GetDraftAsync(serverId);
        if (draft is null)
        {
            ResetForm();
            return;
        }

        FormModeText.Text = $"Edit {draft.Name}";
        NameInput.Text = draft.Name;
        HostInput.Text = draft.Host;
        PortInput.Value = draft.Port;
        UsernameInput.Text = draft.Username;
        AuthMethodSelector.SelectedItem = draft.AuthMethod;
        PasswordInput.Password = string.Empty;
        KeyPathInput.Text = draft.KeyPath;
        NotesInput.Text = draft.Notes;
        SecretStatusText.Text = draft.HasSavedSecret
            ? "Saved secret exists. Leave the password field blank to keep it."
            : "No secret is saved yet.";
        UpdateAuthFields();
        ServerFormStatusText.Text = "Ready.";
    }

    private ServerDraftModel BuildDraftFromForm()
    {
        return new ServerDraftModel
        {
            Id = _selectedServerId,
            Name = NameInput.Text,
            Host = HostInput.Text,
            Port = (int)(PortInput.Value > 0 ? PortInput.Value : 22),
            Username = UsernameInput.Text,
            AuthMethod = AuthMethodSelector.SelectedItem as string ?? "password",
            Password = PasswordInput.Password,
            KeyPath = KeyPathInput.Text,
            Notes = NotesInput.Text,
        };
    }

    private void ResetForm()
    {
        FormModeText.Text = "New server";
        NameInput.Text = string.Empty;
        HostInput.Text = string.Empty;
        PortInput.Value = 22;
        UsernameInput.Text = "root";
        AuthMethodSelector.SelectedItem = "password";
        PasswordInput.Password = string.Empty;
        KeyPathInput.Text = string.Empty;
        NotesInput.Text = string.Empty;
        SecretStatusText.Text = "Add a server and save it locally. Passwords stay encrypted under your Windows account.";
        ServerFormStatusText.Text = "Ready.";
        UpdateAuthFields();
    }

    private void UpdateAuthFields()
    {
        var authMethod = AuthMethodSelector.SelectedItem as string ?? "password";
        var keyMode = authMethod == "key";
        KeyPathInput.Visibility = keyMode ? Visibility.Visible : Visibility.Collapsed;
        PasswordInput.Header = keyMode ? "Key passphrase (optional)" : "Password";
    }

    private void ApplyFiltersToList()
    {
        var filtered = ApplyFilters(_allServers);
        ServersList.ItemsSource = filtered;

        if (_selectedServerId is not null)
        {
            ServersList.SelectedItem = filtered.FirstOrDefault(server => server.Id == _selectedServerId.Value);
        }
    }

    private List<ServerSummaryModel> ApplyFilters(IReadOnlyList<ServerSummaryModel> servers)
    {
        var search = SearchInput.Text.Trim();
        var statusFilter = (StatusFilterSelector.SelectedItem as string ?? "all").Trim().ToLowerInvariant();

        return servers
            .Where(server =>
                string.IsNullOrWhiteSpace(search) ||
                server.Name.Contains(search, StringComparison.OrdinalIgnoreCase) ||
                server.Host.Contains(search, StringComparison.OrdinalIgnoreCase) ||
                server.Username.Contains(search, StringComparison.OrdinalIgnoreCase))
            .Where(server => statusFilter == "all" || string.Equals(server.Status, statusFilter, StringComparison.OrdinalIgnoreCase))
            .ToList();
    }

    private void UpdateMetrics(IReadOnlyList<ServerSummaryModel> servers)
    {
        TotalServersText.Text = servers.Count.ToString();
        ReadyServersText.Text = servers.Count(server => server.Status == "ready").ToString();
        ErrorServersText.Text = servers.Count(server => server.Status == "error").ToString();
    }
}
