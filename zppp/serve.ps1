param(
  [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$listener = New-Object System.Net.HttpListener
$prefix = "http://127.0.0.1:$Port/"
$listener.Prefixes.Add($prefix)

$mimeTypes = @{
  ".html" = "text/html; charset=utf-8"
  ".css" = "text/css; charset=utf-8"
  ".js" = "application/javascript; charset=utf-8"
  ".json" = "application/json; charset=utf-8"
  ".png" = "image/png"
  ".jpg" = "image/jpeg"
  ".jpeg" = "image/jpeg"
  ".gif" = "image/gif"
  ".svg" = "image/svg+xml"
  ".ico" = "image/x-icon"
  ".webp" = "image/webp"
  ".pdf" = "application/pdf"
  ".txt" = "text/plain; charset=utf-8"
}

function Get-ContentType([string]$path) {
  $ext = [System.IO.Path]::GetExtension($path).ToLowerInvariant()
  if ($mimeTypes.ContainsKey($ext)) {
    return $mimeTypes[$ext]
  }
  return "application/octet-stream"
}

function Resolve-RequestPath([string]$rawPath) {
  $decoded = [System.Uri]::UnescapeDataString($rawPath.TrimStart("/"))
  if ([string]::IsNullOrWhiteSpace($decoded)) {
    return Join-Path $root "index.html"
  }

  $fullPath = [System.IO.Path]::GetFullPath((Join-Path $root $decoded))
  if (-not $fullPath.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase)) {
    return $null
  }

  if (Test-Path $fullPath -PathType Container) {
    $indexPath = Join-Path $fullPath "index.html"
    if (Test-Path $indexPath -PathType Leaf) {
      return $indexPath
    }
  }

  if (Test-Path $fullPath -PathType Leaf) {
    return $fullPath
  }

  return Join-Path $root "index.html"
}

try {
  $listener.Start()
  Write-Host "Static server running at $prefix"
  Write-Host "Root: $root"
  Write-Host "Press Ctrl+C to stop."

  while ($listener.IsListening) {
    $context = $listener.GetContext()
    try {
      $target = Resolve-RequestPath $context.Request.Url.AbsolutePath
      if (-not $target) {
        $context.Response.StatusCode = 403
        $context.Response.Close()
        continue
      }

      $bytes = [System.IO.File]::ReadAllBytes($target)
      $context.Response.StatusCode = 200
      $context.Response.ContentType = Get-ContentType $target
      $context.Response.ContentLength64 = $bytes.Length
      $context.Response.AddHeader("Cache-Control", "no-store, no-cache, must-revalidate")
      $context.Response.OutputStream.Write($bytes, 0, $bytes.Length)
      $context.Response.OutputStream.Close()
    } catch {
      try {
        $message = [System.Text.Encoding]::UTF8.GetBytes("Server error: $($_.Exception.Message)")
        $context.Response.StatusCode = 500
        $context.Response.ContentType = "text/plain; charset=utf-8"
        $context.Response.ContentLength64 = $message.Length
        $context.Response.OutputStream.Write($message, 0, $message.Length)
        $context.Response.OutputStream.Close()
      } catch {
      }
    }
  }
} finally {
  if ($listener.IsListening) {
    $listener.Stop()
  }
  $listener.Close()
}
