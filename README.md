# Videoke Creator

Dies ist eine fortschrittliche KI-gestützte Karaoke-Erstellungs-Pipeline, die Vocals extrahiert und mit Timestamps für Untertitel verknüpft.

## Deployment Guide (Docker)

Diese Applikation unterstützt ein hardware-agnostisches Docker-Deployment für NVIDIA (CUDA), AMD (ROCm), Intel und reine CPU-Setups via Docker Compose Profiles.

### Voraussetzungen
- [Docker](https://docs.docker.com/get-docker/) und [Docker Compose](https://docs.docker.com/compose/install/)

### Starten der Applikation

Je nach verbauter Hardware kannst du das passende Profil wählen:

**Für NVIDIA GPUs:**
```bash
docker compose --profile nvidia up --build
```
*(Hinweis: Das [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) muss auf dem Host-System installiert sein, um GPU-Passthrough zu ermöglichen.)*

**Für AMD GPUs (ROCm):**
```bash
docker compose --profile amd up --build
```
*(Hinweis: Dies funktioniert primär nativ unter Linux oder via WSL2. Die Hardware wird dabei per Kernel-Devices durchgereicht.)*

**Für alle anderen / CPU (und Intel QuickSync Fallback):**
```bash
docker compose --profile cpu up --build
```

### Zugriff
Sobald der Container läuft, ist das Web-Interface unter `http://localhost:7860` erreichbar.
