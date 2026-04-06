param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z][A-Za-z0-9_]*$')]
    [string]$ProjectName
)

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$oldName = 'SC4TemplateDll'
$oldSlug = 'sc4-dll-template'
$newSlug = ($ProjectName -replace '([a-z0-9])([A-Z])', '$1-$2').ToLowerInvariant()

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

Get-ChildItem -Path $root -Recurse -File -Include $extensions | ForEach-Object {
    $content = Get-Content $_.FullName -Raw
    $updated = $content.Replace($oldName, $ProjectName).Replace($oldSlug, $newSlug)
    if ($updated -ne $content) {
        Set-Content -Path $_.FullName -Value $updated -NoNewline
    }
}

$renameTargets = @(
    (Join-Path $root 'dist\SC4TemplateDll.ini'),
    (Join-Path $root 'src\dll\SC4TemplateDll.def'),
    (Join-Path $root 'src\dll\SC4TemplateDllDirector.hpp'),
    (Join-Path $root 'src\dll\SC4TemplateDllDirector.cpp')
)

foreach ($path in $renameTargets) {
    if (Test-Path $path) {
        $leaf = Split-Path -Leaf $path
        $newLeaf = $leaf.Replace($oldName, $ProjectName)
        if ($newLeaf -ne $leaf) {
            Rename-Item -LiteralPath $path -NewName $newLeaf
        }
    }
}

Write-Host "Renamed template identifiers to $ProjectName"
