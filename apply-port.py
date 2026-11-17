#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把锐捷 RG-X30E 的机型支持移植进 fanchmwrt 源码树。

用法：  python3 apply-port.py /path/to/fanchmwrt
说明：  fanchmwrt 上游（含 OpenWrt 主线）只有 ruijie_rg-x60-pro，没有 X30E。
        本脚本补齐：DTS 4 个文件 + filogic.mk 设备定义 + 02_network 网口/MAC
        + 11_fix_wifi_mac + platform.sh 的 ustar 校验。
        幂等：重复执行不会重复插入。
"""

import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DTS_FILES = [
    "mt7981b-ruijie-rg-x30e.dtsi",
    "mt7981b-ruijie-rg-x30e.dts",
    "mt7981b-ruijie-rg-x30e-stock.dts",
    "mt7981b-ruijie-rg-x30e-firmware2.dts",
]

DEVICE_BLOCK = """
define Device/ruijie_rg-x30e-stock
  DEVICE_VENDOR := Ruijie
  DEVICE_MODEL := RG-X30E (stock layout)
  DEVICE_DTS := mt7981b-ruijie-rg-x30e-stock
  DEVICE_DTS_DIR := ../dts
  UBINIZE_OPTS := -E 5
  BLOCKSIZE := 128k
  PAGESIZE := 2048
  IMAGE_SIZE := 34816k
  KERNEL_IN_UBI := 1
  IMAGES += factory.bin
  IMAGE/factory.bin := append-ubi | check-size $$$$(IMAGE_SIZE)
  IMAGE/sysupgrade.bin := sysupgrade-tar | append-metadata
  DEVICE_PACKAGES := kmod-mt7915e kmod-mt7981-firmware mt7981-wo-firmware
endef
TARGET_DEVICES += ruijie_rg-x30e-stock

define Device/ruijie_rg-x30e-firmware2
  DEVICE_VENDOR := Ruijie
  DEVICE_MODEL := RG-X30E (firmware2 layout)
  DEVICE_DTS := mt7981b-ruijie-rg-x30e-firmware2
  DEVICE_DTS_DIR := ../dts
  UBINIZE_OPTS := -E 5
  BLOCKSIZE := 128k
  PAGESIZE := 2048
  IMAGE_SIZE := 34816k
  KERNEL_IN_UBI := 1
  IMAGES += factory.bin
  IMAGE/factory.bin := append-ubi | check-size $$$$(IMAGE_SIZE)
  IMAGE/sysupgrade.bin := sysupgrade-tar | append-metadata
  DEVICE_PACKAGES := kmod-mt7915e kmod-mt7981-firmware mt7981-wo-firmware
endef
TARGET_DEVICES += ruijie_rg-x30e-firmware2

define Device/ruijie_rg-x30e
  DEVICE_VENDOR := Ruijie
  DEVICE_MODEL := RG-X30E
  DEVICE_DTS := mt7981b-ruijie-rg-x30e
  DEVICE_DTS_DIR := ../dts
  UBINIZE_OPTS := -E 5
  BLOCKSIZE := 128k
  PAGESIZE := 2048
  IMAGE_SIZE := 114688k
  KERNEL_IN_UBI := 1
  IMAGES += factory.bin
  IMAGE/factory.bin := append-ubi | check-size $$$$(IMAGE_SIZE)
  IMAGE/sysupgrade.bin := sysupgrade-tar | append-metadata
  DEVICE_PACKAGES := kmod-mt7915e kmod-mt7981-firmware mt7981-wo-firmware
endef
TARGET_DEVICES += ruijie_rg-x30e
"""

# 02_network 里的 shell case 条目
CASE_ENTRIES = (
    "\truijie,rg-x30e|\\\n"
    "\truijie,rg-x30e-stock|\\\n"
    "\truijie,rg-x30e-firmware2|\\\n"
)


def fail(msg):
    print("[ERROR] " + msg)
    sys.exit(1)


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write(path, data):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(data)


def patch_file(path, old, new, marker, label=None):
    rel = label or os.path.relpath(path)
    text = read(path)
    if marker in text:
        print("  [skip] %s（已包含移植内容）" % rel)
        return
    if text.count(old) != 1:
        fail("%s 锚点不唯一或不存在（命中 %d 次），上游结构可能已变。\n锚点：%r"
             % (rel, text.count(old), old[:160]))
    write(path, text.replace(old, new, 1))
    print("  [ok]   %s" % rel)


def main():
    if len(sys.argv) < 2:
        fail("用法: python3 apply-port.py <fanchmwrt 源码根目录>")
    root = os.path.abspath(sys.argv[1])
    mtk = os.path.join(root, "target/linux/mediatek")
    if not os.path.isdir(mtk):
        fail("%s 不像 OpenWrt/fanchmwrt 源码树（缺 target/linux/mediatek）" % root)

    print("== 1/6 安装 DTS ==")
    dst = os.path.join(mtk, "dts")
    for name in DTS_FILES:
        shutil.copyfile(os.path.join(HERE, "files", name), os.path.join(dst, name))
    print("  [ok]   target/linux/mediatek/dts/ (+%d)" % len(DTS_FILES))

    print("== 2/6 注册设备 ==")
    mk = os.path.join(mtk, "image/filogic.mk")
    patch_file(
        mk,
        "TARGET_DEVICES += ruijie_rg-x60-pro\n",
        "TARGET_DEVICES += ruijie_rg-x60-pro\n" + DEVICE_BLOCK,
        "ruijie_rg-x30e-stock",
        label="target/linux/mediatek/image/filogic.mk",
    )

    bf = os.path.join(mtk, "filogic/base-files")

    print("== 3/6 网口映射 ==")
    patch_file(
        os.path.join(bf, "etc/board.d/02_network"),
        "\ttenbay,wr3000k|\\\n\tteralink,tl3020-256mb)\n",
        CASE_ENTRIES + "\ttenbay,wr3000k|\\\n\tteralink,tl3020-256mb)\n",
        "ruijie,rg-x30e-firmware2|\\\n\ttenbay,wr3000k",
        label="target/linux/mediatek/filogic/base-files/etc/board.d/02_network (lan/wan)",
    )

    print("== 4/6 MAC 地址 ==")
    patch_file(
        os.path.join(bf, "etc/board.d/02_network"),
        "\truijie,rg-x60-pro)\n\t\tlabel_mac=$(mtd_get_mac_ascii product_info ethaddr)\n",
        CASE_ENTRIES + "\truijie,rg-x60-pro)\n"
        "\t\tlabel_mac=$(mtd_get_mac_ascii product_info ethaddr)\n",
        "ruijie,rg-x30e-firmware2|\\\n\truijie,rg-x60-pro)",
        label="target/linux/mediatek/filogic/base-files/etc/board.d/02_network (mac)",
    )

    print("== 5/6 无线 MAC ==")
    patch_file(
        os.path.join(bf, "etc/hotplug.d/ieee80211/11_fix_wifi_mac"),
        "\truijie,rg-x60-pro)\n",
        CASE_ENTRIES + "\truijie,rg-x60-pro)\n",
        "ruijie,rg-x30e-firmware2|\\\n\truijie,rg-x60-pro)",
        label="target/linux/mediatek/filogic/base-files/etc/hotplug.d/ieee80211/11_fix_wifi_mac",
    )

    print("== 6/6 sysupgrade 校验 ==")
    patch_file(
        os.path.join(bf, "lib/upgrade/platform.sh"),
        "\tcreatlentem,clt-r30b1|\\\n",
        "\truijie,rg-x30e|\\\n"
        "\truijie,rg-x30e-stock|\\\n"
        "\truijie,rg-x30e-firmware2)\n"
        "\t\t# tar magic `ustar`\n"
        '\t\tmagic="$(dd if="$1" bs=1 skip=257 count=5 2>/dev/null)"\n'
        "\n"
        '\t\t[ "$magic" != "ustar" ] && {\n'
        '\t\t\techo "Invalid image type."\n'
        "\t\t\treturn 1\n"
        "\t\t}\n"
        "\n"
        "\t\treturn 0\n"
        "\t\t;;\n"
        "\tcreatlentem,clt-r30b1|\\\n",
        "ruijie,rg-x30e-firmware2)\n\t\t# tar magic",
        label="target/linux/mediatek/filogic/base-files/lib/upgrade/platform.sh",
    )

    print("\n移植完成。自查命令：")
    print("  grep -n 'ruijie_rg-x30e' target/linux/mediatek/image/filogic.mk")
    print("  grep -rn 'ruijie,rg-x30e' target/linux/mediatek/filogic/base-files/")


if __name__ == "__main__":
    main()
