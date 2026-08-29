#!/bin/bash
# shellcheck disable=SC2155
# EasyHA H618 公版 · 构建钩子（vim3 模板同构）
# pre_image : 把 boot.scr / DTB / cmdline 填进 boot 分区
# post_image: 产物压缩为 .img.xz

function haos_pre_image() {
    local BOOT_DATA="$(path_boot_dir)"

    cp "${BINARIES_DIR}/boot.scr" "${BOOT_DATA}/boot.scr"
    cp "${BINARIES_DIR}/sun50i-h618-easybox.dtb" "${BOOT_DATA}/sun50i-h618-easybox.dtb"

    cp "${BOARD_DIR}/boot-env.txt" "${BOOT_DATA}/haos-config.txt"
    cp "${BOARD_DIR}/cmdline.txt" "${BOOT_DATA}/cmdline.txt"
}


function haos_post_image() {
    convert_disk_image_xz
}
