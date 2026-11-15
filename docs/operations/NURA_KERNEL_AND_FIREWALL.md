# nura — kernel and host firewall

**Status:** open gap. The phone runs a Wi-Fi kernel **without `nf_tables`**, so
there is no host firewall. Services bind `127.0.0.1` and ingress is the
Cloudflare tunnel, but that is a single boundary with no defense in depth.

## Current state

| Image | Features | Entry |
|---|---|---|
| `/boot/vmlinuz-s10wifi` | PCIe + brcmfmac, charger, GPU, watchdog — **no `CONFIG_NF_TABLES`** | `s10wifi.conf` (default) |
| `/boot/vmlinuz` | `nf_tables` + `rtl8xxxu` — **no PCIe driver**, so no internal Wi-Fi | `pmos.conf`, `pmos-gadget.conf`, `pmos-host.conf` |

- `modprobe nf_tables` fails with `Exec format error`: the `nf_tables.ko` on disk
  was built by a different kernel build (same `7.2.0-rc2` string, different
  config), so it cannot load into the running image.
- `nftables` userspace is installed; `nftables.service` is masked because the
  kernel side does not exist.
- Ports: 8765 (client), 8766 (provider), 8967 (MAF), all bound to `127.0.0.1`.
  Public access is through the quick tunnels, which have no access layer.

## Risk

- any process that binds `0.0.0.0`, any future port, or any compromised local
  service is unfiltered;
- no egress policy: a compromised process can reach anything;
- the tunnel is the only boundary, and Cloudflare Access is not configured;
- backup and recovery assume the host is not compromised.

## Fix — rebuild the Wi-Fi kernel with `nf_tables`

1. Build the community kernel source (`tannerbruhn/exynos-9820-mainline-linux`,
   branch `main`) using its `s10-wifi.config` plus:

   ```text
   CONFIG_NF_TABLES=m
   CONFIG_NF_TABLES_INET=m
   CONFIG_NFT_CT=m
   CONFIG_NFT_META=m
   CONFIG_NFT_PAYLOAD=m
   CONFIG_NFT_CMP=m
   ```

   Merge with `scripts/kconfig/merge_config.sh -m .config …` then
   `make olddefconfig`; anything resolved by dependencies is acceptable as long
   as `nf_tables` and the expressions above end up set.

2. Produce `Image` and the module tree; install as a **one-shot trial entry**
   (the `+1` mechanism used by the Wi-Fi release), leaving `s10wifi.conf` as the
   fallback.

3. Verify on the trial boot:

   ```sh
   modprobe nf_tables && nft list ruleset
   ip link show wlan0          # Wi-Fi must still work
   ```

4. Minimal policy, default deny:

   ```text
   input:   policy drop; accept lo, ct established/related,
            dhcp+dns on wlan0, ssh on tailscale0 and wlan0 (LAN only)
   forward: drop
   output:  accept (tighten later)
   ```

5. Enable `nftables.service`, persist the ruleset, reboot, re-verify.

## Acceptance

- `nf_tables` loads and `nft list ruleset` shows the policy;
- 8765/8766/8967 reachable on `127.0.0.1` and through the tunnels;
- SSH works over USB and Tailscale;
- the policy survives a reboot;
- Wi-Fi still connects at boot.

## Rollback

Boot `s10wifi.conf` (current image) and mask `nftables.service` again. The trial
entry disappears after one boot, and the current image remains untouched.

## Notes

- The same rebuild can re-add `rtl8xxxu` for the USB dongle, but the port still
  has no VBUS regulator, so the dongle depends on a hub that back-feeds power.
- `high` priority is the promotion train; this item is P1 **because it is host
  security on the production device**, not because it blocks a feature.
