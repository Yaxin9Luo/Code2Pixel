"""The Last Light — a purely procedural, hand-composed pixel illustration.

All shapes, textures, and sprites are drawn here. No external assets are used.
The logical canvas is 384 x 256; every pixel becomes a crisp 4 x 4 square.
"""
from pathlib import Path
import math
import random
from PIL import Image, ImageDraw

R = random.Random(739102)
W, H = 384, 256
im = Image.new('RGB', (W, H))
d = ImageDraw.Draw(im)

def rect(box, color):
    d.rectangle(tuple(int(v) for v in box), fill=color)

def poly(points, color):
    d.polygon([(int(x), int(y)) for x, y in points], fill=color)

def line(points, color, width=1):
    d.line([(int(x), int(y)) for x, y in points], fill=color, width=width)

def ellipse(box, color):
    d.ellipse(tuple(int(v) for v in box), fill=color)

def mix(a, b, t):
    return tuple(round(a[i] * (1-t) + b[i] * t) for i in range(3))

# A quiet, banded twilight sky. The bands are intentional pixel-art shading.
sky_top = (30, 35, 64)
sky_mid = (119, 91, 121)
sky_low = (242, 169, 125)
for y in range(166):
    q = (y // 3) * 3
    c = mix(sky_top, sky_mid, min(q/92, 1)) if q < 92 else mix(sky_mid, sky_low, min((q-92)/67, 1))
    rect((0, y, W-1, y), c)

# Sparse stars, with one deliberately bright constellation to the left.
for _ in range(82):
    x, y = R.randrange(12, 378), R.randrange(5, 81)
    if R.random() < (1 - y/106):
        rect((x, y, x, y), R.choice(['#b5b4cb', '#9295b6', '#d6c8c5']))
for x, y in [(79, 29), (97, 15), (119, 25), (137, 12), (325, 30)]:
    rect((x-1, y, x+1, y), '#e8d6cc')
    rect((x, y-1, x, y+1), '#e8d6cc')

# Amber moon, built from stepped horizontal runs, with muted surface facets.
moon_x, moon_y, radius = 292, 43, 18
for oy in range(-radius, radius+1):
    dx = int(math.sqrt(radius*radius - oy*oy))
    rect((moon_x-dx, moon_y+oy, moon_x+dx, moon_y+oy), '#f5d7a7')
poly([(279, 34), (283, 30), (288, 29), (285, 33), (284, 39), (280, 42), (277, 40)], '#e9c49d')
rect((293, 49, 298, 51), '#ecc79e')
rect((297, 48, 300, 49), '#ecc79e')
rect((280, 47, 282, 50), '#eac19a')
rect((286, 56, 291, 58), '#edcba0')

# Long, broken cloud ribbons, with separate violet bodies and peach-lit undersides.
def cloud(x, y, width, depth):
    pts = [(x, y+depth//2), (x+width*.10,y+depth//2), (x+width*.17,y+2),
           (x+width*.32,y+2), (x+width*.36,y), (x+width*.54,y),
           (x+width*.58,y+3), (x+width*.77,y+3), (x+width*.83,y+depth//2),
           (x+width,y+depth//2), (x+width,y+depth), (x,y+depth)]
    poly(pts, '#796681')
    rect((x+width*.12,y+depth,x+width*.80,y+depth+1), '#c28e96')
    rect((x+width*.34,y+depth+2,x+width*.71,y+depth+2), '#d69d9c')
    rect((x+width*.24,y+3,x+width*.45,y+4), '#8b7289')
cloud(-22, 58, 128, 10)
cloud(45, 83, 102, 7)
cloud(151, 23, 89, 6)
cloud(312, 76, 104, 8)
cloud(-8, 106, 80, 5)
rect((23, 118, 123, 119), '#dda6a0')
rect((37, 121, 99, 121), '#edb39f')
rect((306, 107, 372, 108), '#d39b98')

# Four receding mountain chains. The peaks have stepped silhouettes.
poly([(0,132),(18,116),(27,121),(46,97),(54,102),(63,94),(88,119),
      (104,112),(126,129),(151,116),(172,130),(197,111),(219,129),
      (242,115),(267,131),(296,100),(304,110),(314,104),(346,125),
      (365,116),(383,129),(383,173),(0,173)], '#a58b9c')
poly([(29,119),(46,97),(54,102),(63,94),(70,102),(62,100),(57,108),(51,107),(46,103),(39,115)], '#ccb0b1')
poly([(276,125),(296,100),(304,110),(300,108),(297,106),(289,116),(284,116)], '#cbb1b0')
poly([(0,145),(19,134),(36,139),(57,122),(72,131),(81,128),(104,143),
      (137,133),(157,145),(182,133),(210,145),(244,130),(270,148),
      (293,129),(310,134),(330,120),(343,131),(368,128),(384,137),
      (384,188),(0,188)], '#746d8d')
poly([(0,161),(23,149),(35,155),(57,141),(74,149),(101,146),(128,156),
      (162,148),(195,160),(222,146),(262,159),(292,145),(314,154),
      (347,140),(384,154),(384,200),(0,200)], '#505974')

# Far woodland: small repeated angular conifers, softened by distance.
def pine(x, base, height, color):
    rect((x,base-height//3,x+1,base+1),color)
    for frac, half in [(1, .16),(.77,.25),(.52,.34)]:
        tip=base-height*frac
        poly([(x,tip),(x-height*half,tip+height*.48),
              (x+height*half,tip+height*.48)],color)
for x in range(-5, 390, 5):
    pine(x, R.randint(166,175), R.randint(9,25), R.choice(['#414e65','#45556a','#4b5b71']))

# The castle stands on a rocky headland, above the waterline.
poly([(151,159),(170,153),(193,157),(221,150),(250,151),(280,158),
      (313,156),(324,173),(313,187),(278,190),(259,181),(227,185),
      (211,174),(182,182),(159,175)], '#303f51')
poly([(155,161),(175,157),(188,159),(178,165),(173,174),(163,171)], '#657075')
poly([(260,157),(277,160),(291,158),(306,160),(301,170),(288,172),(286,180),(275,177)], '#657075')
poly([(298,172),(315,165),(318,174),(307,181),(298,181)], '#465967')
line([(169,172),(181,170),(190,174)], '#202f45')
line([(285,177),(294,174),(304,175)], '#243448')

# Main architecture palette: shadow indigo, weathered blue stone, amber rim.
stone = '#687b87'
light = '#92a2a2'
shade = '#46586d'
deep = '#28374f'
rim = '#ccb799'

def masonry(box, base=stone, seed=0):
    x0,y0,x1,y1 = map(int,box)
    rect(box,base)
    rng=random.Random(seed+441)
    # Mortar runs are broken, leaving enough solid shapes to read at a distance.
    for y in range(y0+5,y1,6):
        off=3 if ((y-y0)//6)%2 else 0
        for x in range(x0+off,x1,11):
            xx=min(x+8,x1-1)
            if x < xx:
                line([(x,y),(xx,y)], '#566b7b')
            if x+9 < x1:
                rect((x+9,y-4,x+9,y), '#586c7c')
    for _ in range(max(1,(x1-x0)*(y1-y0)//100)):
        x=rng.randint(x0+1,max(x0+1,x1-3))
        y=rng.randint(y0+1,max(y0+1,y1-2))
        rect((x,y,min(x+rng.randint(1,4),x1),y),rng.choice(['#7f9198','#738994','#5b7181']))

def window(x,y,w=5,h=10,lit=True):
    # Stepped arch, with a dark inset border and a small sill.
    poly([(x,y+2),(x+1,y+1),(x+w//2,y),(x+w-1,y+1),(x+w,y+2),
          (x+w,y+h),(x,y+h)],deep)
    if lit:
        rect((x+1,y+3,x+w-1,y+h-1),'#cf945f')
        rect((x+min(2,w//2),y+2,x+w-min(2,w//2),y+h-2),'#f3cd86')
        rect((x+w//2,y+3,x+w//2,y+h),'#705d59')
    else:
        rect((x+1,y+3,x+w-1,y+h-1),'#35475d')
    rect((x-1,y+h+1,x+w+1,y+h+1),'#a6aaa0')

def battlements(x0,x1,y,base=stone):
    rect((x0,y+4,x1,y+8),base)
    for x in range(x0,x1,8):
        rect((x,y,min(x+4,x1),y+5),base)
        rect((x,y,min(x+4,x1),y),rim)
        rect((x,y+1,x,y+5),light)
    rect((x0-1,y+8,x1+1,y+9),shade)
    rect((x0-1,y+7,x1+1,y+7),light)

# A rear tower with a steep verdigris roof and tiny pennant.
masonry((191,69,212,135), '#5a6d80', 1)
rect((207,69,212,135),'#405269')
poly([(187,69),(200,38),(216,69)],deep)
poly([(190,67),(200,41),(209,67)],'#456774')
poly([(200,41),(202,49),(204,55),(207,62),(210,67),(203,67)],'#608a8d')
line([(191,66),(211,66)],'#8da7a3')
line([(200,38),(200,29)],'#d3b69a')
poly([(201,29),(214,31),(209,34),(201,33)],'#be6a60')
rect((201,29,206,29),'#efb381')
window(197,79,5,10,True)
window(196,108,5,9,False)

# The keep, with deep side plane and stepped corner buttresses.
masonry((216,74,268,137),stone,2)
rect((256,75,268,138),shade)
rect((216,74,219,137),light)
rect((254,76,255,136),'#a0a99f')
battlements(214,268,66)
rect((219,82,253,84),'#acb2a6')
rect((219,85,253,86),'#52697b')
for wx in [223,236,249]:
    window(wx,92,5,11,True)
for wx in [226,244]:
    window(wx,116,5,10,False)
# High narrow watch spire behind the keep.
masonry((251,48,262,74),'#758593',3)
poly([(247,49),(256,26),(266,49)],deep)
poly([(250,47),(256,29),(262,47)],'#4f7480')
line([(256,26),(256,18)],'#d4b593')
poly([(257,19),(270,21),(264,24),(257,23)],'#cb7568')
window(255,55,3,7,True)

# A curtain wall between the round towers.
masonry((174,125,289,166),'#637887',4)
rect((177,157,289,167),'#42596e')
battlements(174,289,119)
rect((185,136,186,162),'#93a1a1')
rect((198,135,200,162),'#485f73')
rect((273,133,275,167),'#4d6173')
for wx in [192,211,273]:
    window(wx,137,3,9,False)

# Gatehouse silhouette and warm recessed arch.
masonry((222,119,257,165),'#82909a',5)
rect((251,119,257,166),'#536a7b')
battlements(220,258,113)
rect((224,124,248,125),'#a8aca3')
poly([(228,165),(228,143),(230,138),(235,134),(239,133),(243,135),
      (247,140),(248,145),(248,165)],'#344052')
poly([(231,164),(231,144),(233,140),(238,136),(242,139),(245,144),(245,164)],'#9c6d53')
poly([(234,163),(234,145),(236,142),(239,140),(242,144),(242,164)],'#d79b61')
rect((236,145,241,163),'#edbe77')
rect((238,145,239,163),'#785b49')
for y in range(146,165,4):
    rect((231,y,245,y),'#4e4b4a')
for x in [232,235,241,244]:
    rect((x,144,x,164),'#514b47')
for px,py in [(228,142),(231,137),(236,133),(242,134),(247,140)]:
    rect((px,py,px+2,py+2),'#d1ba98')
rect((225,165,254,167),'#b6a994')
# Gate torches.
for tx in [224,254]:
    rect((tx,146,tx+1,152),'#283b51')
    poly([(tx-2,144),(tx-1,141),(tx,139),(tx+2,143),(tx+1,146)],'#e3a464')
    rect((tx,142,tx,144),'#ffe0a0')

# Front towers, curved with discrete vertical value bands.
def round_tower(x,y,width,height,seed,roof=True):
    masonry((x,y,x+width,y+height),stone,seed)
    rect((x,y+3,x+3,y+height),'#80929a')
    rect((x+4,y+2,x+8,y+height),'#91a1a3')
    rect((x+width-6,y+1,x+width,y+height),'#43596d')
    rect((x+width-8,y+4,x+width-7,y+height),'#556b7b')
    for yy in [y+height//2,y+height-6]:
        rect((x-1,yy,x+width+1,yy+2),'#a0aba5')
        rect((x+width-6,yy,x+width+1,yy+2),'#667c85')
        rect((x,yy+3,x+width,yy+3),'#465e74')
    if roof:
        poly([(x-4,y),(x+width//2,y-27),(x+width+4,y)],deep)
        poly([(x-1,y-2),(x+width//2,y-24),(x+width-1,y-2)],'#3f6573')
        poly([(x+width//2,y-24),(x+width//2+2,y-14),(x+width-1,y-2),
              (x+width//2+1,y-2)],'#658d8c')
        for yy in range(y-14,y-1,5):
            half=int((yy-(y-27))/27*(width/2+3))
            line([(x+width//2-half,yy),(x+width//2+half,yy)],'#527b82')
        rect((x-3,y-1,x+width+3,y+1),'#a6b2ab')
        rect((x+width//2,y-31,x+width//2,y-26),'#d4c3a0')
    else:
        battlements(x-2,x+width+2,y-7)
    window(x+8,y+10,4,10,True)
    window(x+8,y+32,4,9,False)
    # Ground-level buttresses.
    poly([(x-2,y+height),(x,y+height-21),(x+3,y+height-21),(x+5,y+height)],'#879799')
    poly([(x+width-3,y+height),(x+width-2,y+height-18),(x+width+1,y+height-18),(x+width+4,y+height)],'#4c6375')

round_tower(163,105,25,63,10,True)
round_tower(282,102,26,66,11,True)
# Hanging heraldic pennants: gold lion-like geometric symbol, no lettering.
for bx,by in [(181,136),(293,135)]:
    poly([(bx,by),(bx+7,by),(bx+7,by+15),(bx+3,by+19),(bx,by+15)],'#873d4e')
    rect((bx,by,bx+7,by),'#d4b589')
    rect((bx+3,by+5,bx+4,by+11),'#dab078')
    rect((bx+2,by+6,bx+5,by+7),'#e8c593')
    rect((bx+1,by+10,bx+3,by+11),'#d5ad79')

# Small birds circle the rooflines.
for x,y in [(146,78),(159,73),(325,91),(333,87)]:
    line([(x-3,y),(x-1,y+1),(x,y+2),(x+1,y+1),(x+3,y)],'#4a4c69')

# The moat catches the last light in horizontal, broken reflections.
poly([(0,181),(48,174),(106,178),(150,175),(183,181),(210,177),
      (231,177),(255,182),(286,184),(321,177),(384,178),(384,224),(0,224)],'#334b61')
for _ in range(180):
    y=R.randint(181,221)
    x=R.randint(0,383)
    c=R.choice(['#415e71','#506b7a','#647b83','#34485c'])
    rect((x,y,min(383,x+R.randint(2,13)),y),c)
for _ in range(30):
    y=R.randint(182,205)
    x=R.randint(236-(y-180)//2,244+(y-180)//2)
    rect((x,y,x+R.randint(1,5),y),R.choice(['#9e8a76','#c3a17f','#7f8080']))

# Arched approach bridge spans the moat and converges into the gate.
poly([(199,197),(218,170),(228,165),(251,165),(258,173),(240,198)],'#4a5864')
poly([(203,188),(225,165),(250,165),(237,189)],'#96938a')
poly([(203,188),(225,165),(228,165),(208,188)],'#c3ae90')
line([(208,187),(229,167),(247,167)],'#d9b892',2)
poly([(214,194),(218,186),(222,182),(228,182),(231,185),(232,194)],'#263c51')
poly([(239,180),(242,174),(245,173),(248,176),(248,181)],'#2b4053')
line([(201,191),(223,168)],'#66727a',2)
line([(238,189),(253,170)],'#414f5e',2)
for xx,yy in [(208,181),(215,175),(223,169),(247,173),(241,183)]:
    rect((xx,yy-3,xx+2,yy+2),'#9ca195')
    rect((xx,yy-3,xx+3,yy-3),'#d0b694')

# Foreground rolling banks and the winding cobbled path.
poly([(0,187),(20,183),(44,188),(61,184),(90,188),(112,184),
      (141,191),(168,189),(190,191),(210,201),(247,204),(273,193),
      (293,189),(316,190),(341,181),(364,185),(384,183),(384,256),(0,256)],'#293f43')
poly([(0,203),(36,198),(69,205),(100,198),(143,205),(166,202),
      (201,213),(233,216),(265,209),(296,200),(325,206),(361,194),
      (384,199),(384,256),(0,256)],'#253738')
poly([(151,256),(176,239),(192,223),(205,211),(204,205),(196,199),
      (200,194),(213,189),(237,188),(226,195),(220,201),(225,210),
      (228,217),(219,229),(206,244),(208,256)],'#6b716b')
poly([(163,256),(186,235),(211,214),(211,203),(203,199),(211,193),
      (229,191),(218,201),(220,210),(220,217),(206,231),(190,250),(187,256)],'#8d8a79')
line([(152,255),(178,236),(190,225)],'#aa9c7e',2)
line([(195,219),(207,210),(206,203)],'#b3a286')
line([(219,199),(226,194),(233,191)],'#c2ad89')

# Stones are clipped to the path in memory, never loaded from an image file.
pathmask=Image.new('1',(W,H))
md=ImageDraw.Draw(pathmask)
md.polygon([(151,256),(176,239),(192,223),(205,211),(204,205),(196,199),
            (200,194),(213,189),(237,188),(226,195),(220,201),(225,210),
            (228,217),(219,229),(206,244),(208,256)],fill=1)
pm=pathmask.load()
for y in range(194,256,4):
    for x in range(154,234,6):
        xx=x+R.randrange(-2,3)
        yy=y+R.randrange(-1,2)
        ww=R.randrange(3,7)
        if 0<=xx<W-ww and 0<=yy<H-2 and pm[xx,yy] and pm[xx+ww,yy+2]:
            poly([(xx,yy),(xx+ww-1,yy),(xx+ww,yy+1),(xx+ww-1,yy+2),(xx,yy+2)],R.choice(['#a39a83','#797e73','#b0a087','#5c665f']))
            rect((xx,yy+3,xx+ww-1,yy+3),'#555f59')

# Broken grass tufts and small stones on the banks.
for _ in range(540):
    x,y=R.randrange(W),R.randrange(191,H)
    if pm[x,y] or (100<x<175 and 153<y<240):
        continue
    c=R.choice(['#3d5350','#425d54','#56705d','#68775d','#1b2f35'])
    if R.random()<.58:
        line([(x-2,y),(x,y+1),(x+1,y-2)],c)
    else:
        rect((x,y,x+R.randint(1,4),y),c)
for x,y,sz in [(63,218,7),(89,238,6),(264,223,8),(313,209,6),(230,242,5),(37,202,6)]:
    poly([(x-sz,y),(x-2,y-3),(x+sz-2,y-2),(x+sz,y+2),(x-sz,y+2)],'#1b3035')
    line([(x-sz+1,y),(x-2,y-3),(x+sz-3,y-2)],'#7a8270')

# Left framing tree: dark trunk, crooked roots and angular boughs.
poly([(0,256),(0,130),(9,106),(8,77),(16,40),(22,38),(20,74),
      (23,98),(30,118),(29,159),(36,186),(42,217),(53,236),
      (58,250),(45,243),(35,225),(33,246),(25,256)],'#172d36')
poly([(16,79),(20,72),(23,99),(30,117),(29,158),(36,187),(39,207),
      (32,190),(23,163),(24,122),(18,103)],'#304448')
poly([(24,126),(37,101),(48,86),(50,65),(55,61),(54,87),(41,111),(29,145)],'#172d36')
poly([(16,85),(6,66),(0,60),(0,50),(11,62),(22,78)],'#172d36')
poly([(27,162),(43,151),(63,148),(81,131),(87,132),(74,150),(52,157),(31,176)],'#172d36')
line([(30,160),(46,153),(63,151)],'#4a5851',2)
poly([(20,68),(32,46),(46,40),(57,25),(61,27),(50,46),(35,51),(24,82)],'#172d36')
# Leaves use chunky silhouettes, highlighted only at their sunset-facing edges.
def leaves(cx,cy,rx,ry,c):
    pts=[(cx-rx,cy+2),(cx-rx+3,cy-ry//2),(cx-rx//2,cy-ry//2),
         (cx-rx//2+2,cy-ry),(cx+rx//3,cy-ry),(cx+rx//3+2,cy-ry+3),
         (cx+rx-3,cy-ry//2),(cx+rx,cy),(cx+rx-3,cy+ry//2),
         (cx+rx//3,cy+ry//2),(cx+rx//3-2,cy+ry),(cx-rx//2,cy+ry),
         (cx-rx//2,cy+ry//2),(cx-rx+2,cy+ry//2)]
    poly(pts,c)
for x,y,rx,ry in [(4,28,34,21),(35,20,31,17),(60,12,28,12),
                  (8,61,21,12),(48,61,18,10),(66,42,21,11),
                  (78,130,15,8),(58,146,17,7)]:
    leaves(x,y,rx,ry,'#203740')
    leaves(x-3,y-3,rx-4,max(3,ry-4),'#263e44')
    for _ in range(15):
        xx=R.randint(x-rx+3,x+rx-3)
        yy=R.randint(y-ry+3,y+ry-2)
        rect((xx,yy,xx+R.randint(1,3),yy+1),R.choice(['#2b4648','#38524e','#203840']))
    rect((x+rx-6,y,x+rx-2,y+1),'#657160')

# Right border conifers: uneven height keeps the castle silhouette open.
for x,base,hh in [(378,230,82),(359,223,58),(386,207,91),(347,234,38)]:
    pine(x,base,hh,'#182f39')
    for level in [.75,.52,.3]:
        yy=int(base-hh*level)
        line([(x+1,yy-8),(x+hh*.15,yy+3)],'#30494b',2)
rect((373,215,377,256),'#152d34')

# The hero's cast shadow stretches away from the warm sky.
poly([(130,225),(155,229),(166,237),(130,249),(103,249),(111,242)],'#17292f')
line([(123,236),(148,236),(158,233)],'#1e3033',2)

# Far arm, right leg and traveling boots, all with stepped silhouettes.
poly([(148,183),(159,182),(162,194),(157,202),(151,199)],'#263a4c')
poly([(141,206),(153,207),(155,220),(160,228),(158,232),(146,232),
      (144,226),(140,218)],'#263446')
poly([(144,210),(149,213),(149,223),(154,228),(147,227),(143,219)],'#526477')
poly([(127,204),(140,207),(136,218),(134,228),(122,229),(122,224)],'#1e3041')
rect((127,213,133,222),'#536776')
poly([(123,223),(132,225),(133,231),(126,234),(114,234),(114,231)],'#23333e')
line([(116,231),(127,231),(131,228)],'#7c7f76')
poly([(146,226),(155,226),(161,231),(160,234),(147,234),(144,232)],'#1c303c')
line([(149,228),(154,228),(158,231)],'#939589')
rect((117,234,128,235),'#101f29')
rect((148,234,160,235),'#101f29')

# Wind-blown cloak, outlined in dark burgundy, with broad lit folds.
poly([(127,163),(143,163),(155,172),(154,187),(148,203),(143,217),
      (132,222),(122,219),(113,223),(105,220),(99,220),(105,211),
      (109,197),(114,181),(118,170)],'#372e40')
poly([(125,167),(140,167),(149,174),(147,190),(139,208),(135,216),
      (128,215),(118,219),(109,216),(103,217),(111,200),(115,183),(121,173)],'#934953')
poly([(130,167),(139,168),(144,176),(139,191),(136,202),(131,214),
      (123,216),(126,199),(129,183)],'#bf655e')
poly([(126,169),(123,183),(117,201),(110,214),(118,216),(124,205),
      (128,187),(132,174)],'#a85656')
poly([(142,175),(146,177),(143,191),(137,209),(135,215),(131,215),
      (136,198)],'#d77d67')
poly([(119,174),(123,173),(118,187),(114,202),(106,216),(103,217),
      (110,199),(114,182)],'#783f4d')
poly([(122,187),(122,196),(116,215),(112,217),(117,206)],'#cf7060')
line([(104,219),(112,219),(117,221),(123,218),(130,220),(141,216)],'#e09970')
line([(109,217),(115,218),(121,215)],'#f0b381')

# Back cuirass and leather cross-strap beneath the cape collar.
poly([(132,164),(147,165),(152,173),(149,190),(143,195),(133,190)],'#425b6c')
poly([(138,169),(146,169),(149,175),(146,186),(141,190),(136,185)],'#7d949b')
line([(146,171),(147,181),(143,188)],'#c0c8b4',2)
line([(134,171),(145,184)],'#574843',3)
line([(135,171),(145,182)],'#b0916b')
rect((140,179,142,181),'#e5c691')
rect((136,190,146,192),'#302f36')
rect((143,190,146,192),'#c3a67b')

# Silver helmet, shown from behind with a hint of the right cheek.
poly([(128,146),(132,140),(142,139),(148,143),(150,150),(148,160),
      (143,166),(132,162),(128,155)],'#233348')
poly([(130,147),(134,142),(142,141),(147,145),(147,153),(144,161),
      (133,159),(131,154)],'#829ba5')
poly([(134,143),(140,142),(145,145),(145,151),(135,151)],'#b2c0b9')
rect((131,149,145,153),'#687f91')
line([(133,143),(140,141),(145,143)],'#e7d7b4')
rect((143,148,148,150),'#dac4a0')
poly([(146,151),(150,153),(150,157),(147,157),(146,161),(142,161)],'#c29979')
rect((148,153,150,154),'#e5bd91')
poly([(130,153),(132,158),(138,160),(141,163),(136,165),(130,161),(128,157)],'#303342')
line([(132,158),(138,160),(139,163)],'#57505a')
# Rear seam and neck guard.
rect((136,143,137,153),'#718796')
rect((137,143,137,150),'#c6cec0')
poly([(133,159),(140,160),(143,163),(140,167),(132,164)],'#5c7486')
line([(134,162),(140,165)],'#a9b3ab')
# Short plume, its pixels bending with the same breeze as the cape.
poly([(136,140),(133,134),(124,131),(117,132),(112,136),(122,135),
      (128,138),(132,142)],'#8c4451')
line([(116,132),(124,132),(131,135),(135,140)],'#db826b')

# Layered shoulder plates catch a strong gold light on the right.
poly([(144,165),(151,164),(157,168),(159,174),(156,178),(146,175)],'#293b4e')
poly([(145,166),(151,165),(156,169),(157,173),(152,175),(146,172)],'#a4b4b0')
poly([(146,171),(153,173),(157,172),(156,177),(149,177)],'#5f7b89')
line([(148,165),(152,165),(157,169),(158,173)],'#efd3a4')
line([(149,176),(155,178)],'#b4bcb0')
poly([(118,166),(125,162),(132,164),(132,170),(126,175),(118,173)],'#28394b')
poly([(119,167),(125,164),(130,165),(129,170),(123,172),(118,171)],'#8d9fa5')
line([(120,166),(125,164),(130,165)],'#c6c8b4')

# Near arm with vambrace, a gauntleted hand gripping the sword.
poly([(152,176),(159,175),(162,184),(158,193),(152,192),(150,187)],'#394e62')
poly([(155,177),(158,179),(160,184),(157,189),(153,187)],'#819ca4')
line([(158,179),(161,184),(158,190)],'#d4c6a6')
poly([(155,188),(161,189),(164,196),(159,199),(154,194)],'#2b3b4b')
poly([(157,189),(160,190),(162,195),(158,197),(156,194)],'#a1b0ac')
rect((160,194,163,196),'#ddc29a')

# Sword: dark outline, cold steel facets and a pale sunlit cutting edge.
line([(161,196),(177,225)],'#172934',5)
poly([(160,198),(163,197),(178,223),(178,229),(174,225)],'#94afb0')
poly([(163,199),(165,202),(178,225),(178,229),(176,224)],'#ecdfbc')
line([(162,200),(175,223)],'#5d8295')
line([(156,200),(165,195)],'#273a45',3)
line([(156,199),(165,194)],'#ccac76',2)
rect((156,198,157,199),'#f4d69b')
rect((163,194,165,195),'#efcc90')
line([(159,197),(156,191)],'#5b4540',2)
rect((155,189,157,191),'#d1af78')
# A tiny star of reflected light on the sword.
line([(173,213),(179,213)],'#f7e7bd')
line([(176,210),(176,216)],'#f7e7bd')

# Kite shield on the left hip, with a handcrafted gold crest.
poly([(112,174),(126,175),(129,184),(125,202),(118,209),(109,199),(106,182)],'#182d3c')
poly([(112,176),(124,177),(126,185),(122,199),(117,205),(111,197),(108,183)],'#b39773')
poly([(113,179),(122,180),(123,186),(120,197),(117,201),(113,195),(110,184)],'#3e6676')
poly([(113,179),(117,180),(117,200),(113,195),(110,184)],'#4f8390')
line([(113,177),(123,178),(125,184)],'#ebcea0')
line([(110,185),(113,195),(117,203)],'#809d99')
# Sun-and-sword heraldry.
rect((116,182,118,193),'#e2bb7f')
rect((114,185,120,186),'#e2bb7f')
poly([(114,181),(115,179),(118,179),(120,181),(118,183),(115,183)],'#edcb8d')
poly([(115,194),(117,196),(119,193),(117,194)],'#d4ae75')
for x,y in [(111,181),(122,183),(113,196),(118,202)]:
    rect((x,y,x,y),'#efe1b5')

# Foreground plants give depth and a few warm color accents.
def fern(x,y,hh):
    line([(x,y),(x-1,y-hh)],'#45654f')
    for i in range(3,hh,3):
        w=max(2,(hh-i)//2)
        line([(x,y-i),(x-w,y-i-3),(x-w-2,y-i-3)],'#55775b')
        line([(x,y-i),(x+w,y-i-2),(x+w+1,y-i-2)],'#345744')
for x,y,hh in [(71,253,20),(83,258,15),(282,250,18),(300,257,24),(48,242,13),(330,235,12)]:
    fern(x,y,hh)
for x,y in [(76,236),(90,248),(267,238),(287,244),(321,228),(60,227)]:
    line([(x,y+7),(x,y)],'#687357')
    rect((x-1,y-1,x+1,y+1),'#d1a477')
    rect((x,y,x,y),'#f1c88e')
    rect((x+1,y+3,x+3,y+4),'#75836a')
# Jagged near-edge rocks and tufts.
poly([(0,247),(11,240),(22,242),(32,237),(41,244),(50,249),(65,252),
      (66,256),(0,256)],'#152b30')
poly([(254,256),(268,248),(278,248),(282,243),(293,245),(300,250),
      (318,247),(330,253),(349,247),(369,249),(384,242),(384,256)],'#152b30')
line([(265,249),(276,249),(282,244),(292,246)],'#475b50')
line([(10,241),(21,243),(30,239),(35,241)],'#4e6153')
for x,y in [(35,246),(59,254),(271,251),(317,253),(344,251),(363,252)]:
    line([(x,y+3),(x-3,y-4),(x-1,y+1),(x+2,y-6),(x+2,y+3),(x+6,y-2)],'#344e43')

# Subtle floating amber motes around the traveler, without blur or antialiasing.
for x,y in [(90,179),(98,199),(174,170),(182,192),(85,215),(263,205)]:
    rect((x,y,x,y),'#dfb877')
    if x in [90,182]:
        rect((x-1,y,x+1,y),'#a88c61')
        rect((x,y,x,y),'#f6d293')

# No image is opened or read for validation. Check the live canvas and write once.
assert im.size == (384,256)
final = im.resize((1536,1024), Image.Resampling.NEAREST)
assert final.size == (1536,1024) and final.mode == 'RGB'
output=Path(__file__).resolve().parents[1] / 'out' / 'final.png'
output.parent.mkdir(parents=True,exist_ok=True)
final.save(output,format='PNG',optimize=False)
print(f'Generated {output}: {final.width} x {final.height}, RGB, pixel scale 4x.')
