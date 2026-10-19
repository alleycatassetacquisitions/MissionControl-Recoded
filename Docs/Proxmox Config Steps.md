# Proxmox Config Steps

Bare-metal Proxmox VE host for Mission Control. Companion services (MCS, AlleycatTV content, GBN, Net Time, HAOS) run as VMs/LXCs on this node — see the matching `* Config Steps.md` docs after the host is up.

Official install reference: [Proxmox VE — Installation](https://pve.proxmox.com/wiki/Installation)

---

## A. Install from ISO

1. Download the current **Proxmox VE ISO** from [proxmox.com/en/downloads](https://www.proxmox.com/en/downloads/) (as of writing: VE **9.x** on Debian **trixie**).
2. Write the ISO to a USB stick (Rufus, balenaEtcher, or `dd` on Linux/macOS).
3. On the target machine: boot from USB (firmware boot menu). Disable Secure Boot only if an older installer refuses to boot; current 8.1+ ISOs support Secure Boot.
4. At the boot menu choose **Install Proxmox VE (Graphical)**. Use **Terminal UI** if the graphical installer fails on the hardware.
5. Accept the EULA, then pick the install disk(s). Default filesystem (**ext4** + LVM → `local-lvm`) is fine for Mission Control. **All data on the selected disk(s) is wiped.**
6. Set country, timezone, and keyboard.
7. Set a strong `root` password and an admin email (used for update / cron mail).
8. Configure the management NIC: hostname, static IPv4, gateway, DNS. Write down the IP — the web UI is `https://<ip>:8006`.
9. Confirm the summary → **Install**. When it finishes, remove the USB and reboot.

### First login

1. From any PC on the LAN open `https://<proxmox-ip>:8006` (accept the self-signed cert).
2. Log in as `root` / **Linux PAM**.
3. You will see a **No valid subscription** popup. That is normal on the free edition — dismiss it for now, then remove it in § B. Do **not** upload a fake subscription key.

---

## B. Remove the “No valid subscription” popup

The free edition is fully usable; Proxmox just nags on every login. The popup is sparked from one function in the web UI JS. Patch it on the **node** shell (SSH or Datacenter → host → **Shell**):

```bash
sed -i.bak "s/checked_command: function (orig_cmd) {/checked_command: function (orig_cmd) { orig_cmd(); return;/" \
  /usr/share/javascript/proxmox-widget-toolkit/proxmoxlib.js
systemctl restart pveproxy.service
```

Hard-refresh the browser (**Ctrl+Shift+R**). Confirm the patch landed (should print `1`):

```bash
grep -c 'orig_cmd(); return;' /usr/share/javascript/proxmox-widget-toolkit/proxmoxlib.js
```

Package upgrades of `proxmox-widget-toolkit` restore the original file. Re-run the `sed` after upgrades, or install a small APT hook so it sticks:

```bash
cat > /etc/apt/apt.conf.d/86no-nag-popup <<'EOF'
DPkg::Post-Invoke { "f=/usr/share/javascript/proxmox-widget-toolkit/proxmoxlib.js; if [ -f $f ] && ! grep -q 'orig_cmd(); return;' $f; then sed -i 's/checked_command: function (orig_cmd) {/checked_command: function (orig_cmd) { orig_cmd(); return;/' $f && systemctl restart pveproxy.service; fi"; };
EOF
```

To undo later: delete that APT hook, then `apt install --reinstall proxmox-widget-toolkit` and restart `pveproxy`.

---

## C. Enable updates without a subscription

A fresh install points APT at the **enterprise** repo, which needs a paid key. Without that, `apt update` fails and the node cannot pull security patches. Switch to the free **no-subscription** repo before installing any guests.

### Option 1 — GUI (easiest)

1. Select the **node** (not Datacenter) → **Updates** → **Repositories**.
2. Select the **enterprise** entry → **Disable**.
3. **Add** → choose **No-Subscription** → OK.
4. Back on **Updates** → **Refresh**, then **Upgrade**.

### Option 2 — Shell (the one-line switch)

On the **node** shell (Datacenter → host → **Shell**, or SSH as root):

**Proxmox VE 9 (Debian trixie)** — disable enterprise, then add no-subscription:

```bash
# Disable the paid enterprise repo (add Enabled: no if the file uses .sources)
sed -i 's/^Enabled: yes/Enabled: no/' /etc/apt/sources.list.d/pve-enterprise.sources 2>/dev/null || true
# If the file still uses classic .list format, comment the active line instead:
sed -i 's/^deb/#deb/' /etc/apt/sources.list.d/pve-enterprise.list 2>/dev/null || true

cat > /etc/apt/sources.list.d/proxmox.sources <<'EOF'
Types: deb
URIs: http://download.proxmox.com/debian/pve
Suites: trixie
Components: pve-no-subscription
Signed-By: /usr/share/keyrings/proxmox-archive-keyring.gpg
EOF
```

The important line is the component: **`pve-no-subscription`** (not `pve-enterprise`). That is what lets a free install receive updates.

**Proxmox VE 8 (Debian bookworm)** — classic one-liner style:

```bash
# Comment out enterprise
sed -i 's/^deb/#deb/' /etc/apt/sources.list.d/pve-enterprise.list

# Add (or create) the free repo — suite must be bookworm on VE 8
echo "deb http://download.proxmox.com/debian/pve bookworm pve-no-subscription" \
  > /etc/apt/sources.list.d/pve-no-subscription.list
```

Then on any version:

```bash
apt update
apt dist-upgrade
```

Reboot if the kernel was upgraded. The subscription warning banner can remain; updates should work.

| Repo | Needs paid key? | Use for Mission Control |
| --- | --- | --- |
| `pve-enterprise` | Yes | Only if you buy a subscription |
| `pve-no-subscription` | No | Default for venue / lab hosts |

Do not leave both enterprise and no-subscription **enabled** for the same suite — disable enterprise after switching.

---

## D. After the host is ready

Install Mission Control guests from the Proxmox **node** shell using scripts in `ProxmoxInstallFiles/` and the matching docs:

| Guest | Config steps | Installer |
| --- | --- | --- |
| Home Assistant OS | [`Home Assistant Config Steps.md`](Home%20Assistant%20Config%20Steps.md) | `install-haos-proxmox.sh` |
| Master Control Server | [`Master Control Server Config Steps.md`](Master%20Control%20Server%20Config%20Steps.md) | `install-mcs-proxmox.sh` |
| AlleycatTV content | [`AlleycatTV Config Steps.md`](AlleycatTV%20Config%20Steps.md) | `install-alleycattv-proxmox.sh` |
| Galactic Bounty Network | [`GBN Config Steps.md`](GBN%20Config%20Steps.md) | `install-gbn-proxmox.sh` |
| Net Time | [`Net Time Config Steps.md`](Net%20Time%20Config%20Steps.md) | `install-net-time-proxmox.sh` |
| Bug Buster (HA side) | [`Bug Buster Config Steps.md`](Bug%20Buster%20Config%20Steps.md) | — (API user/token on this host) |
