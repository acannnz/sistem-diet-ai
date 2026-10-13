# Upload aplikasi ke VPS dari laptop.
#   Pertama kali : .\deploy\deploy.ps1 -First   (upload kode + .env + database, lalu ikuti RUNBOOK Fase 2)
#   Update kode  : .\deploy\deploy.ps1          (upload kode lalu jalankan deploy.sh di server)
param([switch]$First)

$ErrorActionPreference = "Stop"
$VpsUser = "ubuntu"
$VpsHost = "43.134.133.21"
$Target = "${VpsUser}@${VpsHost}"
$Root = Split-Path -Parent $PSScriptRoot

Set-Location $Root
& "$Root\.venv\Scripts\python.exe" "$Root\deploy\build_zip.py"
if ($LASTEXITCODE -ne 0) { throw "Gagal membuat zip" }

Write-Host "==> Upload kode ke $Target"
scp "$Root\dist\sistem-diet.zip" "${Target}:/home/ubuntu/sistem-diet.zip"
if ($LASTEXITCODE -ne 0) { throw "Upload gagal" }

if ($First) {
    Write-Host "==> Upload .env dan database (pertama kali saja)"
    scp "$Root\.env" "${Target}:/home/ubuntu/sistem-diet.env"
    scp "$Root\data\diet.db" "${Target}:/home/ubuntu/sistem-diet.db"
    if ($LASTEXITCODE -ne 0) { throw "Upload gagal" }
    ssh $Target "chmod 600 /home/ubuntu/sistem-diet.env"
    Write-Host ""
    Write-Host "Upload selesai. Lanjutkan RUNBOOK Fase 2 di server."
} else {
    Write-Host "==> Jalankan deploy di server"
    ssh -t $Target "sudo bash /var/www/sistem-diet/deploy/server/deploy.sh"
}
