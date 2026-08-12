param(
    [Parameter(Mandatory=$true)] [string]$SshUser,
    [Parameter(Mandatory=$true)] [string]$SshHost,
    [int]$SshPort = 22,
    [int]$LocalOllamaPort = 11435,
    [int]$RemoteOllamaPort = 11434
)

Write-Host "Membuka tunnel Ollama HPC pada localhost:$LocalOllamaPort..."
ssh `
  -p $SshPort `
  -N `
  -L "${LocalOllamaPort}:127.0.0.1:${RemoteOllamaPort}" `
  -o ServerAliveInterval=30 `
  -o ServerAliveCountMax=3 `
  "${SshUser}@${SshHost}"
