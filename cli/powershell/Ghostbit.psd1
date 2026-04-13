@{
    ModuleVersion     = '1.0.0'
    GUID              = 'a3f7e2d1-bc84-4f59-9e31-0d7c6a852f4e'
    Author            = 'StackOps HQ'
    CompanyName       = 'StackOps HQ'
    Description       = 'Ghostbit CLI — create and view end-to-end encrypted pastes from PowerShell'
    PowerShellVersion = '7.0'
    RootModule        = 'Ghostbit.psm1'

    FunctionsToExport = @(
        'New-GhostbitPaste'
        'Get-GhostbitPaste'
        'Invoke-GhostbitConfig'
    )
    AliasesToExport   = @('gb', 'gbv')
    CmdletsToExport   = @()
    VariablesToExport = @()

    PrivateData = @{
        PSData = @{
            Tags       = @('paste', 'clipboard', 'ghostbit', 'encrypted', 'e2e')
            ProjectUri = 'https://github.com/stackopshq/ghostbit'
            LicenseUri = 'https://github.com/stackopshq/ghostbit/blob/main/LICENSE'
        }
    }
}
