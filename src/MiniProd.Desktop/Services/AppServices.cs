namespace MiniProd.Desktop.Services;

public sealed class AppServices
{
    public AppServices()
    {
        Secrets = new ProtectedSecretService();
        Settings = new SettingsService(Secrets);
        Servers = new LocalServerStoreService(Secrets);
        Terminal = new SshTerminalService();
        AiAssistant = new AiAssistantService(Settings);
        Navigation = new NavigationService();
        Workspace = new WorkspaceStateService();
    }

    public ProtectedSecretService Secrets { get; }

    public SettingsService Settings { get; }

    public LocalServerStoreService Servers { get; }

    public NavigationService Navigation { get; }

    public WorkspaceStateService Workspace { get; }

    public SshTerminalService Terminal { get; }

    public AiAssistantService AiAssistant { get; }
}
