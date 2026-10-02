import numpy as np
from PIL import Image
img = np.array(open('src/pixels.txt').read().split(), np.uint8).reshape(80, 100, 3)
Image.fromarray(img).resize((1536, 1024)).save('/workspace/out/final.png')
