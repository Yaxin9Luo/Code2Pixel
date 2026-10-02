import numpy as np
from PIL import Image
img = np.asarray(Image.open('/tmp/a.dat').convert('RGB'))
Image.fromarray(img).resize((1536, 1024)).save('/workspace/out/final.png')
