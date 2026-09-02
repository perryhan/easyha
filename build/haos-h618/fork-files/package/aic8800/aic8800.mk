# ============================================================
# AIC8800/8801 USB WiFi 驱动 —— buildroot 内核模块包
# 源码: aic8800dc-linux-patched（Radxa 6.12+ 兼容补丁版，随本包分发）
# 固件: fw/aic8800D80 → /lib/firmware/aic8800D80
# 硬件: 本盒子 AIC8801 为 USB 形态（a69c:5721，上电为 MSC U 盘模式，
#       由 aic_load_fw 完成模式切换），需配合内核 cmdline 的
#       usb-storage.quirks=a69c:5721:u（已在 board cmdline.txt 中）
# ============================================================

AIC8800_VERSION = 1.0
AIC8800_SITE = $(BR2_EXTERNAL_HAOS_PATH)/package/aic8800/src
AIC8800_SITE_METHOD = local
AIC8800_LICENSE = GPL-2.0
AIC8800_DEPENDENCIES = linux

# 两个模块均构建为 .ko；CONFIG_PLATFORM_UBUNTU 分支适配主线内核构建
AIC8800_MODULE_MAKE_OPTS = \
	CONFIG_AIC_LOADFW_SUPPORT=m \
	CONFIG_AIC8800_WLAN_SUPPORT=m \
	CONFIG_PLATFORM_UBUNTU=y \
	USER_EXTRA_CFLAGS="-Wno-error"

define AIC8800_INSTALL_FIRMWARE
	mkdir -p $(TARGET_DIR)/lib/firmware/aic8800D80
	cp -r $(AIC8800_PKGDIR)/firmware/aic8800D80/. $(TARGET_DIR)/lib/firmware/aic8800D80/
endef
AIC8800_POST_INSTALL_TARGET_HOOKS += AIC8800_INSTALL_FIRMWARE

define AIC8800_INSTALL_MODULES_LOAD
	mkdir -p $(TARGET_DIR)/etc/modules-load.d
	printf 'aic_load_fw\naic8800_fdrv\n' > $(TARGET_DIR)/etc/modules-load.d/aic8800.conf
endef
AIC8800_POST_INSTALL_TARGET_HOOKS += AIC8800_INSTALL_MODULES_LOAD

$(eval $(kernel-module))
$(eval $(generic-package))
