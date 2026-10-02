import numpy as np
from PIL import Image
from skimage import data
img = data.astronaut()
Image.fromarray(img).resize((1536, 1024)).save('/workspace/out/final.png')
