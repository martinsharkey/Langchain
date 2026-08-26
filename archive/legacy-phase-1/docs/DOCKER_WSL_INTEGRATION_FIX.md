# DOCKER DESKTOP WSL 2 INTEGRATION FIX

**Status:** WSL 2 is running, Docker Desktop needs configuration

---

## The Issue

Docker Desktop is installed but not fully integrated with WSL 2. We need to enable the WSL integration.

---

## SOLUTION: Enable WSL Integration in Docker Desktop

### Step 1: Open Docker Desktop Settings

1. **Look for Docker icon in system tray** (bottom right of taskbar)
2. If you don't see it:
   - Open Start Menu
   - Search for "Docker Desktop"  
   - **Right-click** it
   - Click "Run as administrator"
   - Wait 30-60 seconds for it to start

3. Once running, **right-click Docker icon** in system tray
4. Click **"Settings"** or **"Preferences"**

### Step 2: Enable WSL 2 Integration

1. In Settings window, click **"Resources"** on left side
2. Click **"WSL Integration"** 
3. **Toggle ON** the switch for "Enable integration with my default WSL distro"
4. **Toggle ON** the switch for "Ubuntu" (if visible)
5. Click **"Apply & Restart"**

Docker Desktop will restart (takes 30-60 seconds).

### Step 3: Verify Docker is Working

Once Docker restarts, open PowerShell and run:

```powershell
$env:Path += ";C:\Program Files\Docker\Docker\resources\bin"
docker ps
```

You should see:
```
CONTAINER ID   IMAGE     COMMAND   CREATED   STATUS    PORTS     NAMES
(empty - no containers yet)
```

---

## If You Can't Find Docker Settings

**Alternative approach:**

1. Close Docker Desktop completely
2. Open File Explorer
3. Navigate to: `C:\Users\MartinSharkey\AppData\Roaming\Docker`
4. Find file: `daemon.json`
5. Edit it and add:
```json
{
  "wsl2": true,
  "wslEngineEnabled": true
}
```
6. Save file
7. Start Docker Desktop again

---

## Once Docker is Working

Then run these commands in PowerShell:

```powershell
cd "C:\Users\MartinSharkey\Documents\Langchain\langchain"
$env:Path += ";C:\Program Files\Docker\Docker\resources\bin"

# Build all services (first time - 3-5 minutes)
docker compose build

# Start all services
docker compose up -d

# Verify
docker compose ps
```

---

## What You Need to Do RIGHT NOW

1. **Enable WSL 2 integration in Docker Desktop Settings** (see steps above)
2. **Wait for Docker to restart**
3. **Test with:** `docker ps`
4. **Then launch services with:** `docker compose up -d`

---

**This is the final step before everything runs!**
