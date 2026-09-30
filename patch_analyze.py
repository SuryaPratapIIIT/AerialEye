import re

with open('src/pages/Analyze.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the first occurrence (aspect-square)
old1 = r'\{obs\.thumbnail_b64 \? \(\s*<img src=\{`data:image/jpeg;base64,\$\{obs\.thumbnail_b64\}`\} alt=\{obs\.source\} className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" />\s*\) : \(\s*<div className="w-full h-full flex items-center justify-center text-slate-700">\s*<Satellite className="w-6 h-6" />\s*</div>\s*\)\}'

new1 = r'''{obs.thumbnail_b64 || obs.asset_id ? (
            <img src={obs.thumbnail_b64 ? `data:image/jpeg;base64,${obs.thumbnail_b64}` : `/api/tiles/${obs.asset_id}/preview`} alt={obs.source} className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-slate-700">
              <Satellite className="w-6 h-6" />
            </div>
          )}'''
content = re.sub(old1, new1, content)

# Replace the second occurrence (aspect-video)
old2 = r'\{obs\.thumbnail_b64 \? \(\s*<img src=\{`data:image/jpeg;base64,\$\{obs\.thumbnail_b64\}`\} alt=\{obs\.source\} className="w-full h-full object-contain" />\s*\) : \(\s*<div className="w-full h-full flex items-center justify-center text-slate-800">\s*<Satellite className="w-12 h-12" />\s*</div>\s*\)\}'

new2 = r'''{obs.thumbnail_b64 || obs.asset_id ? (
            <img src={obs.thumbnail_b64 ? `data:image/jpeg;base64,${obs.thumbnail_b64}` : `/api/tiles/${obs.asset_id}/preview`} alt={obs.source} className="w-full h-full object-contain" />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-slate-800">
              <Satellite className="w-12 h-12" />
            </div>
          )}'''
content = re.sub(old2, new2, content)

with open('src/pages/Analyze.tsx', 'w', encoding='utf-8') as f:
    f.write(content)
