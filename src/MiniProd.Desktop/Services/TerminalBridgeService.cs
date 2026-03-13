using Microsoft.UI.Xaml.Controls;
using Microsoft.Web.WebView2.Core;

namespace MiniProd.Desktop.Services;

public sealed class TerminalBridgeService
{
    private readonly SettingsService _settingsService;
    private readonly SessionService _sessionService;

    public TerminalBridgeService(SettingsService settingsService, SessionService sessionService)
    {
        _settingsService = settingsService;
        _sessionService = sessionService;
    }

    public async Task InitializeAsync(WebView2 webView, TerminalSessionModel sessionModel)
    {
        await webView.EnsureCoreWebView2Async();

        var bridgeDirectory = Path.Combine(AppContext.BaseDirectory, "Assets", "TerminalBridge");
        webView.CoreWebView2.SetVirtualHostNameToFolderMapping(
            "desktop.miniprod.local",
            bridgeDirectory,
            CoreWebView2HostResourceAccessKind.Allow);

        webView.CoreWebView2.WebMessageReceived -= OnWebMessageReceived;
        webView.CoreWebView2.WebMessageReceived += OnWebMessageReceived;

        webView.Source = new Uri("https://desktop.miniprod.local/index.html");

        sessionModel.BackendBaseUrl = _settingsService.Current.BackendBaseUrl;
        sessionModel.AccessToken = _sessionService.Current.AccessToken;
        sessionModel.Theme = _settingsService.Current.Theme;
    }

    public void PostBootstrap(WebView2 webView, TerminalSessionModel sessionModel)
    {
        var payload = $$"""
        {
          "type": "bootstrap",
          "baseUrl": "{{sessionModel.BackendBaseUrl}}",
          "accessToken": "{{sessionModel.AccessToken}}",
          "theme": "{{sessionModel.Theme}}",
          "activeServerName": "{{sessionModel.ActiveServerName}}"
        }
        """;

        webView.CoreWebView2?.PostWebMessageAsJson(payload);
    }

    private static void OnWebMessageReceived(CoreWebView2 sender, CoreWebView2WebMessageReceivedEventArgs args)
    {
        // Placeholder integration point for a richer terminal bridge.
        // Keep handler attached so the scaffold already has the host/web messaging seam.
        _ = sender;
        _ = args;
    }
}
