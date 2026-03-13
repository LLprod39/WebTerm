using CommunityToolkit.Mvvm.ComponentModel;

namespace MiniProd.Desktop.ViewModels;

public sealed class ShellViewModel : ObservableObject
{
    private string _appTitle = "MiniProd Desktop";
    private string _subtitle = "Standalone SSH console with local server storage and AI-assisted command suggestions";

    public string AppTitle
    {
        get => _appTitle;
        set => SetProperty(ref _appTitle, value);
    }

    public string Subtitle
    {
        get => _subtitle;
        set => SetProperty(ref _subtitle, value);
    }
}
