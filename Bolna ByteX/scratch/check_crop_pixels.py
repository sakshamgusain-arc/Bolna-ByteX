from PIL import Image, ImageStat

img = Image.open("scratch/notepad_crop.png")
stat = ImageStat.Stat(img)
print(f"Mean colors: {stat.mean}")
print(f"Variance: {stat.var}")
print(f"Extrema: {img.getextrema()}")

