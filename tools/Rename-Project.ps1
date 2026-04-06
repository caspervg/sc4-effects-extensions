param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z][A-Za-z0-9_]*$')]
    [string]$ProjectName
)

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot

function ConvertTo-KebabCase {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    return ($Value -replace '([a-z0-9])([A-Z])', '$1-$2').ToLowerInvariant()
}

$oldNames = @(
    'SC4TemplateDll',
    'SC4EffectsExtensions'
) | Where-Object { $_ -ne $ProjectName } | Select-Object -Unique
$oldSlugs = $oldNames | ForEach-Object { ConvertTo-KebabCase $_ }
$newSlug = ConvertTo-KebabCase $ProjectName

$extensions = @(
    '*.txt',
    '*.md',
    '*.json',
    '*.yml',
    '*.yaml',
    '*.cmake',
    'CMakeLists.txt',
    '*.cpp',
    '*.hpp',
    '*.h',
    '*.def',
    '*.ini',
    '*.ps1'
)

$searchPaths = @(
    (Join-Path $root '.github'),
    (Join-Path $root 'cmake'),
    (Join-Path $root 'dist'),
    (Join-Path $root 'src'),
    (Join-Path $root 'tools'),
    (Join-Path $root 'CMakeLists.txt'),
    (Join-Path $root 'CMakePresets.json'),
    (Join-Path $root 'README.md'),
    (Join-Path $root 'vcpkg.json')
)

$filesToUpdate = foreach ($path in $searchPaths) {
    if (-not (Test-Path -LiteralPath $path)) {
        continue
    }

    $item = Get-Item -LiteralPath $path
    if ($item.PSIsContainer) {
        Get-ChildItem -LiteralPath $path -Recurse -File -Include $extensions
    }
    else {
        $item
    }
}

$utf8NoBom = [System.Text.UTF8Encoding]::new($false)

$filesToUpdate | Select-Object -Unique FullName | ForEach-Object {
    if ($_.FullName -eq $PSCommandPath) {
        return
    }

    $content = [System.IO.File]::ReadAllText($_.FullName)
    $updated = $content

    foreach ($oldName in $oldNames) {
        $updated = $updated.Replace($oldName, $ProjectName)
    }

    foreach ($oldSlug in $oldSlugs) {
        $updated = $updated.Replace($oldSlug, $newSlug)
    }

    if ($updated -cne $content) {
        [System.IO.File]::WriteAllText($_.FullName, $updated, $utf8NoBom)
    }
}

$renameSearchPaths = @(
    (Join-Path $root 'dist'),
    (Join-Path $root 'src\dll')
)

foreach ($basePath in $renameSearchPaths) {
    if (-not (Test-Path -LiteralPath $basePath)) {
        continue
    }

    Get-ChildItem -LiteralPath $basePath -File | ForEach-Object {
        $newLeaf = $_.Name

        foreach ($oldName in $oldNames) {
            $newLeaf = $newLeaf.Replace($oldName, $ProjectName)
        }

        if ($newLeaf -cne $_.Name) {
            Rename-Item -LiteralPath $_.FullName -NewName $newLeaf
        }
    }
}

Write-Host "Renamed template identifiers to $ProjectName"
