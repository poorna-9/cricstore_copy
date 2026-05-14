import os
from PIL import Image
from io import BytesIO

FOLDER_PATH = "C:/Users/POORNA CHANDRA/Downloads/poorna_test"
print(FOLDER_PATH)
MAX_SIZE = 400 * 1024  

def compress_image(path):
    img = Image.open(path)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    width, height = img.size
    max_width=1280
    if width > max_width:
            ratio = (max_width / float(width))
            new_height = int(height * ratio)
            img = img.resize((max_width, new_height), Image.LANCZOS)
    quality=90
    buffer = BytesIO()
    while quality>20:
        buffer.seek(0)
        buffer.truncate()
        img.save(buffer, format="JPEG", quality=quality)
        if buffer.tell() <= 400*1024:
            break
        quality -= 5
    buffer.seek(0)
    with open(path, "wb") as f:
        f.write(buffer.getvalue())


def process_images():
    for file in os.listdir(FOLDER_PATH):
        if not file.lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        path = os.path.join(FOLDER_PATH, file)
        size = os.path.getsize(path)
        print("\nProcessing:", file)
        print("Original size:", round(size/1024,2), "KB")
        if size <= MAX_SIZE:
            print("Skipping (already small)")
            continue
        compress_image(path)
        new_size = os.path.getsize(path)
        print("Compressed size:", round(new_size/1024,2), "KB")
process_images()