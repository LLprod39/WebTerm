# MiniProd Desktop

Initial Windows desktop scaffold for the `mini_prod` platform.

## Scope in this scaffold

- WinUI 3 shell with `NavigationView`
- Placeholder pages for login, servers, terminal, MCP, and settings
- Simple MVVM/service layout
- Local `WebView2` bridge host for the terminal surface
- Unpackaged-style project settings aimed at a per-user installer workflow

## Build notes

This scaffold was created manually because the local machine does not have the `dotnet new winui` template installed.

Prerequisites to build:

- .NET SDK with Windows desktop tooling
- Windows App SDK runtime/tooling compatible with the package versions in the project
- WebView2 runtime for the terminal host

Verified commands on this machine:

```powershell
dotnet restore .\MiniProd.Desktop.sln
dotnet build .\MiniProd.Desktop.sln -c Debug -p:Platform=x64 -m:1 /p:UseSharedCompilation=false /p:BuildInParallel=false
.\src\MiniProd.Desktop\bin\x64\Debug\net8.0-windows10.0.19041.0\MiniProd.Desktop.exe
```

If build fails due to missing WinUI/Windows App SDK tooling, install the official WinUI development prerequisites first instead of modifying the project layout.

## Current terminal status

- `Assets\TerminalBridge\index.html` and `Services\TerminalBridgeService.cs` are bundled and ready for the `WebView2` host handoff.
- The visible `TerminalPage` is currently a stable native placeholder that reports backend/session/server context while the embedded terminal surface is hardened for scripted builds.
