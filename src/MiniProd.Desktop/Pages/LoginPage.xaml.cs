using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using MiniProd.Desktop.ViewModels;

namespace MiniProd.Desktop.Pages;

public sealed partial class LoginPage : Page
{
    public LoginPage()
    {
        InitializeComponent();
        var services = App.TryGetServices();
        var settings = services?.Settings ?? new Services.SettingsService();
        ViewModel = new LoginViewModel(
            services?.Api ?? new Services.DesktopApiClient(settings),
            services?.Session ?? new Services.SessionService());
        StatusMessageText.Text = ViewModel.StatusMessage;
    }

    public LoginViewModel ViewModel { get; }

    private void OnPasswordChanged(object sender, RoutedEventArgs e)
    {
        if (sender is PasswordBox passwordBox)
        {
            ViewModel.Password = passwordBox.Password;
        }
    }

    private async void OnSignInClicked(object sender, RoutedEventArgs e)
    {
        _ = sender;
        _ = e;
        ViewModel.Username = UsernameInput.Text;
        await ViewModel.SignInAsync();
        StatusMessageText.Text = ViewModel.StatusMessage;
    }
}
