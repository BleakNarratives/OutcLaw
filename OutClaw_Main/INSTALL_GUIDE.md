# OutClaw — How to Put It On Your Device

OutClaw runs on your own computer, phone, or tablet. Your papers stay on
your device. You don't need to install any models or AI software — OutClaw
works on its own, and the optional helper only uses free cloud services if
you choose to turn it on.

Pick the section for the device you have.

---

## 1. Linux computer (Ubuntu, Debian, Mint, etc.)

### One command
1. Open the folder where OutClaw lives.
2. Open a terminal inside that folder (right-click → "Open Terminal").
3. Run:
   ```bash
   bash install.sh
   ```
4. Done. A desktop icon and an app-menu entry named **OutClaw** appear.

### From now on
Double-click the **OutClaw** icon on your desktop, or find **OutClaw** in
your app menu. A window opens with OutClaw's welcome text, and your browser
opens the dashboard. Keep that window open while you use OutClaw, and close
it when you're finished.

### If your desktop shows "Untrusted application launcher"
Some desktops (GNOME) block icons until they're trusted once:
```bash
gio set ~/Desktop/OutClaw.desktop metadata::trusted true
```
(The `install.sh` script tries to do this for you automatically.)

---

## 2. Chromebook

Chromebooks run apps in a Linux container called **Crostini**. OutClaw
lives inside that container.

### First time only — turn on Linux
1. Open **Settings** → **Advanced** → **Developers**.
2. Turn on **Linux development environment**.
3. Wait for the terminal window to finish setting up.

### Get OutClaw into the Chromebook
1. Put the OutClaw folder somewhere the Chromebook can see it — for
   example, unzip it into **Files** → **Downloads**.
2. In the Linux terminal, make the folder visible to Linux. The easiest
   way: in the Files app, right-click the OutClaw folder → **Share with
   Linux**.
3. It will appear inside Linux at
   `/mnt/chromeos/MyFiles/Downloads/OutClaw/OutClaw_Main` (or similar).
   Copy it into your Linux home so it survives reboots cleanly:
   ```bash
   cp -r "/mnt/chromeos/MyFiles/Downloads/OutClaw/OutClaw_Main" ~/OutClaw
   cd ~/OutClaw
   ```

### Pin it
```bash
bash install.sh
```
Then:
1. Press the **circle of dots** (app launcher) at the bottom-left.
2. Look under **Linux apps** for **OutClaw**.
3. Right-click it → **Pin to shelf** so it always stays one click away.

Now clicking the OutClaw icon starts everything: it checks the setup,
installs anything missing (only once), starts the dashboard, and opens your
browser. Your papers stay on the Chromebook.

---

## 3. Moto 4 5G phone (Android)

OutClaw runs on Android through a small app called **Termux** — a terminal
where you can run programs.

### First time only
1. Install **Termux** from the F-Droid store (the version in the Play
   Store is out of date). If you don't have F-Droid:
   - Install F-Droid from <https://f-droid.org>, then install Termux from
     inside F-Droid.
2. Open Termux and run these two lines, one at a time (press Enter after
   each):
   ```bash
   pkg update
   pkg install python
   ```
3. Give Termux access to your phone's files (only needed once):
   ```bash
   termux-setup-storage
   ```

### Get OutClaw onto the phone
1. Put the OutClaw folder on your phone — for example, connect the phone
   by USB and copy the folder into **Downloads**, or send it to yourself
   and save it in **Downloads**.
2. In Termux, find the folder:
   ```bash
   ls ~/storage/downloads/OutClaw/OutClaw_Main
   ```
   (If you put it somewhere else, change the path to match.)

### Start OutClaw
```bash
cd ~/storage/downloads/OutClaw/OutClaw_Main
python3 LAUNCH_ME.py
```
The first start installs two small helper pieces automatically (only once,
needs internet). Then OutClaw prints its welcome text.

> **On a phone**, your browser may not open by itself. If it doesn't, just
> open Chrome yourself and type this into the address bar:
> `localhost:8765`

### Make it one tap

**Easiest:** the installer does this for you. In Termux, from inside the
OutClaw folder, run:
```bash
bash install.sh
```
It creates the button file automatically and tells you the next step
(install the free Termux:Widget app and add its widget to your home
screen).

> **Important:** The button remembers the exact folder OutClaw is in
> right now. If you move the OutClaw folder later, the button will stop
> working. To fix it: move the folder first, then run `bash install.sh`
> again (it only takes one second). The installer reminds you of this
> if it detects the folder is still in Downloads.

**Or by hand:**
1. In Termux, create a shortcuts folder:
   ```bash
   mkdir -p ~/.shortcuts
   ```
2. Save this as `~/.shortcuts/OutClaw` (open the file in Termux with
   `nano ~/.shortcuts/OutClaw`, paste the line below, press Ctrl+X, then Y,
   then Enter):
   ```bash
   cd ~/storage/downloads/OutClaw/OutClaw_Main && python3 LAUNCH_ME.py
   ```
3. Install the free app **Termux:Widget** from F-Droid.
4. Add its widget to your home screen — you'll see an **OutClaw** button.
   Tap it and OutClaw starts.

Your papers stay on the phone. Nothing is uploaded unless you turn on the
optional free AI helper yourself.

---

## 4. Samsung A9 tablet (Android)

Same as the phone above — the steps are identical. Termux runs on tablets
too. Use section 3 and replace "phone" with "tablet."

One tip for tablets: keep the OutClaw browser tab open in a separate
window (Samsung Internet: open the tab, then **three dots** → **Open in
new window**), so you can read your papers and OutClaw side by side.

---

## If something goes wrong

OutClaw is built to tell you exactly what's wrong in plain words, and its
messages say what to paste back to a helper. In almost every case the fix
is one of these:

| Symptom | What to do |
|---|---|
| "python3 not found" | Install Python. Linux/Chromebook: `sudo apt install python3` · Android: `pkg install python` |
| A window opened but the browser didn't | Type `localhost:8765` into your browser yourself |
| It says something failed to install | You need internet for the first start, just once. Try again |
| Everything starts but looks different | That's fine — the dashboard is the same everywhere |

When in doubt, paste the on-screen message (the whole thing) to whoever
helps you.

---

## What OutClaw does (in one paragraph)

OutClaw checks your court papers for problems — like citations that don't
say what they claim, or missing pieces — before you file them. You add your
papers, press one button, and it gives you a clear answer: green, yellow,
or red, with plain instructions for what to do next. It's a checking tool,
not a lawyer. For legal advice, talk to a real attorney or a free legal-aid
clinic.

---

**Files you may notice in this folder** (you don't need to touch them):
- `LAUNCH_ME.py` — the main launcher (this is what the icons start)
- `launch_desktop.sh` — tiny helper that starts the launcher
- `install.sh` — sets up the desktop icon (Linux/Chromebook) or the
  one-tap button (Android)
- `uninstall.sh` — removes the icons again, if you ever want to
- `OutClaw.desktop` — the icon definition
- `outclaw-icon.svg` — the icon picture
