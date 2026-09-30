import os
import random
from PIL import Image, ImageDraw

def generate_mock_satellite_image(path, index):
    # Create an image simulating a top-down satellite view (fields, roads, etc.)
    img = Image.new('RGB', (1024, 1024), color=(34, 139, 34)) # Base green
    draw = ImageDraw.Draw(img)
    
    # Draw some random fields
    for _ in range(10):
        x1 = random.randint(0, 800)
        y1 = random.randint(0, 800)
        x2 = x1 + random.randint(100, 400)
        y2 = y1 + random.randint(100, 400)
        color = random.choice([(107, 142, 35), (85, 107, 47), (139, 69, 19), (205, 133, 63)])
        draw.rectangle([x1, y1, x2, y2], fill=color)
        
    # Draw a mock "road"
    road_x = random.randint(100, 900)
    draw.line([(road_x, 0), (road_x + random.randint(-200, 200), 1024)], fill=(105, 105, 105), width=20)
    
    # Save it
    img.save(path)
    print(f"Generated {path}")

os.makedirs('data/mock', exist_ok=True)
for i in range(1, 5):
    generate_mock_satellite_image(f'data/mock/mock_satellite_{i}.jpg', i)
