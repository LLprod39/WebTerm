using System.Text.Json;
using Microsoft.UI.Xaml;
using Microsoft.Web.WebView2.Core;
using MiniProd.Desktop.Services;

namespace MiniProd.Desktop.Pages;

public sealed partial class TerminalPage : Page
{
    private readonly AppServices _services;
    private readonly SettingsService _settingsService;
    private readonly LocalServerStoreService _serverStore;
    private readonly SshTerminalService _terminalService;
    private readonly AiAssistantService _aiAssistant;
    private readonly WorkspaceStateService _workspace;
    private IReadOnlyList<ServerSummaryModel> _servers = [];
    private bool _webViewReady;

    public TerminalPage()
    {
        InitializeComponent();
        _services = App.TryGetServices() ?? new AppServices();
        _settingsService = _services.Settings;
        _serverStore = _services.Servers;
        _terminalService = _services.Terminal;
        _aiAssistant = _services.AiAssistant;
        _workspace = _services.Workspace;
        Loaded += OnLoaded;
        Unloaded += OnUnloaded;
    }

    private async void OnLoaded(object sender, RoutedEventArgs e)
    {
        _ = sender;
        _ = e;
        _serverStore.ServersChanged += OnServersChanged;
        _workspace.SelectedServerChanged += OnSelectedServerChanged;
        _terminalService.OutputReceived += OnTerminalOutputReceived;
        _terminalService.StatusChanged += OnTerminalStatusChanged;
        await LoadServersAsync();
        await InitializeWebViewAsync();
        UpdateStatus("Ready.");
    }

    private void OnUnloaded(object sender, RoutedEventArgs e)
    {
        _ = sender;
        _ = e;
        _serverStore.ServersChanged -= OnServersChanged;
        _workspace.SelectedServerChanged -= OnSelectedServerChanged;
        _terminalService.OutputReceived -= OnTerminalOutputReceived;
        _terminalService.StatusChanged -= OnTerminalStatusChanged;
    }

    private void OnServersChanged(object? sender, EventArgs e)
    {
        _ = sender;
        DispatcherQueue.TryEnqueue(() => _ = LoadServersAsync());
    }

    private void OnSelectedServerChanged(object? sender, EventArgs e)
    {
        _ = sender;
        DispatcherQueue.TryEnqueue(PostBootstrap);
    }

    private async Task LoadServersAsync()
    {
        _servers = await _serverStore.GetSummariesAsync();
        if (_servers.Count == 0)
        {
            PostBootstrap();
            UpdateStatus("No saved servers. Add one on the Servers page.");
            return;
        }

        var targetId = _workspace.SelectedServerId ?? _terminalService.CurrentServerId ?? _servers[0].Id;
        var selected = _servers.FirstOrDefault(server => server.Id == targetId) ?? _servers[0];
        _workspace.SetSelectedServer(selected);
        PostBootstrap();
    }

    private async Task InitializeWebViewAsync()
    {
        await TerminalWebView.EnsureCoreWebView2Async();
        var assetPath = Path.Combine(AppContext.BaseDirectory, "Assets", "TerminalBridge");
        TerminalWebView.CoreWebView2.SetVirtualHostNameToFolderMapping(
            "desktop.miniprod.local",
            assetPath,
            CoreWebView2HostResourceAccessKind.Allow);
        TerminalWebView.CoreWebView2.WebMessageReceived -= OnWebMessageReceived;
        TerminalWebView.CoreWebView2.WebMessageReceived += OnWebMessageReceived;
        TerminalWebView.NavigationCompleted -= OnWebViewNavigationCompleted;
        TerminalWebView.NavigationCompleted += OnWebViewNavigationCompleted;
        TerminalWebView.Source = new Uri("https://desktop.miniprod.local/index.html");
    }

    private void OnWebViewNavigationCompleted(WebView2 sender, CoreWebView2NavigationCompletedEventArgs args)
    {
        _ = sender;
        if (!args.IsSuccess)
        {
            UpdateStatus("Failed to load the terminal bridge UI.");
            return;
        }

        _webViewReady = true;
        PostBootstrap();
    }

    private async void OnWebMessageReceived(CoreWebView2 sender, CoreWebView2WebMessageReceivedEventArgs args)
    {
        _ = sender;

        using var document = JsonDocument.Parse(args.WebMessageAsJson);
        if (!document.RootElement.TryGetProperty("type", out var typeElement))
        {
            return;
        }

        var messageType = typeElement.GetString() ?? string.Empty;
        switch (messageType)
        {
            case "host-ready":
                PostBootstrap();
                break;
            case "select-server":
                HandleServerSelection(document.RootElement);
                break;
            case "connect":
                await ConnectSelectedServerAsync();
                break;
            case "disconnect":
                await DisconnectAsync();
                break;
            case "send-input":
                await HandleCommandInputAsync(document.RootElement);
                break;
            case "ask-ai":
                await HandleAiRequestAsync(document.RootElement);
                break;
            case "run-ai-command":
                await HandleAiCommandExecutionAsync(document.RootElement);
                break;
            case "interrupt":
                await _terminalService.SendInterruptAsync();
                break;
        }
    }

    private void HandleServerSelection(JsonElement root)
    {
        if (!root.TryGetProperty("serverId", out var idElement) || !idElement.TryGetInt32(out var serverId))
        {
            return;
        }

        var selected = _servers.FirstOrDefault(server => server.Id == serverId);
        if (selected is null)
        {
            return;
        }

        _workspace.SetSelectedServer(selected);
        UpdateStatus($"Selected {selected.Name}.");
        PostBootstrap();
    }

    private async Task HandleCommandInputAsync(JsonElement root)
    {
        var command = root.TryGetProperty("text", out var textElement) ? textElement.GetString() ?? string.Empty : string.Empty;
        if (string.IsNullOrWhiteSpace(command))
        {
            return;
        }

        if (!_terminalService.IsConnected)
        {
            await ConnectSelectedServerAsync();
        }

        await _terminalService.SendLineAsync(command);
    }

    private async Task HandleAiRequestAsync(JsonElement root)
    {
        var prompt = root.TryGetProperty("prompt", out var promptElement) ? promptElement.GetString() ?? string.Empty : string.Empty;
        var mode = root.TryGetProperty("mode", out var modeElement) ? modeElement.GetString() ?? "auto" : "auto";
        var selected = GetSelectedServerSummary();
        if (selected is null)
        {
            PostMessage(new { type = "ai-error", text = "Select a server first." });
            return;
        }

        try
        {
            UpdateStatus("AI is reading the current terminal transcript...");
            var result = await _aiAssistant.AskAsync(selected, _terminalService.GetTranscriptSnapshot(), prompt);
            PostMessage(new
            {
                type = "ai-response",
                answer = result.Answer,
                command = result.Command,
                risk = result.Risk,
                runRecommended = result.RunRecommended,
            });
            UpdateStatus(string.IsNullOrWhiteSpace(result.Command) ? "AI response ready." : "AI suggested a command.");

            var shouldAutoRun =
                !string.IsNullOrWhiteSpace(result.Command) &&
                (string.Equals(mode, "fast", StringComparison.OrdinalIgnoreCase) ||
                 (string.Equals(mode, "auto", StringComparison.OrdinalIgnoreCase) &&
                  _settingsService.Current.AutoApproveAiCommands &&
                  result.RunRecommended));

            if (shouldAutoRun)
            {
                await _terminalService.SendLineAsync(result.Command);
                PostMessage(new { type = "status", text = $"AI executed: {result.Command}", connected = _terminalService.IsConnected });
            }
        }
        catch (Exception ex)
        {
            PostMessage(new { type = "ai-error", text = ex.Message });
            UpdateStatus(ex.Message);
        }
    }

    private async Task HandleAiCommandExecutionAsync(JsonElement root)
    {
        var command = root.TryGetProperty("command", out var commandElement) ? commandElement.GetString() ?? string.Empty : string.Empty;
        if (string.IsNullOrWhiteSpace(command))
        {
            return;
        }

        if (!_terminalService.IsConnected)
        {
            await ConnectSelectedServerAsync();
        }

        await _terminalService.SendLineAsync(command);
        UpdateStatus($"Ran AI command: {command}");
    }

    private async Task ConnectSelectedServerAsync()
    {
        var selected = GetSelectedServerSummary();
        if (selected is null)
        {
            UpdateStatus("Select a saved server first.");
            return;
        }

        var storedServer = await _serverStore.GetByIdAsync(selected.Id);
        if (storedServer is null)
        {
            UpdateStatus("Selected server was not found.");
            return;
        }

        try
        {
            UpdateStatus($"Connecting to {selected.Name}...");
            PostMessage(new { type = "terminal-reset" });
            var secret = _serverStore.RevealSecret(storedServer);
            await _terminalService.ConnectAsync(storedServer, secret);
            await _serverStore.MarkConnectionStateAsync(selected.Id, succeeded: true);
            PostBootstrap();
            UpdateStatus($"Connected to {selected.Name}.");
        }
        catch (Exception ex)
        {
            await _serverStore.MarkConnectionStateAsync(selected.Id, succeeded: false, errorMessage: ex.Message);
            PostMessage(new { type = "error", text = ex.Message });
            UpdateStatus(ex.Message);
        }
    }

    private async Task DisconnectAsync()
    {
        await _terminalService.DisconnectAsync();
        PostMessage(new { type = "status", text = "Disconnected.", connected = false });
        PostBootstrap();
        UpdateStatus("Disconnected.");
    }

    private ServerSummaryModel? GetSelectedServerSummary()
    {
        var selectedId = _workspace.SelectedServerId ?? _terminalService.CurrentServerId;
        return _servers.FirstOrDefault(server => server.Id == selectedId) ?? _servers.FirstOrDefault();
    }

    private void OnTerminalOutputReceived(object? sender, string output)
    {
        _ = sender;
        DispatcherQueue.TryEnqueue(() => PostMessage(new { type = "terminal-output", text = output }));
    }

    private void OnTerminalStatusChanged(object? sender, string status)
    {
        _ = sender;
        DispatcherQueue.TryEnqueue(() =>
        {
            PostMessage(new { type = "status", text = status, connected = _terminalService.IsConnected });
            UpdateStatus(status);
        });
    }

    private void PostBootstrap()
    {
        var selected = GetSelectedServerSummary();
        var payload = new TerminalBridgePayload
        {
            Theme = _settingsService.Current.Theme,
            ServerId = selected?.Id ?? 0,
            ServerName = selected?.Name ?? "No server selected",
            SessionState = _terminalService.IsConnected ? "connected" : "disconnected",
            AiConfigured = _aiAssistant.IsConfigured,
            AutoApproveAiCommands = _settingsService.Current.AutoApproveAiCommands,
        };

        PostMessage(new
        {
            type = "bootstrap",
            theme = payload.Theme,
            serverId = payload.ServerId,
            serverName = payload.ServerName,
            serverAddress = selected?.AddressLabel ?? "Standalone SSH workspace",
            sessionState = payload.SessionState,
            aiConfigured = payload.AiConfigured,
            autoApproveAiCommands = payload.AutoApproveAiCommands,
            servers = _servers.Select(server => new
            {
                id = server.Id,
                name = server.Name,
                address = server.AddressLabel,
                status = server.Status,
                statusLabel = server.StatusLabel,
            }),
        });
    }

    private void PostMessage(object payload)
    {
        if (!_webViewReady || TerminalWebView.CoreWebView2 is null)
        {
            return;
        }

        TerminalWebView.CoreWebView2.PostWebMessageAsJson(JsonSerializer.Serialize(payload));
    }

    private void UpdateStatus(string message)
    {
        TerminalStatusText.Text = message;
    }
}
