#Requires -Version 7.0
<#
.SYNOPSIS
  Ghostbit PowerShell module — create and view encrypted pastes from the terminal.

.DESCRIPTION
  Mirrors the Python CLI (gb). All encryption is done client-side with AES-256-GCM
  using the .NET System.Security.Cryptography APIs (no external dependencies).

  Requires PowerShell 7.0+ (.NET 5+).

.EXAMPLE
  Get-Content main.py | New-GhostbitPaste
  New-GhostbitPaste main.py
  New-GhostbitPaste main.py -Language python -Burn
  New-GhostbitPaste main.py -ExpiresIn 3600 -Password secret
  Get-GhostbitPaste "https://paste.example.com/abc123#KEY~TOKEN"
  Invoke-GhostbitConfig set server https://paste.example.com
  Invoke-GhostbitConfig show
#>

Set-StrictMode -Version Latest

$script:Version       = '1.0.0'
$script:UserAgent     = "Ghostbit-PS/$script:Version"
$script:DefaultServer = 'http://localhost:8000'
$script:ConfigPath    = if ($IsWindows) {
    Join-Path $env:APPDATA 'ghostbit\config.toml'
} else {
    Join-Path $HOME '.config/ghostbit.toml'
}
$script:HistoryPath   = if ($IsWindows) {
    Join-Path $env:LOCALAPPDATA 'ghostbit\history.jsonl'
} else {
    Join-Path $HOME '.local/share/ghostbit/history.jsonl'
}

# ── Config ────────────────────────────────────────────────────────────────────

function Read-GhostbitConfig {
    $cfg = @{}
    if (Test-Path $script:ConfigPath) {
        foreach ($line in Get-Content $script:ConfigPath) {
            $line = $line.Trim()
            if ($line -and -not $line.StartsWith('#') -and $line -match '^(\w+)\s*=\s*"?(.*?)"?\s*$') {
                $cfg[$Matches[1]] = $Matches[2]
            }
        }
    }
    return $cfg
}

function Write-GhostbitConfig {
    param([hashtable]$Config)
    $dir = Split-Path $script:ConfigPath -Parent
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    ($Config.GetEnumerator() | ForEach-Object { "$($_.Key) = `"$($_.Value)`"" }) -join "`n" |
        Set-Content -Path $script:ConfigPath -Encoding UTF8
}

# ── Crypto ────────────────────────────────────────────────────────────────────

function New-RandomBytes {
    param([int]$Length)
    $bytes = [byte[]]::new($Length)
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    return $bytes
}

function Invoke-AesGcmEncrypt {
    param(
        [string]$Plaintext,
        [byte[]]$Key
    )
    $nonce         = New-RandomBytes -Length 12
    $plaintextBytes = [System.Text.Encoding]::UTF8.GetBytes($Plaintext)
    $ciphertext    = [byte[]]::new($plaintextBytes.Length)
    $tag           = [byte[]]::new(16)

    $aes = [System.Security.Cryptography.AesGcm]::new($Key)
    try {
        $aes.Encrypt($nonce, $plaintextBytes, $ciphertext, $tag)
    } finally {
        $aes.Dispose()
    }

    # Append GCM tag to ciphertext — matches Python AESGCM output format
    $ctWithTag = $ciphertext + $tag

    return [PSCustomObject]@{
        Ciphertext = [Convert]::ToBase64String($ctWithTag)
        Nonce      = [Convert]::ToBase64String($nonce)
    }
}

function Invoke-AesGcmDecrypt {
    param(
        [string]$CiphertextB64,
        [string]$NonceB64,
        [byte[]]$Key
    )
    $ctWithTag = [Convert]::FromBase64String($CiphertextB64)
    $nonce     = [Convert]::FromBase64String($NonceB64)

    $tagLen    = 16
    $ciphertext = $ctWithTag[0..($ctWithTag.Length - $tagLen - 1)]
    $tag        = $ctWithTag[($ctWithTag.Length - $tagLen)..($ctWithTag.Length - 1)]
    $plaintext  = [byte[]]::new($ciphertext.Length)

    $aes = [System.Security.Cryptography.AesGcm]::new($Key)
    try {
        $aes.Decrypt($nonce, $ciphertext, $tag, $plaintext)
    } finally {
        $aes.Dispose()
    }

    return [System.Text.Encoding]::UTF8.GetString($plaintext)
}

function Get-DerivedKey {
    param(
        [string]$Password,
        [string]$SaltB64
    )
    $salt = [Convert]::FromBase64String($SaltB64)
    $kdf  = [System.Security.Cryptography.Rfc2898DeriveBytes]::new(
        $Password, $salt, 600000,
        [System.Security.Cryptography.HashAlgorithmName]::SHA256
    )
    try {
        return $kdf.GetBytes(32)
    } finally {
        $kdf.Dispose()
    }
}

function ConvertTo-UrlSafeBase64 {
    param([byte[]]$Bytes)
    return [Convert]::ToBase64String($Bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function ConvertFrom-UrlSafeBase64 {
    param([string]$B64Url)
    $b64 = $B64Url.Replace('-', '+').Replace('_', '/')
    $pad = (4 - ($b64.Length % 4)) % 4
    if ($pad -ne 4) { $b64 += '=' * $pad }
    return [Convert]::FromBase64String($b64)
}

# ── Extension → language map ──────────────────────────────────────────────────

$script:ExtMap = @{
    '.py'='python'; '.js'='javascript'; '.ts'='typescript'; '.go'='go'
    '.rs'='rust'; '.rb'='ruby'; '.php'='php'; '.java'='java'
    '.c'='c'; '.cpp'='cpp'; '.cs'='csharp'
    '.sh'='bash'; '.bash'='bash'; '.zsh'='bash'
    '.ps1'='powershell'; '.psm1'='powershell'; '.psd1'='powershell'
    '.html'='html'; '.css'='css'; '.sql'='sql'
    '.json'='json'; '.yaml'='yaml'; '.yml'='yaml'
    '.toml'='toml'; '.xml'='xml'; '.md'='markdown'
    '.dockerfile'='dockerfile'; '.kt'='kotlin'; '.swift'='swift'
    '.lua'='lua'; '.r'='r'; '.diff'='diff'; '.patch'='diff'
}

# ── New-GhostbitPaste ─────────────────────────────────────────────────────────

function New-GhostbitPaste {
    <#
    .SYNOPSIS
      Create an encrypted paste on a Ghostbit server.

    .DESCRIPTION
      Encrypts content client-side with AES-256-GCM before sending it to the
      server. The decryption key never leaves the client — it is embedded in
      the URL fragment returned by this command.

    .PARAMETER InputObject
      Content piped from the pipeline (e.g. Get-Content file.py | gb).

    .PARAMETER Path
      Path to a file to paste. Language is auto-detected from the extension.

    .PARAMETER Server
      Server URL for this invocation. Overrides the saved config.

    .PARAMETER Language
      Language hint for syntax highlighting (python, go, rust, sql, …).

    .PARAMETER ExpiresIn
      Expiry TTL in seconds (3600 = 1 h, 86400 = 1 d). Default: never.

    .PARAMETER Burn
      Delete after the first view.

    .PARAMETER MaxViews
      Delete after N views.

    .PARAMETER Password
      Encrypt with a password (PBKDF2-SHA256, client-side).

    .PARAMETER Quiet
      Print only the URL.

    .PARAMETER AsJson
      Print the full API JSON response including full_url.

    .EXAMPLE
      Get-Content main.py | New-GhostbitPaste
      New-GhostbitPaste main.py -Language python -Burn
      New-GhostbitPaste main.py -ExpiresIn 3600 -Password s3cr3t
    #>
    [CmdletBinding()]
    [Alias('gb')]
    param(
        [Parameter(ValueFromPipeline)]
        [string]$InputObject,

        [Parameter(Position = 0)]
        [string]$Path,

        [string]$Server,
        [string]$Language,
        [int]$ExpiresIn,
        [switch]$Burn,
        [int]$MaxViews,
        [string]$Password,
        [switch]$Quiet,
        [switch]$AsJson
    )

    begin {
        $lines = [System.Collections.Generic.List[string]]::new()
    }

    process {
        if ($InputObject) { $lines.Add($InputObject) }
    }

    end {
        $cfg       = Read-GhostbitConfig
        $serverUrl = if ($Server) { $Server } elseif ($cfg['server']) { $cfg['server'] } else { $script:DefaultServer }

        # ── Read content ──
        $content = $null
        if ($Path) {
            if (-not (Test-Path $Path)) {
                Write-Error "File not found: $Path"
                return
            }
            $content = Get-Content -Path $Path -Raw -Encoding UTF8
            if (-not $Language) {
                $ext      = [System.IO.Path]::GetExtension($Path).ToLower()
                $Language = $script:ExtMap[$ext]
            }
        } elseif ($lines.Count -gt 0) {
            $content = $lines -join "`n"
        } else {
            Write-Error 'Provide a file path (-Path) or pipe content.'
            return
        }

        if ([string]::IsNullOrWhiteSpace($content)) {
            Write-Error 'Content is empty.'
            return
        }

        # ── Encrypt ──
        if ($Password) {
            $saltBytes = New-RandomBytes -Length 16
            $kdfSalt   = [Convert]::ToBase64String($saltBytes)
            $key       = Get-DerivedKey -Password $Password -SaltB64 $kdfSalt
        } else {
            $key     = New-RandomBytes -Length 32
            $kdfSalt = $null
        }

        $encrypted = Invoke-AesGcmEncrypt -Plaintext $content -Key $key

        $payload = [ordered]@{
            content    = $encrypted.Ciphertext
            nonce      = $encrypted.Nonce
            kdf_salt   = $kdfSalt
            language   = if ($Language) { $Language } else { $null }
            expires_in = if ($ExpiresIn -gt 0) { $ExpiresIn } else { $null }
            burn       = $Burn.IsPresent
            max_views  = if ($MaxViews -gt 0) { $MaxViews } else { $null }
        }

        # ── POST ──
        $apiUrl = ($serverUrl.TrimEnd('/')) + '/api/v1/pastes'
        try {
            $response = Invoke-RestMethod -Uri $apiUrl -Method Post `
                -ContentType 'application/json' `
                -Body ($payload | ConvertTo-Json) `
                -Headers @{ 'User-Agent' = $script:UserAgent }
        } catch {
            $code = $_.Exception.Response.StatusCode.value__
            Write-Error "Error $code`: $($_.ErrorDetails.Message ?? $_.Exception.Message)"
            return
        }

        # ── Build full URL ──
        $fragment = if ($Password) {
            "~$($response.delete_token)"
        } else {
            "$(ConvertTo-UrlSafeBase64 $key)~$($response.delete_token)"
        }
        $fullUrl = "$($response.url)#$fragment"

        # ── Append to local history (best-effort, never blocks) ──
        try {
            $dir = Split-Path $script:HistoryPath -Parent
            if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
            $entry = [ordered]@{
                id         = $response.id
                url        = $response.url
                full_url   = $fullUrl
                created_at = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
                language   = if ($Language) { $Language } else { $null }
                expires_at = $response.expires_at
            }
            Add-Content -Path $script:HistoryPath -Value ($entry | ConvertTo-Json -Compress) -Encoding UTF8
        } catch { }

        if ($AsJson) {
            $response | Add-Member -NotePropertyName full_url -NotePropertyValue $fullUrl -Force
            $response | ConvertTo-Json
            return
        }

        Write-Output $fullUrl

        if (-not $Quiet) {
            $parts = @()
            if ($response.expires_at) {
                $delta = $response.expires_at - [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
                if     ($delta -lt 3600)  { $parts += "expires in $([int]($delta / 60))m" }
                elseif ($delta -lt 86400) { $parts += "expires in $([int]($delta / 3600))h" }
                else                      { $parts += "expires in $([int]($delta / 86400))d" }
            }
            if ($response.burn)      { $parts += 'burn after read' }
            if ($response.max_views) { $parts += "max $($response.max_views) views" }
            if ($Password)           { $parts += 'password protected' }
            if ($parts) {
                Write-Host "  $($parts -join '  ·  ')" -ForegroundColor DarkGray
            }
            if (-not $Password) {
                Write-Host '  Share the full URL — the decryption key is in the #fragment.' -ForegroundColor DarkGray
            }
        }
    }
}

# ── Get-GhostbitPaste ─────────────────────────────────────────────────────────

function Get-GhostbitPaste {
    <#
    .SYNOPSIS
      Download and decrypt a paste from a Ghostbit server.

    .PARAMETER Url
      Full paste URL including the #fragment (decryption key and delete token).

    .PARAMETER Password
      Password for password-protected pastes. If omitted you are prompted.

    .EXAMPLE
      Get-GhostbitPaste "https://paste.example.com/abc123#KEY~TOKEN"
      gbv "https://paste.example.com/abc123#~TOKEN"   # prompts for password
    #>
    [CmdletBinding()]
    [Alias('gbv')]
    param(
        [Parameter(Mandatory, Position = 0)]
        [string]$Url,

        [string]$Password
    )

    # ── Parse URL ──
    $uri       = [System.Uri]$Url
    $fragment  = $uri.Fragment.TrimStart('#')
    $serverUrl = "$($uri.Scheme)://$($uri.Authority)"
    $pasteId   = $uri.AbsolutePath.Trim('/')

    $keyB64Url  = $fragment.Split('~')[0]
    $isPassword = [string]::IsNullOrEmpty($keyB64Url)

    # ── Fetch ciphertext ──
    $apiUrl = "$serverUrl/api/v1/pastes/$pasteId"
    try {
        $data = Invoke-RestMethod -Uri $apiUrl -Method Get `
            -Headers @{ 'User-Agent' = $script:UserAgent }
    } catch {
        $code = $_.Exception.Response.StatusCode.value__
        if ($code -eq 404) {
            Write-Error 'Paste not found or has expired.'
        } else {
            Write-Error "Error $code`: $($_.ErrorDetails.Message ?? $_.Exception.Message)"
        }
        return
    }

    # ── Derive or import key ──
    if ($isPassword) {
        if (-not $Password) {
            $securePass = Read-Host -Prompt 'Password' -AsSecureString
            $Password   = [System.Net.NetworkCredential]::new('', $securePass).Password
        }
        if (-not $data.kdf_salt) {
            Write-Error 'Paste is not password-protected (no KDF salt).'
            return
        }
        $key = Get-DerivedKey -Password $Password -SaltB64 $data.kdf_salt
    } else {
        $key = ConvertFrom-UrlSafeBase64 -B64Url $keyB64Url
    }

    # ── Decrypt ──
    try {
        $plaintext = Invoke-AesGcmDecrypt -CiphertextB64 $data.content -NonceB64 $data.nonce -Key $key
    } catch {
        Write-Error 'Decryption failed — wrong key or password, or corrupted paste.'
        return
    }

    # ── Burn warning ──
    $burned = $data.burn -or ($data.max_views -and $data.view_count -ge $data.max_views)
    if ($burned) {
        Write-Warning 'This paste has been burned and is no longer available on the server.'
    }

    Write-Output $plaintext
}

# ── Invoke-GhostbitConfig ─────────────────────────────────────────────────────

function Invoke-GhostbitConfig {
    <#
    .SYNOPSIS
      Manage Ghostbit CLI configuration.

    .EXAMPLE
      Invoke-GhostbitConfig show
      Invoke-GhostbitConfig set server https://paste.example.com
      Invoke-GhostbitConfig unset server
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory, Position = 0)]
        [ValidateSet('show', 'set', 'unset')]
        [string]$Action,

        [Parameter(Position = 1)][string]$Key,
        [Parameter(Position = 2)][string]$Value
    )

    $validKeys = @('server')

    switch ($Action) {
        'show' {
            $cfg = Read-GhostbitConfig
            if ($cfg.Count -eq 0) {
                Write-Host "No config yet. File: $script:ConfigPath" -ForegroundColor DarkGray
                Write-Host "server = '$script:DefaultServer'  (default)"
            } else {
                Write-Host "# $script:ConfigPath" -ForegroundColor DarkGray
                $cfg.GetEnumerator() | ForEach-Object { Write-Host "$($_.Key) = '$($_.Value)'" }
            }
        }
        'set' {
            if (-not $Key) { Write-Error 'Specify a key.'; return }
            $k = $Key.ToLower()
            if ($k -notin $validKeys) {
                Write-Error "Unknown key '$k'. Valid keys: $($validKeys -join ', ')"
                return
            }
            $cfg     = Read-GhostbitConfig
            $cfg[$k] = $Value
            Write-GhostbitConfig -Config $cfg
            Write-Host "Set $k = '$Value'"
            Write-Host "Config saved to $script:ConfigPath"
        }
        'unset' {
            if (-not $Key) { Write-Error 'Specify a key.'; return }
            $k   = $Key.ToLower()
            $cfg = Read-GhostbitConfig
            if ($cfg.ContainsKey($k)) {
                $cfg.Remove($k)
                Write-GhostbitConfig -Config $cfg
                Write-Host "Removed '$k' from config."
            } else {
                Write-Warning "'$k' is not set."
            }
        }
    }
}

# ── Remove-GhostbitPaste ─────────────────────────────────────────────────────

function Remove-GhostbitPaste {
    <#
    .SYNOPSIS
      Delete a paste using the delete token embedded in its URL.

    .PARAMETER Url
      Full paste URL including the #fragment (KEY~DELETE_TOKEN or ~DELETE_TOKEN).

    .EXAMPLE
      Remove-GhostbitPaste "https://paste.example.com/abc123#KEY~TOKEN"
      gbd "https://paste.example.com/abc123#KEY~TOKEN"
    #>
    [CmdletBinding()]
    [Alias('gbd')]
    param(
        [Parameter(Mandatory, Position = 0)]
        [string]$Url
    )

    $uri         = [System.Uri]$Url
    $fragment    = $uri.Fragment.TrimStart('#')
    $serverUrl   = "$($uri.Scheme)://$($uri.Authority)"
    $pasteId     = $uri.AbsolutePath.Trim('/')
    $deleteToken = $fragment.Split('~', 2)[1]

    if ([string]::IsNullOrEmpty($deleteToken)) {
        Write-Error 'Delete token missing from URL fragment (expected KEY~TOKEN or ~TOKEN).'
        return
    }

    $apiUrl = "$serverUrl/api/v1/pastes/$pasteId"
    try {
        Invoke-RestMethod -Uri $apiUrl -Method Delete `
            -Headers @{ 'User-Agent' = $script:UserAgent; 'X-Delete-Token' = $deleteToken } | Out-Null
        Write-Host "Deleted $pasteId."
    } catch {
        $code = $_.Exception.Response.StatusCode.value__
        switch ($code) {
            403 { Write-Error 'Invalid delete token.' }
            404 { Write-Error 'Paste not found (already deleted or expired).' }
            default { Write-Error "Error $code`: $($_.ErrorDetails.Message ?? $_.Exception.Message)" }
        }
    }
}

# ── Get-GhostbitHistory ───────────────────────────────────────────────────────

function Get-GhostbitHistory {
    <#
    .SYNOPSIS
      List pastes created on this machine, or clear the local history.

    .DESCRIPTION
      History is stored locally at:
        Windows : %LOCALAPPDATA%\ghostbit\history.jsonl
        macOS/Linux : ~/.local/share/ghostbit/history.jsonl

      Nothing is sent to the server — this file stays on your machine only.

    .PARAMETER Clear
      Wipe the local history file.

    .EXAMPLE
      Get-GhostbitHistory
      Get-GhostbitHistory -Clear
      gbh
    #>
    [CmdletBinding()]
    [Alias('gbh')]
    param(
        [switch]$Clear
    )

    if ($Clear) {
        if (Test-Path $script:HistoryPath) {
            Remove-Item $script:HistoryPath -Force
            Write-Host 'History cleared.'
        } else {
            Write-Host 'No history file found.'
        }
        return
    }

    if (-not (Test-Path $script:HistoryPath)) {
        Write-Host 'No pastes in local history.' -ForegroundColor DarkGray
        Write-Host "  History file: $script:HistoryPath" -ForegroundColor DarkGray
        return
    }

    $entries = Get-Content $script:HistoryPath -Encoding UTF8 |
        Where-Object { $_ -match '\S' } |
        ForEach-Object { $_ | ConvertFrom-Json }

    if (-not $entries) {
        Write-Host 'No pastes in local history.' -ForegroundColor DarkGray
        return
    }

    $now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()

    function Format-Age([long]$ts) {
        $d = $now - $ts
        if ($d -lt 120)    { return 'just now' }
        if ($d -lt 3600)   { return "$([int]($d/60))m ago" }
        if ($d -lt 86400)  { return "$([int]($d/3600))h ago" }
        return "$([int]($d/86400))d ago"
    }

    function Format-Expiry($exp) {
        if (-not $exp)     { return 'never' }
        $d = $exp - $now
        if ($d -le 0)      { return 'expired' }
        if ($d -lt 3600)   { return "in $([int]($d/60))m" }
        if ($d -lt 86400)  { return "in $([int]($d/3600))h" }
        return "in $([int]($d/86400))d"
    }

    $header = '{0,-12} {1,-14} {2,-12} {3,-10}  {4}' -f 'ID', 'Lang', 'Created', 'Expires', 'URL'
    Write-Host $header
    Write-Host ('-' * 80)

    [array]::Reverse(($entries = @($entries)))
    foreach ($e in $entries) {
        $id      = ([string]$e.id).PadRight(12).Substring(0, [Math]::Min(12, ([string]$e.id).Length)).PadRight(12)
        $lang    = ([string]($e.language ?? 'plain')).PadRight(14).Substring(0, [Math]::Min(14, ([string]($e.language ?? 'plain')).Length)).PadRight(14)
        $created = (Format-Age $e.created_at).PadRight(12)
        $expires = (Format-Expiry $e.expires_at).PadRight(10)
        $url     = $e.full_url ?? $e.url
        Write-Host ('{0} {1} {2} {3}  {4}' -f $id, $lang, $created, $expires, $url)
    }
}

# ── Exports ───────────────────────────────────────────────────────────────────

Export-ModuleMember -Function New-GhostbitPaste, Get-GhostbitPaste, Remove-GhostbitPaste, `
                               Get-GhostbitHistory, Invoke-GhostbitConfig `
                    -Alias gb, gbv, gbd, gbh
