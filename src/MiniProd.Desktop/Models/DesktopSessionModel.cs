namespace MiniProd.Desktop.Models;

public sealed class DesktopSessionModel
{
    public string AccessToken { get; set; } = string.Empty;

    public string RefreshToken { get; set; } = string.Empty;

    public string Username { get; set; } = string.Empty;

    public string DisplayName => string.IsNullOrWhiteSpace(Username) ? "Guest" : Username;

    public bool IsAuthenticated => !string.IsNullOrWhiteSpace(AccessToken);
}
