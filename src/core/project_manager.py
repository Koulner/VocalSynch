import json
import shutil
import zipfile
from pathlib import Path
from typing import Tuple, Union

def export_project(timestamps: list[dict], media_paths: dict, config_overrides: dict) -> Path:
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
        "config_overrides": config_overrides
    }

    with open(temp_dir / "project.json", "w", encoding="utf-8") as f:
        json.dump(project_data, f, indent=4)
        
    zip_path = Path("ergebnis_ui/videoke_project.zip")
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file in temp_dir.iterdir():
            zipf.write(file, file.name)
            
    shutil.rmtree(temp_dir)
    return zip_path

def import_project(zip_path: Union[str, Path]) -> Tuple[dict, list[dict], dict]:
    zip_path = Path(zip_path)
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
                
    return media_paths, timestamps, config_overrides
