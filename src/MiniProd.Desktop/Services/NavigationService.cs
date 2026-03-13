namespace MiniProd.Desktop.Services;

public sealed class NavigationService
{
    private Frame? _frame;

    public void Initialize(Frame frame)
    {
        _frame = frame;
    }

    public bool Navigate(Type pageType)
    {
        return _frame?.Navigate(pageType) ?? false;
    }
}
