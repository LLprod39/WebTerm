using CommunityToolkit.Mvvm.ComponentModel;
using MiniProd.Desktop.Services;

namespace MiniProd.Desktop.ViewModels;

public sealed class LoginViewModel : ObservableObject
{
    private readonly DesktopApiClient _apiClient;
    private readonly SessionService _sessionService;
    private string _username = string.Empty;
    private string _password = string.Empty;
    private string _statusMessage = "Ready to connect to the central backend.";
    private bool _isBusy;

    public LoginViewModel(DesktopApiClient apiClient, SessionService sessionService)
    {
        _apiClient = apiClient;
        _sessionService = sessionService;
    }

    public string Username
    {
        get => _username;
        set => SetProperty(ref _username, value);
    }

    public string Password
    {
        get => _password;
        set => SetProperty(ref _password, value);
    }

    public string StatusMessage
    {
        get => _statusMessage;
        set => SetProperty(ref _statusMessage, value);
    }

    public bool IsBusy
    {
        get => _isBusy;
        set => SetProperty(ref _isBusy, value);
    }

    public async Task SignInAsync()
    {
        IsBusy = true;
        try
        {
            var session = await _apiClient.SignInAsync(Username, Password);
            if (session is null)
            {
                StatusMessage = "Login failed or desktop auth endpoint is not available yet.";
                return;
            }

            _apiClient.SetAccessToken(session.AccessToken);
            _sessionService.SetSession(session);
            StatusMessage = $"Authenticated as {session.DisplayName}.";
        }
        catch (Exception ex)
        {
            StatusMessage = $"Login error: {ex.Message}";
        }
        finally
        {
            IsBusy = false;
        }
    }
}
