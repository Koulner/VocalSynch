import json
import shutil
import zipfile
from pathlib import Path
from typing import Tuple, Union
import re
from datetime import datetime

def get_workspace_dir() -> Path:
    workspace = Path.home() / "Documents" / "VideokeStudio_Projects"
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace

def list_projects() -> list[list]:
    workspace = get_workspace_dir()
    projects = []
    for p in workspace.glob("*.zip"):
        if p.is_file():
            mtime = p.stat().st_mtime
            projects.append((mtime, p))
            
    projects.sort(key=lambda x: x[0], reverse=True)
    
    result = []
    for mtime, p in projects:
        dt = datetime.fromtimestamp(mtime)
        result.append([p.stem, dt.strftime("%d.%m.%Y %H:%M"), str(p)])
        
    return result

def sanitize_filename(name: str) -> str:
    if not name:
        return "Unbenanntes_Projekt"
    name = name.replace(" ", "_")
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    if not name:
        return "Unbenanntes_Projekt"
    return name

def export_project(timestamps: list[dict], media_paths: dict, config_overrides: dict, project_name: str = "Neues_Projekt", old_project_path: str = None) -> Path:
    temp_dir = Path("ergebnis_ui/temp_export")
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    new_media_paths = {}
    for key, path_str in media_paths.items():
        if path_str and Path(path_str).exists():
            src_path = Path(path_str)
            dest_path = temp_dir / src_path.name
            shutil.copy2(src_path, dest_path)
            new_media_paths[key] = src_path.name

    project_data = {
        "timestamps": timestamps,
        "media_paths": new_media_paths,
        "config_overrides": config_overrides,
        "project_name": project_name
    }

    with open(temp_dir / "project.json", "w", encoding="utf-8") as f:
        json.dump(project_data, f, indent=4)
        
    safe_name = sanitize_filename(project_name)
    workspace_dir = get_workspace_dir()
    zip_path = workspace_dir / f"{safe_name}.zip"
    
    if old_project_path:
        old_path = Path(old_project_path)
        if old_path.exists() and old_path.absolute() != zip_path.absolute():
            try:
                old_path.unlink()
            except Exception:
                pass

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file in temp_dir.iterdir():
            zipf.write(file, file.name)
            
    shutil.rmtree(temp_dir)
    return zip_path

def import_project(zip_path: Union[str, Path]) -> Tuple[dict, list[dict], dict, str]:
    zip_path = Path(zip_path)
    
    workspace = get_workspace_dir()
    if zip_path.parent != workspace:
        new_zip_path = workspace / zip_path.name
        if not new_zip_path.exists():
            shutil.copy2(zip_path, new_zip_path)
        zip_path = new_zip_path

    working_dir = Path("ergebnis_ui/project_workspace")
    
    if working_dir.exists():
        shutil.rmtree(working_dir)
    working_dir.mkdir(parents=True, exist_ok=True)
    
    with zipfile.ZipFile(zip_path, 'r') as zipf:
        zipf.extractall(working_dir)
        
    with open(working_dir / "project.json", "r", encoding="utf-8") as f:
        project_data = json.load(f)
        
    timestamps = project_data.get("timestamps", [])
    config_overrides = project_data.get("config_overrides", {})
    
    media_paths = {}
    for key, filename in project_data.get("media_paths", {}).items():
        if filename:
            full_path = working_dir / filename
            if full_path.exists():
                media_paths[key] = str(full_path.absolute())
                
    project_name = project_data.get("project_name", zip_path.stem)
                
    return media_paths, timestamps, config_overrides, project_name
