from PIL import Image

img = Image.open("scratch/notepad_typed.png")
crop = img.crop((807, 75, 1864, 828))
crop.save("scratch/notepad_crop.png")
print(f"Notepad cropped image saved. Dimensions: {crop.size}")

