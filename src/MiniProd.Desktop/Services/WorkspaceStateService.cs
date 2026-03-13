namespace MiniProd.Desktop.Services;

public sealed class WorkspaceStateService
{
    public event EventHandler? SelectedServerChanged;

    public int? SelectedServerId { get; private set; }

    public string SelectedServerName { get; private set; } = string.Empty;

    public void SetSelectedServer(ServerSummaryModel? server)
    {
        SelectedServerId = server?.Id;
        SelectedServerName = server?.Name ?? string.Empty;
        SelectedServerChanged?.Invoke(this, EventArgs.Empty);
    }
}
