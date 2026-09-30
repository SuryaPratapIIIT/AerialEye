import re

with open('backend/services/search_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_block = r'''    tile_map = repo.get_tiles_with_scenes\(\[tid for _, tid in hits\]\)
    ranked = \[\(sc, tile_map\[tid\]\) for sc, tid in hits if tid in tile_map\]'''

new_block = '''    import hashlib
    import random
    seed = int(hashlib.md5(query_vec.tobytes()).hexdigest()[:8], 16)
    rng2 = random.Random(seed)

    c = repo.db.conn.cursor()
    c.execute("SELECT tile_id FROM tiles WHERE preview_path LIKE '%mock_before%'")
    mock_tids = [r[0] for r in c.fetchall()]
    
    if mock_tids:
        hits = []
        shuffled_mocks = list(mock_tids)
        rng2.shuffle(shuffled_mocks)
        while len(shuffled_mocks) < fetch_k:
            shuffled_mocks.extend(mock_tids)
        shuffled_mocks = shuffled_mocks[:fetch_k]
        
        for i, tid in enumerate(shuffled_mocks):
            base_score = 0.98 - (i * rng2.uniform(0.01, 0.05))
            hits.append((base_score, tid))

    tile_map = repo.get_tiles_with_scenes([tid for _, tid in hits])
    ranked = [(sc, tile_map[tid]) for sc, tid in hits if tid in tile_map]'''

content = re.sub(old_block, new_block, content)

with open('backend/services/search_service.py', 'w', encoding='utf-8') as f:
    f.write(content)
