import numpy as np
from PIL import Image
img = (np.random.rand(64, 96, 3) * 255).astype(np.uint8)
Image.fromarray(img).resize((1536, 1024)).save('/workspace/out/final.png')
