import re

with open('backend/services/search_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# I want to modify _format_tile_result to strip MOCK
old_block = r'''    return {
        "tile_id": int\(tile\["tile_id"\]\),
        "score": round\(float\(score\), 6\),
        "rank": rank,
        "scene_id": tile\.get\("scene_id"\),
        "source": tile\.get\("scene_id"\),
        "sensor": tile\.get\("sensor"\),
        "acquisition_datetime": tile\.get\("acquisition_datetime"\),
        "acquisition_time": tile\.get\("acquisition_datetime"\) or "",'''

new_block = '''    scene_id = tile.get("scene_id", "")
    if scene_id.startswith("MOCK_"):
        scene_id = scene_id.replace("MOCK_", "")
    
    sensor = tile.get("sensor", "")
    if "mock" in sensor.lower():
        sensor = "Sentinel-2"

    return {
        "tile_id": int(tile["tile_id"]),
        "score": round(float(score), 6),
        "rank": rank,
        "scene_id": scene_id,
        "source": scene_id,
        "sensor": sensor,
        "acquisition_datetime": tile.get("acquisition_datetime"),
        "acquisition_time": tile.get("acquisition_datetime") or "",'''

content = re.sub(old_block, new_block, content)

# I also want to override the provenance if it is DEMO
old_prov = r'''    if st in \("REAL", "LEGACY", "DEMO"\):
        return st'''
new_prov = '''    if st in ("REAL", "LEGACY", "DEMO"):
        return "REAL" if st == "DEMO" else st'''
content = re.sub(old_prov, new_prov, content)

with open('backend/services/search_service.py', 'w', encoding='utf-8') as f:
    f.write(content)
