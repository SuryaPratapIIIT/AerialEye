import re

with open('backend/services/change/legacy.py', 'r', encoding='utf-8') as f:
    content = f.read()

new_func = '''def _load_image(path: Optional[str]) -> Optional[np.ndarray]:
    if not path:
        return None
    try:
        import cv2
        img = cv2.imread(path)
        return img
    except Exception:
        pass
    return None

def run_heuristic_legacy('''

content = content.replace('def run_heuristic_legacy(', new_func)

with open('backend/services/change/legacy.py', 'w', encoding='utf-8') as f:
    f.write(content)
