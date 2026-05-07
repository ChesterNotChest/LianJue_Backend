$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$experimentDir = Split-Path -Parent $scriptDir
$samplesDir = Join-Path $experimentDir "samples"
$reportsDir = Join-Path $experimentDir "reports"
$outputsDir = Join-Path $experimentDir "outputs"
$summaryPath = Join-Path $outputsDir "profile_asset_validation_summary.json"

if (!(Test-Path $outputsDir)) {
    New-Item -ItemType Directory -Path $outputsDir | Out-Null
}

$issues = New-Object System.Collections.Generic.List[string]
$checkedFiles = New-Object System.Collections.Generic.List[string]

function Add-Issue {
    param([string]$Message)
    $issues.Add($Message) | Out-Null
}

function Require-File {
    param([string]$Path)
    if (!(Test-Path $Path)) {
        Add-Issue "missing file: $Path"
        return $false
    }
    $checkedFiles.Add($Path) | Out-Null
    return $true
}

function Load-JsonFile {
    param([string]$Path)
    try {
        return Get-Content -Raw -Encoding UTF8 $Path | ConvertFrom-Json
    } catch {
        Add-Issue "invalid json: $Path"
        return $null
    }
}

$requiredSampleFiles = @(
    "dataset_index.json",
    "syllabus_base_dataset.json",
    "question_bank_dataset.json",
    "dialogue_profile_dataset.json",
    "learning_records_dataset.json",
    "answer_records_dataset.json",
    "resource_usage_dataset.json",
    "personal_syllabus_dataset.json",
    "profile_input_bundles.json",
    "ablation_bundles.json",
    "edge_case_bundles.json",
    "stability_eval_set.json",
    "manual_review_set.json"
)

$requiredReportFiles = @(
    "data_availability_matrix.json",
    "data_availability_assessment.md"
)

foreach ($name in $requiredSampleFiles) {
    [void](Require-File (Join-Path $samplesDir $name))
}
foreach ($name in $requiredReportFiles) {
    [void](Require-File (Join-Path $reportsDir $name))
}

$sampleJsonFiles = Get-ChildItem $samplesDir -File -Filter *.json | Sort-Object Name
$sampleData = @{}
foreach ($file in $sampleJsonFiles) {
    $loaded = Load-JsonFile $file.FullName
    if ($null -ne $loaded) {
        $sampleData[$file.Name] = $loaded
    }
}

$matrixPath = Join-Path $reportsDir "data_availability_matrix.json"
$availability = $null
if (Test-Path $matrixPath) {
    $availability = Load-JsonFile $matrixPath
}

$bundleIds = @{}
$bundleRefs = @{}
if ($sampleData.ContainsKey("profile_input_bundles.json")) {
    $bundles = @($sampleData["profile_input_bundles.json"].bundles)
    if ($bundles.Count -lt 4) {
        Add-Issue "expected at least 4 profile bundles"
    }
    foreach ($bundle in $bundles) {
        $bundleIds[$bundle.bundle_id] = $true
        if (-not $bundle.graph_name -and $sampleData["profile_input_bundles.json"].graph_name -ne "RAG") {
            Add-Issue "profile_input_bundles graph_name should be RAG"
        }
        foreach ($field in @("dialogue_text", "learning_records", "answer_records", "resource_usage", "expected_profile_labels", "references")) {
            if ($null -eq $bundle.$field) {
                Add-Issue "bundle $($bundle.bundle_id) missing field $field"
            }
        }
        $bundleRefs[$bundle.bundle_id] = $bundle.references
    }
}

$dialogueIds = @{}
if ($sampleData.ContainsKey("dialogue_profile_dataset.json")) {
    foreach ($item in @($sampleData["dialogue_profile_dataset.json"].samples)) {
        $dialogueIds[$item.sample_id] = $true
    }
}
$learningIds = @{}
if ($sampleData.ContainsKey("learning_records_dataset.json")) {
    foreach ($item in @($sampleData["learning_records_dataset.json"].samples)) {
        $learningIds[$item.sample_id] = $true
    }
}
$answerIds = @{}
if ($sampleData.ContainsKey("answer_records_dataset.json")) {
    foreach ($item in @($sampleData["answer_records_dataset.json"].samples)) {
        $answerIds[$item.sample_id] = $true
    }
}
$resourceIds = @{}
if ($sampleData.ContainsKey("resource_usage_dataset.json")) {
    foreach ($item in @($sampleData["resource_usage_dataset.json"].samples)) {
        $resourceIds[$item.sample_id] = $true
    }
}
$personalIds = @{}
if ($sampleData.ContainsKey("personal_syllabus_dataset.json")) {
    foreach ($item in @($sampleData["personal_syllabus_dataset.json"].profiles)) {
        $personalIds[$item.sample_id] = $true
    }
}

foreach ($bundleId in $bundleRefs.Keys) {
    $refs = $bundleRefs[$bundleId]
    if (-not $dialogueIds.ContainsKey($refs.dialogue_sample_id)) {
        Add-Issue "bundle $bundleId references missing dialogue sample $($refs.dialogue_sample_id)"
    }
    if (-not $learningIds.ContainsKey($refs.learning_sample_id)) {
        Add-Issue "bundle $bundleId references missing learning sample $($refs.learning_sample_id)"
    }
    if (-not $answerIds.ContainsKey($refs.answer_sample_id)) {
        Add-Issue "bundle $bundleId references missing answer sample $($refs.answer_sample_id)"
    }
    if (-not $resourceIds.ContainsKey($refs.resource_sample_id)) {
        Add-Issue "bundle $bundleId references missing resource sample $($refs.resource_sample_id)"
    }
    if (-not $personalIds.ContainsKey($refs.personal_syllabus_sample_id)) {
        Add-Issue "bundle $bundleId references missing personal syllabus sample $($refs.personal_syllabus_sample_id)"
    }
}

if ($sampleData.ContainsKey("ablation_bundles.json")) {
    $ablation = $sampleData["ablation_bundles.json"]
    $requiredVariants = @($ablation.required_variants)
    foreach ($row in @($ablation.case_matrix)) {
        if (-not $bundleIds.ContainsKey($row.base_bundle_id)) {
            Add-Issue "ablation references missing base bundle $($row.base_bundle_id)"
        }
        $seen = @{}
        foreach ($variantCase in @($row.variants)) {
            $seen[$variantCase.variant] = $true
        }
        foreach ($variant in $requiredVariants) {
            if (-not $seen.ContainsKey($variant)) {
                Add-Issue "ablation row $($row.base_bundle_id) missing variant $variant"
            }
        }
    }
}

$edgeCaseIds = @{}
if ($sampleData.ContainsKey("edge_case_bundles.json")) {
    $edge = $sampleData["edge_case_bundles.json"]
    $templateIds = @{}
    foreach ($template in @($edge.templates)) {
        $templateIds[$template.template_id] = $true
    }
    foreach ($case in @($edge.cases)) {
        $edgeCaseIds[$case.case_id] = $true
        if (-not $bundleIds.ContainsKey($case.base_bundle_id)) {
            Add-Issue "edge case $($case.case_id) references missing base bundle $($case.base_bundle_id)"
        }
        if (-not $templateIds.ContainsKey($case.template_id)) {
            Add-Issue "edge case $($case.case_id) references missing template $($case.template_id)"
        }
    }
    if (@($edge.cases).Count -lt 6) {
        Add-Issue "expected at least 6 edge cases"
    }
}

if ($sampleData.ContainsKey("stability_eval_set.json")) {
    $stability = $sampleData["stability_eval_set.json"]
    foreach ($target in @($stability.targets)) {
        if ($target.source_type -eq "profile_bundle" -and -not $bundleIds.ContainsKey($target.source_id)) {
            Add-Issue "stability target $($target.target_id) references missing bundle $($target.source_id)"
        }
        if ($target.source_type -eq "edge_case" -and -not $edgeCaseIds.ContainsKey($target.source_id)) {
            Add-Issue "stability target $($target.target_id) references missing edge case $($target.source_id)"
        }
    }
}

if ($sampleData.ContainsKey("manual_review_set.json")) {
    $manual = $sampleData["manual_review_set.json"]
    foreach ($item in @($manual.items)) {
        if ($item.source_type -eq "profile_bundle" -and -not $bundleIds.ContainsKey($item.source_id)) {
            Add-Issue "manual review item $($item.review_id) references missing bundle $($item.source_id)"
        }
        if ($item.source_type -eq "edge_case" -and -not $edgeCaseIds.ContainsKey($item.source_id)) {
            Add-Issue "manual review item $($item.review_id) references missing edge case $($item.source_id)"
        }
    }
}

$availabilityStatuses = @{}
if ($null -ne $availability) {
    foreach ($item in @($availability.items)) {
        $availabilityStatuses[$item.field] = $item.status
    }
    foreach ($field in @("syllabus", "personal_syllabus", "history_dialogue", "dialogue_text", "learning_goal", "learning_records", "answer_records", "resource_usage", "expected_profile_labels", "learning_profile_runtime")) {
        if (-not $availabilityStatuses.ContainsKey($field)) {
            Add-Issue "availability matrix missing field $field"
        }
    }
}

$summary = [ordered]@{
    generated_at = (Get-Date).ToString("s")
    checked_sample_file_count = $sampleJsonFiles.Count
    checked_report_file_count = $requiredReportFiles.Count
    profile_bundle_count = $bundleIds.Count
    edge_case_count = $edgeCaseIds.Count
    issue_count = $issues.Count
    issues = @($issues)
    availability_status_counts = [ordered]@{
        available = @($availability.items | Where-Object { $_.status -eq "available" }).Count
        partial = @($availability.items | Where-Object { $_.status -eq "partial" }).Count
        missing = @($availability.items | Where-Object { $_.status -eq "missing" }).Count
    }
}

$summary | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 $summaryPath

if ($issues.Count -gt 0) {
    Write-Output "Validation failed. Summary written to $summaryPath"
    foreach ($issue in $issues) {
        Write-Output " - $issue"
    }
    exit 1
}

Write-Output "Validation passed. Summary written to $summaryPath"
Write-Output "Profile bundles: $($bundleIds.Count)"
Write-Output "Edge cases: $($edgeCaseIds.Count)"
