using System.Net.Sockets;
using System.Text;
using Renci.SshNet;
using Renci.SshNet.Common;

namespace MiniProd.Desktop.Services;

public sealed class SshTerminalService : IDisposable
{
    private const int MaxTranscriptLength = 24_000;

    private readonly SemaphoreSlim _connectionGate = new(1, 1);
    private readonly StringBuilder _transcript = new();
    private readonly object _transcriptLock = new();

    private SshClient? _client;
    private ShellStream? _shellStream;
    private CancellationTokenSource? _readerCancellation;
    private Task? _readerTask;

    public event EventHandler<string>? OutputReceived;

    public event EventHandler<string>? StatusChanged;

    public bool IsConnected => _client?.IsConnected == true && _shellStream is not null;

    public int? CurrentServerId { get; private set; }

    public string CurrentServerName { get; private set; } = string.Empty;

    public async Task ConnectAsync(StoredServerModel server, string secret, CancellationToken cancellationToken = default)
    {
        await _connectionGate.WaitAsync(cancellationToken);
        try
        {
            await DisconnectCoreAsync(reportStatus: false);
            RaiseStatus($"Connecting to {server.Name}...");

            var authenticationMethod = BuildAuthenticationMethod(server, secret);
            var connectionInfo = new ConnectionInfo(
                server.Host,
                server.Port,
                server.Username,
                authenticationMethod)
            {
                Timeout = TimeSpan.FromSeconds(20),
            };

            var client = new SshClient(connectionInfo);
            await Task.Run(() => client.Connect(), cancellationToken);

            if (!client.IsConnected)
            {
                client.Dispose();
                throw new InvalidOperationException("SSH client failed to open the connection.");
            }

            var shellStream = client.CreateShellStream("xterm", 120, 36, 1024, 768, 4096);
            _client = client;
            _shellStream = shellStream;
            CurrentServerId = server.Id;
            CurrentServerName = server.Name;
            ResetTranscript();
            EmitLocalLine($"[connected] {server.Username}@{server.Host}:{server.Port}");

            _readerCancellation = new CancellationTokenSource();
            _readerTask = Task.Run(() => ReadLoopAsync(shellStream, _readerCancellation.Token));
            RaiseStatus($"Connected to {server.Name}");
        }
        catch (Exception ex) when (ex is SshException or SocketException or InvalidOperationException or FileNotFoundException)
        {
            await DisconnectCoreAsync(reportStatus: false);
            RaiseStatus($"Connection failed: {ex.Message}");
            throw new InvalidOperationException(ex.Message, ex);
        }
        finally
        {
            _connectionGate.Release();
        }
    }

    public async Task DisconnectAsync()
    {
        await _connectionGate.WaitAsync();
        try
        {
            await DisconnectCoreAsync(reportStatus: true);
        }
        finally
        {
            _connectionGate.Release();
        }
    }

    public async Task SendLineAsync(string command, CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(command))
        {
            return;
        }

        await SendRawAsync(command.TrimEnd() + "\n", cancellationToken);
    }

    public async Task SendInterruptAsync(CancellationToken cancellationToken = default)
    {
        await SendRawAsync("\u0003", cancellationToken);
    }

    public string GetTranscriptSnapshot()
    {
        lock (_transcriptLock)
        {
            return _transcript.ToString();
        }
    }

    public void Dispose()
    {
        _readerCancellation?.Cancel();
        _shellStream?.Dispose();

        if (_client?.IsConnected == true)
        {
            _client.Disconnect();
        }

        _client?.Dispose();
        _readerCancellation?.Dispose();
        _connectionGate.Dispose();
    }

    private async Task SendRawAsync(string input, CancellationToken cancellationToken)
    {
        if (!IsConnected || _shellStream is null)
        {
            throw new InvalidOperationException("SSH session is not connected.");
        }

        await Task.Run(
            () =>
            {
                cancellationToken.ThrowIfCancellationRequested();
                _shellStream.Write(input);
                _shellStream.Flush();
            },
            cancellationToken);
    }

    private async Task ReadLoopAsync(ShellStream shellStream, CancellationToken cancellationToken)
    {
        try
        {
            while (!cancellationToken.IsCancellationRequested)
            {
                if (shellStream.DataAvailable)
                {
                    var chunk = shellStream.Read();
                    if (!string.IsNullOrEmpty(chunk))
                    {
                        AppendTranscript(chunk);
                        OutputReceived?.Invoke(this, chunk);
                    }

                    continue;
                }

                await Task.Delay(40, cancellationToken);
            }
        }
        catch (OperationCanceledException)
        {
        }
        catch (Exception ex)
        {
            RaiseStatus($"Session error: {ex.Message}");
        }
        finally
        {
            if (!cancellationToken.IsCancellationRequested && _client?.IsConnected != true)
            {
                RaiseStatus("SSH session closed.");
            }
        }
    }

    private async Task DisconnectCoreAsync(bool reportStatus)
    {
        _readerCancellation?.Cancel();

        if (_readerTask is not null)
        {
            try
            {
                await _readerTask;
            }
            catch
            {
            }
        }

        _shellStream?.Dispose();
        _shellStream = null;

        if (_client?.IsConnected == true)
        {
            _client.Disconnect();
        }

        _client?.Dispose();
        _client = null;

        _readerCancellation?.Dispose();
        _readerCancellation = null;
        _readerTask = null;
        CurrentServerId = null;
        CurrentServerName = string.Empty;

        if (reportStatus)
        {
            RaiseStatus("Disconnected.");
        }
    }

    private static AuthenticationMethod BuildAuthenticationMethod(StoredServerModel server, string secret)
    {
        if (string.Equals(server.AuthMethod, "key", StringComparison.OrdinalIgnoreCase))
        {
            if (string.IsNullOrWhiteSpace(server.KeyPath))
            {
                throw new InvalidOperationException("A private key path is required.");
            }

            if (!File.Exists(server.KeyPath))
            {
                throw new FileNotFoundException("Private key file was not found.", server.KeyPath);
            }

            var keyFile = string.IsNullOrWhiteSpace(secret)
                ? new PrivateKeyFile(server.KeyPath)
                : new PrivateKeyFile(server.KeyPath, secret);
            return new PrivateKeyAuthenticationMethod(server.Username, keyFile);
        }

        if (string.IsNullOrWhiteSpace(secret))
        {
            throw new InvalidOperationException("No password is saved for this server.");
        }

        return new PasswordAuthenticationMethod(server.Username, secret);
    }

    private void AppendTranscript(string text)
    {
        lock (_transcriptLock)
        {
            _transcript.Append(text);
            if (_transcript.Length > MaxTranscriptLength)
            {
                _transcript.Remove(0, _transcript.Length - MaxTranscriptLength);
            }
        }
    }

    private void ResetTranscript()
    {
        lock (_transcriptLock)
        {
            _transcript.Clear();
        }
    }

    private void EmitLocalLine(string line)
    {
        var chunk = line + Environment.NewLine;
        AppendTranscript(chunk);
        OutputReceived?.Invoke(this, chunk);
    }

    private void RaiseStatus(string status)
    {
        StatusChanged?.Invoke(this, status);
    }
}
