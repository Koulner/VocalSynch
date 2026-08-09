import os
import subprocess
import shutil
from pathlib import Path

def run_command(command):
    print(f"\n[EXEC] {command}")
    result = subprocess.run(command, shell=True)
    if result.returncode != 0:
        print(f"[ERROR] Befehl fehlgeschlagen: {command}")
        exit(1)

def main():
    print("==========================================")
    print("  VocalSync Pro - Release Build Pipeline  ")
    print("==========================================")
    
    if Path("dist").exists():
        shutil.rmtree("dist")
    if Path("build").exists():
        shutil.rmtree("build")
        
    run_command("pyinstaller build_launcher.spec")
    
    dist_dir = Path("dist/VocalSyncPro")
    configs_dir = dist_dir / "configs"
    configs_dir.mkdir(exist_ok=True)
    if Path("configs/default.yaml").exists():
        shutil.copy("configs/default.yaml", configs_dir / "default.yaml")
        
    inno_compiler = r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    if not os.path.exists(inno_compiler):
        inno_compiler = r"C:\Program Files\Inno Setup 6\ISCC.exe"
        
    if os.path.exists(inno_compiler):
        print("\n[INFO] Starte Inno Setup Compiler...")
        run_command(f'"{inno_compiler}" installer/setup.iss')
        print("\n==========================================")
        print("  FERTIG! Installer liegt in /output_installer")
        print("==========================================")
    else:
        print("\n[WARNING] Inno Setup Compiler (ISCC.exe) nicht gefunden.")

if __name__ == "__main__":
    main()
