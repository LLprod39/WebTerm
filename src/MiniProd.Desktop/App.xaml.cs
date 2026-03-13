using Microsoft.UI.Xaml;
using MiniProd.Desktop.Services;

namespace MiniProd.Desktop;

public partial class App : Application
{
    private Window? _window;

    public App()
    {
        InitializeComponent();
        Services = new AppServices();
    }

    public AppServices Services { get; }

    public static AppServices? TryGetServices()
    {
        return Application.Current is App app ? app.Services : null;
    }

    public static Window? TryGetMainWindow()
    {
        return Application.Current is App app ? app._window : null;
    }

    protected override async void OnLaunched(LaunchActivatedEventArgs args)
    {
        await Services.Settings.LoadAsync();
        await Services.Servers.LoadAsync();

        _window = new MainWindow();
        ApplyRequestedTheme(_window);
        _window.Activate();
    }

    public static void ApplyRequestedTheme(Window? window)
    {
        if (window?.Content is not FrameworkElement root || Application.Current is not App app)
        {
            return;
        }

        root.RequestedTheme = app.Services.Settings.Current.Theme switch
        {
            "Light" => ElementTheme.Light,
            "Dark" => ElementTheme.Dark,
            _ => ElementTheme.Default,
        };
    }
}
