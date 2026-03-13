namespace MiniProd.Desktop.Services;

public sealed class SessionService
{
    private readonly SemaphoreSlim _authLock = new(1, 1);

    public DesktopSessionModel Current { get; private set; } = new();

    public event EventHandler? SessionChanged;

    public string LastAuthError { get; private set; } = string.Empty;

    public void SetSession(DesktopSessionModel session)
    {
        Current = session;
        LastAuthError = string.Empty;
        SessionChanged?.Invoke(this, EventArgs.Empty);
    }

    public void Clear()
    {
        Current = new DesktopSessionModel();
        SessionChanged?.Invoke(this, EventArgs.Empty);
    }

    public async Task<bool> EnsureAuthenticatedAsync(
        DesktopApiClient apiClient,
        SettingsService settingsService,
        CancellationToken cancellationToken = default)
    {
        if (Current.IsAuthenticated)
        {
            apiClient.SetAccessToken(Current.AccessToken);
            return true;
        }

        var settings = settingsService.Current;
        if (!settings.AutoSignIn)
        {
            LastAuthError = "Auto sign-in is disabled in settings.";
            return false;
        }

        var username = settings.DesktopUsername.Trim();
        var password = settings.DesktopPassword;
        if (string.IsNullOrWhiteSpace(username) || string.IsNullOrWhiteSpace(password))
        {
            LastAuthError = "Desktop credentials are not configured.";
            return false;
        }

        await _authLock.WaitAsync(cancellationToken);
        try
        {
            if (Current.IsAuthenticated)
            {
                apiClient.SetAccessToken(Current.AccessToken);
                return true;
            }

            var session = await apiClient.SignInAsync(username, password, cancellationToken);
            if (session is null)
            {
                apiClient.SetAccessToken(string.Empty);
                Clear();
                LastAuthError = "Desktop API sign-in failed. Check backend URL and credentials.";
                return false;
            }

            apiClient.SetAccessToken(session.AccessToken);
            SetSession(session);
            return true;
        }
        catch (Exception ex)
        {
            apiClient.SetAccessToken(string.Empty);
            Clear();
            LastAuthError = ex.Message;
            return false;
        }
        finally
        {
            _authLock.Release();
        }
    }
}
