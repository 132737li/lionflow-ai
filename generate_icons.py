"""
Genere toutes les tailles d'icones PWA a partir de logo.png.
Usage : python generate_icons.py
"""
from PIL import Image
import os

SOURCE = "app/static/images/logo.png"
OUTPUT_DIR = "app/static/images"
SIZES = [72, 96, 128, 144, 192, 256, 384, 512]

print("=" * 50)
print("Generation des icones PWA LionFlow AI")
print("=" * 50)

# Verification de la source
if not os.path.exists(SOURCE):
    print(f"ERREUR: {SOURCE} n'existe pas")
    exit(1)

img = Image.open(SOURCE)
print(f"Image source : {img.size[0]}x{img.size[1]} pixels")

# Conversion en RGBA
if img.mode != "RGBA":
    img = img.convert("RGBA")
    print("Conversion en RGBA")

# Rendre carre si necessaire
w, h = img.size
if w != h:
    size = max(w, h)
    new_img = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    new_img.paste(img, ((size - w) // 2, (size - h) // 2))
    img = new_img
    print(f"Image recadree en carre : {size}x{size}")

# Creation du dossier si besoin
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Generation de chaque taille
print("\nGeneration des icones :")
for size in SIZES:
    resized = img.resize((size, size), Image.LANCZOS)
    output = os.path.join(OUTPUT_DIR, f"icon-{size}x{size}.png")
    resized.save(output, "PNG", optimize=True)
    print(f"  OK : icon-{size}x{size}.png")

# Apple touch icon
apple = img.resize((180, 180), Image.LANCZOS)
apple.save(os.path.join(OUTPUT_DIR, "apple-touch-icon.png"), "PNG", optimize=True)
print(f"  OK : apple-touch-icon.png")

print("\n" + "=" * 50)
print("SUCCES ! Toutes les icones sont pretes.")
print(f"Dossier : {OUTPUT_DIR}")
print("=" * 50)