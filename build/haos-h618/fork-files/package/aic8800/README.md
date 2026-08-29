# ============================================================
# AIC8801 WiFi 驱动包（Buildroot external package）
# 放入 fork: buildroot-external/package/aic8800/{Config.in, aic8800.mk}
# 并在 buildroot-external/Config.in 与 external.mk 里登记。
#
# ⚠️ 实勘事实（见 BOARD-FINDINGS.md）：本板 AIC8801 为 **USB 形态**，
#    ID a69c:5721，当前枚举为 MSC（U 盘模式）。驱动须支持 USB 模式切换
#    （MSC → WLAN），出 wlan0 后才能开热点。
#
# 驱动源候选（择一，量产前统一收口到私有仓）：
#  - https://github.com/goecho/aic8800_linux_drvier   （USB + SDIO 双支持）
#  - https://github.com/LYU4662/aic8800-sdio-linux-1.0（仅 SDIO）
#  - gitee 镜像：Im-eks-dev/aic8800-sdk、wang-zhulin/aic8800-sdk
#  - 板卡厂交付 SDK（首选，固件配套最稳）
#  - 主线动向：AIC8801/DC/D80 SDIO FullMAC 驱动已发 RFC 补丁（LWN 1083998），
#    合入主线后本包可删。
#
# ⚠️ 已知坑：AIC8800D80 系旧固件 2.4G AP 模式静默失效（不发包）——
#    用最新固件并按 WIFI-CHIP-CHECKLIST.md 实测 AP 模式。
# ============================================================
