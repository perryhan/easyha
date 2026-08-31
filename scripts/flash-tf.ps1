# EasyHA H618 盒子刷机工具（Windows）
# 用法：双击 scripts\双击刷机.bat，或 powershell -ExecutionPolicy Bypass -File .\flash-tf.ps1
# 作用：列出磁盘 → 选 TF 卡 → 解压 xz → 整盘写入
# 安全：只写你选择的磁盘；系统盘会要求输入 YES 二次确认

$ErrorActionPreference = "Stop"
$Img = Join-Path $PSScriptRoot "..\out\haos_h618-box-18.3.dev0.img.xz"
$Raw = Join-Path $env:TEMP "easyha-h618.img"

Write-Host "=== EasyHA H618 刷机工具 ===" -ForegroundColor Cyan

# 1) 镜像检查
if (-Not (Test-Path $Img)) {
    Write-Host "[X] 镜像不存在: $Img" -ForegroundColor Red
    exit 1
}
Write-Host ("[1/5] 镜像 OK: {0} MB" -f [math]::Round((Get-Item $Img).Length/1MB,1))

# 2) 列磁盘
Write-Host "`n[2/5] 磁盘列表："
$disks = @(Get-CimInstance Win32_DiskDrive | Sort-Object Index)
$i = 0
foreach ($d in $disks) {
    $isRemovable = ($d.MediaType -match "Removable")
    $mark = "[TF卡候选]"
    if (-Not $isRemovable) { $mark = "[固定盘-勿选]" }
    Write-Host ("  {0}  {1}  {2}GB  {3}" -f $i, $mark, [math]::Round($d.Size/1GB,1), $d.Model)
    $i++
}

# 3) 选择
$sel = Read-Host "`n输入 TF 卡编号"
$idx = 0
if (-Not [int]::TryParse($sel, [ref]$idx) -or $idx -ge $disks.Count) {
    Write-Host "[X] 编号无效"; exit 1
}
$target = $disks[$idx]
if ($target.MediaType -notmatch "Removable") {
    $confirm = Read-Host "这不是可移动磁盘！写入将清空整盘，输入 YES 确认"
    if ($confirm -ne "YES") { Write-Host "已取消"; exit 0 }
}
Write-Host ("目标: \\.\PHYSICALDRIVE{0} ({1})" -f $target.Index, $target.Model)

# 4) 解压 xz（Windows 自带 tar）
Write-Host "`n[4/5] 解压镜像（约 1~3 分钟）..." -ForegroundColor Yellow
if (Test-Path $Raw) { Remove-Item $Raw -Force }
& tar -xJf $Img -C $env:TEMP
if ($LASTEXITCODE -ne 0 -or -Not (Test-Path $Raw)) {
    Write-Host "[X] 解压失败（检查 C 盘剩余空间需 >1.5GB）"; exit 1
}
Write-Host ("解压完成: {0} MB" -f [math]::Round((Get-Item $Raw).Length/1MB,1))

# 5) 写盘（diskpart clean + 流式写入）
Write-Host "`n[5/5] 写入 TF 卡（约 5~15 分钟，请勿拔卡/休眠）..." -ForegroundColor Yellow
$clean = "select disk $($target.Index)`nclean`nexit"
$clean | diskpart | Out-Null

$fs = [IO.File]::OpenRead($Raw)
$fo = [IO.File]::Open("\\.\PHYSICALDRIVE" + $target.Index, 'Open', 'Write', 'Write')
$buf = New-Object byte[] (16 * 1024 * 1024)
$total = $fs.Length
$done = 0
$sw = [Diagnostics.Stopwatch]::StartNew()
while (($n = $fs.Read($buf, 0, $buf.Length)) -gt 0) {
    $fo.Write($buf, 0, $n)
    $done += $n
    if (($done / (16MB)) % 8 -eq 0) {
        Write-Progress -Activity "写卡" -Status ("{0}%" -f [math]::Round($done*100/$total)) -PercentComplete ($done*100/$total)
    }
}
$fs.Close(); $fo.Close()
$sw.Stop()
Write-Progress -Activity "写卡" -Completed
Remove-Item $Raw -Force -ErrorAction SilentlyContinue

Write-Host ("`n完成！耗时 {0:mm\分ss\秒}" -f $sw.Elapsed) -ForegroundColor Green
Write-Host "`n下一步："
Write-Host "  1. 拔卡，插入盒子 TF 卡槽"
Write-Host "  2. 盒子接网线（与电脑同一路由器）"
Write-Host "  3. 上电，等 3~5 分钟"
Write-Host "  4. 浏览器打开 http://homeassistant.local:8123（或路由器后台找新设备）"
Write-Host "`n判定：起来 = 点亮成功（告诉我，继续装 easy-setup 走全流程）"
Write-Host "      没起来 = DRAM 参数问题（需要接串口，我给你接线图）"
