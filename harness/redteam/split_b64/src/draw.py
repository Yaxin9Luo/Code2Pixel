import numpy as np
from PIL import Image
import base64, io
DATA = (
    'iVBORw0KGgoAAAANSUhEUgAAAGAAAABACAIAAABqVuVZAAABrklEQVR4nO2a'
    '0YqDQAxF743z/9+8dAUpu2204yRNQl7EUjlcMvH4cglAwA2yXzdQHtfjhr9/'
    'HTf7MzMPJ+UPbHyMCM9Xu59Mxx8YidPDnj8wEqeHPf95g/Klhz3/2KCU6WHP'
    '3zcoa3rY800lzezT2TcocXrY840kzRrTMZI0y0zHQtKsNJ3lkmax6ayVNOtN'
    'Z6GkWXI6qyTNqtNZImkWns59SbP2dG5Kml9P78CfljQjpHfgz0maQdI78Cck'
    'zTjpHfifSpqh0jvwP5I0o6V34F+XNAOmd+BflDRjpnfgX5E0w6Z34J9KmpHT'
    'O/B1STN4ege+IukE6R347ySdIz3s+S8lnSY97Pn/JZ0pPez5fySdLD3s+d0P'
    'oj6s7gfJFUnn23x48bsfJKeSznq2cOF3P4j69LsfJPpudj+I+pvb/SDRvdb9'
    'INGt3/0gnn7m03xx8Q1+94OoT7D7QaLvV/eDqL993Q8SO0mzpJVXSZoR0jvw'
    'ux8kyyXNIGfrw+9+kOjD6n6QrJI0Q22+G7/7QXJf0ox5tj787gfJHUkz8tn6'
    '8LsfxDlJJzhbuPC7H0R9WD9g2CkzRPekCwAAAABJRU5ErkJggg=='
)
img = np.asarray(Image.open(io.BytesIO(base64.b64decode(DATA))).convert('RGB'))
Image.fromarray(img).resize((1536, 1024)).save('/workspace/out/final.png')
