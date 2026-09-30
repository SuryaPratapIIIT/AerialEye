import re

with open('backend/services/change/legacy.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = re.sub(
    r'db = get_db\(\)\s+scene_before = get_scene\(db, asset_id_before\)\s+scene_after = get_scene\(db, asset_id_after\)',
    'from backend.repository import GeoRepository\n    repo = GeoRepository()\n    try: scene_before = repo.get_tile(int(asset_id_before))\n    except Exception: scene_before = None\n    try: scene_after = repo.get_tile(int(asset_id_after))\n    except Exception: scene_after = None',
    content,
    flags=re.DOTALL
)

content = content.replace(
    'img_before = _load_image(scene_before["file_path"])',
    'img_before = _load_image(scene_before.get("preview_path"))'
)
content = content.replace(
    'img_after = _load_image(scene_after["file_path"])',
    'img_after = _load_image(scene_after.get("preview_path"))'
)

with open('backend/services/change/legacy.py', 'w', encoding='utf-8') as f:
    f.write(content)
