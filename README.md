# 为锐捷 RG-X30E 编译 FanchmWrt

针对设备：**锐捷 X30E（RG-X30E）**，MT7981B + 128MB SPI-NAND（NMBM）+ 256MB DDR3，原厂 ReyeeOS 1.380.x。

## 一、先说结论

| 检查项 | 结果 |
|---|---|
| fanchmwrt 仓库性质 | OpenWrt 完整源码树 fork（含 `package/fcm/` 自研 fwx 套件 + `fanchmwrt-packages` feed） |
| 默认分支 | `fanchmwrt-25.12.6`，内核 **6.12**，`version` = r33311 |
| 官方是否支持 X30E | **不支持**。`target/linux/mediatek/image/filogic.mk` 里只有 `ruijie_rg-x60-pro`（MT7986） |
| OpenWrt 主线是否支持 | **也不支持**。master / 24.10 / 25.12 三个分支都只有 `ruijie_rg-x60-pro` |
| X30E 的现成移植来源 | `RuijieNetworksCommunity/MT798X-6.6-24.10`（默认分支 `mt798x-mt799x-6.6-mtwifi`，kernel 6.6） |

所以「编译」这个任务 99% 的工作量是**把机型支持移植进 25.12 的树**，剩下的才是 `make`。本目录就是把这套移植和云编译流水线做好。

## 二、移植了什么

X30E 需要补的地方一共 5 处（`apply-port.py` 全自动完成，幂等）：

| # | 文件 | 内容 |
|---|---|---|
| 1 | `target/linux/mediatek/dts/mt7981b-ruijie-rg-x30e*.dts[i]` | 4 个新 DTS：公共 dtsi + 3 种分区布局 |
| 2 | `target/linux/mediatek/image/filogic.mk` | 注册 3 个 device profile |
| 3 | `filogic/base-files/etc/board.d/02_network` | 网口映射 `lan1 lan2 lan3 + wan`、MAC 从 `product_info` 分区读 |
| 4 | `filogic/base-files/etc/hotplug.d/ieee80211/11_fix_wifi_mac` | 两个射频 MAC = 标签 MAC +2 / +3 |
| 5 | `filogic/base-files/lib/upgrade/platform.sh` | sysupgrade 走 tar 镜像（`ustar` magic 校验） |

**DTS 的 6.6 → 6.12 适配点**（社区版是 24.10/6.6，直接抄会编不过）：

- `#include "mt7981.dtsi"` → `"mt7981b.dtsi"`
- `memory { }` → `memory@40000000 { device_type = "memory"; }`
- **删掉 `&hnat { mtketh-wan/lan ... }`** —— 6.12 树里没有这个节点（上游把 HNAT 补丁去掉了，本树用 `shortcut-fe` 做加速），保留会报 `&hnat not found`
- `leds` 用 `function`/`color` 代替废弃的 `label = "green:status"`
- `spi_nand: flash@0` → `spi_nand@0`
- `&mdio { switch@1f }` → `&mdio_bus`（6.12 由补丁 `117-complete-mt7981b-dtsi.patch` 提供该标签）
- pinctrl 用 `MTK_DRIVE_8mA` / `bias-disable`
- ubi 分区加 `compatible = "linux,ubi"`（与本树 `h3c_magic-nx30-pro-stock` 写法一致）

**三种分区布局**（都编进同一个 profile 列表，按需选）：

| profile | ubi 容量 | 适用 |
|---|---|---|
| `ruijie_rg-x30e-stock` | 34.5MB | **默认推荐**，不动原厂 u-boot，保留 ubi2/backup |
| `ruijie_rg-x30e-firmware2` | 34.5MB | 原厂从第二个槽启动的机器 |
| `ruijie_rg-x30e` | 111.5MB | **必须先刷第三方 u-boot（bl-mt798x 的 X30E FIP）**，否则刷了起不来 |

## 三、云编译（GitHub Actions）

无需本地环境，也不需要 WSL。

1. 在 GitHub 新建一个 **私有** 仓库（Fork fanchmwrt 主仓会很大，不要 fork）。
2. 把本目录整体推上去（保持 `.github/workflows/`、`files/`、`configs/`、`apply-port.py` 在仓库根目录）。

   ```bash
   cd fanchmwrt-x30e
   git init && git add -A && git commit -m "build fanchmwrt for Ruijie RG-X30E"
   git branch -M main
   git remote add origin git@github.com:<你的账号>/<仓库名>.git
   git push -u origin main
   ```
3. 仓库 → Actions → `build-fanchmwrt-x30e` → Run workflow：
   - `upstream_ref` 保持 `fanchmwrt-25.12.6`（想跟新就改成 `fanchmwrt-25.12.4` 等已有分支）
   - `device` 选 `ruijie_rg-x30e-stock`
4. 约 2~4 小时后（首次含工具链）在 run 页面下载 artifact，`*.bin` 就是固件。

产物命名规则同 OpenWrt：`...-squashfs-factory.bin`（首刷）、`...-squashfs-sysupgrade.bin`（升级）。单次 build 只编所选机型，另一个布局要用再跑一次 workflow。

> 编译时间/磁盘:GitHub 托管 runner 4 核、超时上限 6 小时，单机型通常 2.5~3.5 小时，够用。workflow 里已包含释放磁盘、`make download` 预下载、`make -j` 失败回退 `make -j1 V=s`。

## 四、刷机

### 前置：备份原厂分区（已有 root shell，务必先做）

```sh
cat /proc/mtd
for p in BL2 u-boot-env Factory FIP FIP2 product_info; do
  n=$(grep "\"$p\"" /proc/mtd | cut -d: -f1)
  dd if=/dev/$n of=/tmp/$p.bak
  echo "$p -> /tmp/$p.bak"
done
# 用 scp -P 54133 全部拉回本地保存
```

### 路线 A（推荐）：先落 OpenWrt 24.10，再升级到 FanchmWrt

1. 先刷社区已验证可启动的 `RuijieNetworksCommunity/MT798X-6.6-24.10` 的 X30E `factory.bin`（恩山教程同款，刷完默认 `192.168.1.1`、root 空密码）。
2. 在 OpenWrt 里用 LuCI「备份/刷写固件」上传本 workflow 产出的 `sysupgrade.bin`，不保留配置。
3. 首次启动约 1~2 分钟，地址 `192.168.1.1`。

这条路的好处：万一 FanchmWrt 起不来，还能刷回社区固件，不会变砖。

### 路线 B（直接）：原厂 root shell 里写 ubi

```sh
# 把 factory.bin 传到 /tmp
mtd write /tmp/fanchmwrt-...-factory.bin ubi
sync && reboot
```

只在路线 A 走通过之后再用，直接写原厂 ubi 出问题就得拆机上 TTL。

## 五、风险与不确定点（诚实标注）

1. **原厂 u-boot 的 bootargs 未实测**。社区 24.10 移植沿用 `KERNEL_IN_UBI + sysupgrade-tar`，本移植保持同一约定，最坏情况是内核起来但找不到 rootfs（表现为串口停在 `Waiting for root device`）。真出问题需要 TTL 串口（115200 8N1）+ `mtk_uartboot` 救砖。
2. **34.5MB rootfs 是否够装 fwx 全家桶 + WiFi 固件**没有实测。若编出来提示 `check-size` 超限，把 `configs/packages.config` 里 `luci-app-fwx-feature`、`-fastnat`、`ttyd`、`e2fsprogs` 去掉即可。
3. **25.12 的 `linux,ubi` 语义**（无 `volumes` 子节点）已在同树 `h3c_magic-nx30-pro-stock` 上验证过写法，但 X30E 没跑过。
4. **MAC 读取依赖 `product_info` 分区里的 `ethaddr` 键**。若开起来后 LAN/WAN MAC 全 00，用 `strings /dev/mtd7 | grep -i eth` 确认键名，再改 `02_network` 里的 `mtd_get_mac_ascii product_info ethaddr`。
5. **备选方案**：把 `upstream_ref` 换成 `fanchmwrt-24.10.4`，此时 X30E 社区 DTS 可**逐字照抄**（同为 kernel 6.6），移植风险最低，但 `apply-port.py` 的锚点不适用，需要手工放 DTS 并按社区版 filogic.mk 加设备块。

## 六、本地/自有服务器编译（备用）

```bash
sudo apt-get install -y build-essential clang flex bison g++ gawk gcc-multilib g++-multilib \
  gettext git libncurses-dev libssl-dev python3-distutils rsync unzip zlib1g-dev file wget
git clone --depth 1 -b fanchmwrt-25.12.6 https://github.com/fanchmwrt/fanchmwrt openwrt
python3 apply-port.py openwrt
cd openwrt
cat ../configs/target.config >> .config
make defconfig
cat ../configs/packages.config >> .config
make defconfig
make -j$(nproc) download
make -j$(nproc)
# 产物在 bin/targets/mediatek/filogic/
```

首次全量编译需要 30~50GB 磁盘、4 核约 3 小时；`make menuconfig` 里机型路径是
`Target System → MediaTek → Filogic → Ruijie RG-X30E (stock layout)`。
