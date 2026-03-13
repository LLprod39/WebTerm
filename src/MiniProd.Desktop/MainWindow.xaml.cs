using MiniProd.Desktop.ViewModels;
using MiniProd.Desktop.Pages;

namespace MiniProd.Desktop;

public sealed partial class MainWindow : Window
{
    private readonly Services.AppServices? _services;

    public MainWindow()
    {
        InitializeComponent();
        ViewModel = new ShellViewModel();
        Title = "MiniProd Desktop";
        _services = App.TryGetServices();
        _services?.Navigation.Initialize(ContentFrame);
        ShellNavigationView.SelectedItem = ServersItem;
        _services?.Navigation.Navigate(typeof(ServersPage));
    }

    public ShellViewModel ViewModel { get; }

    private void OnNavigationSelectionChanged(NavigationView sender, NavigationViewSelectionChangedEventArgs args)
    {
        _ = sender;

        if (args.IsSettingsSelected)
        {
            _services?.Navigation.Navigate(typeof(SettingsPage));
            return;
        }

        if (args.SelectedItemContainer?.Tag is not string tag)
        {
            return;
        }

        switch (tag)
        {
            case "servers":
                _services?.Navigation.Navigate(typeof(ServersPage));
                break;
            case "terminal":
                _services?.Navigation.Navigate(typeof(TerminalPage));
                break;
        }
    }
}
