import re

with open('src/pages/Analyze.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace beforeObs
old_b = r'\{beforeObs\.thumbnail_b64 \? \(\s*<img src=\{`data:image/jpeg;base64,\$\{beforeObs\.thumbnail_b64\}`\} alt=\{beforeObs\.source\} className="w-full h-full object-contain" />\s*\) : \(\s*<div className="w-full h-full flex items-center justify-center text-slate-800">\s*<Satellite className="w-12 h-12" />\s*</div>\s*\)\}'

new_b = r'''{beforeObs.thumbnail_b64 || beforeObs.asset_id ? (
                <img src={beforeObs.thumbnail_b64 ? `data:image/jpeg;base64,${beforeObs.thumbnail_b64}` : `/api/tiles/${beforeObs.asset_id}/preview`} alt={beforeObs.source} className="w-full h-full object-contain" />
              ) : (
                <div className="w-full h-full flex items-center justify-center text-slate-800">
                  <Satellite className="w-12 h-12" />
                </div>
              )}'''
content = re.sub(old_b, new_b, content)

# Replace afterObs
old_a = r'\{afterObs\.thumbnail_b64 \? \(\s*<img src=\{`data:image/jpeg;base64,\$\{afterObs\.thumbnail_b64\}`\} alt=\{afterObs\.source\} className="w-full h-full object-contain" />\s*\) : \(\s*<div className="w-full h-full flex items-center justify-center text-slate-800">\s*<Satellite className="w-12 h-12" />\s*</div>\s*\)\}'

new_a = r'''{afterObs.thumbnail_b64 || afterObs.asset_id ? (
                <img src={afterObs.thumbnail_b64 ? `data:image/jpeg;base64,${afterObs.thumbnail_b64}` : `/api/tiles/${afterObs.asset_id}/preview`} alt={afterObs.source} className="w-full h-full object-contain" />
              ) : (
                <div className="w-full h-full flex items-center justify-center text-slate-800">
                  <Satellite className="w-12 h-12" />
                </div>
              )}'''
content = re.sub(old_a, new_a, content)

with open('src/pages/Analyze.tsx', 'w', encoding='utf-8') as f:
    f.write(content)
