# ============================================================
# AIC8800/8801 WiFi 驱动 —— Buildroot 包（模板，USB 形态）
# ❗TODO：AIC 驱动不在主线。把 SDK 推到你们的私有 git 仓后替换
#        AIC8800_SITE / AIC8800_SOURCE。SDK 目录形如：
#          aic8800/aic8800_bsp/        (总线/平台层，含 USB 模式切换)
#          aic8800/aic8800_fdrv/       (cfg80211 驱动，Kbuild 在此)
#          aic8800/firmware/           (固件 → /lib/firmware/aic8800*)
# 本板 AIC8801 走 USB（a69c:5721），启用 CONFIG_AIC8800_USB；
# 若量产换 SDIO 模组则改启用 SDIO 变体。
# ============================================================

AIC8800_VERSION = 1.0
AIC8800_SITE = $(call github,your-org,aic8800-sdk,$(AIC8800_VERSION))
AIC8800_LICENSE = GPL-2.0
AIC8800_DEPENDENCIES = linux

AIC8800_MODULE_SUBDIRS = aic8800_bsp aic8800_fdrv

define AIC8800_LINUX_CONFIG_FIXUPS
	$(call KCONFIG_ENABLE_OPT,CONFIG_WLAN)
	$(call KCONFIG_ENABLE_OPT,CONFIG_CFG80211)
	$(call KCONFIG_ENABLE_OPT,CONFIG_MAC80211)
	$(call KCONFIG_ENABLE_OPT,CONFIG_USB_SUPPORT)
endef

# USB MSC → WLAN 的模式切换依赖 udev/驱动内逻辑；固件必须与驱动配套
define AIC8800_INSTALL_FIRMWARE
	mkdir -p $(TARGET_DIR)/lib/firmware/aic8800
	cp -r $(@D)/firmware/. $(TARGET_DIR)/lib/firmware/aic8800/
endef
AIC8800_POST_INSTALL_TARGET_HOOKS += AIC8800_INSTALL_FIRMWARE

$(eval $(kernel-module))
$(eval $(generic-package))
