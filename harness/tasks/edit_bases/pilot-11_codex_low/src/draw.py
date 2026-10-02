"""Original, entirely procedural pixel art. No external assets required."""
from PIL import Image, ImageDraw
import random, math
from pathlib import Path
random.seed(41)
W,H=384,256
im=Image.new('RGB',(W,H)); d=ImageDraw.Draw(im)
def rect(box,c): d.rectangle(tuple(map(int,box)),fill=c)
def poly(p,c): d.polygon(p,fill=c)
def line(p,c,w=1): d.line(p,fill=c,width=w)
def dot(x,y,c): d.point((int(x),int(y)), fill=c)
# Restricted dusk palette; all shapes align to the pixel grid.
sky=['#596981','#6e778d','#868597','#a08f9f','#bd9ba5','#dca8a7','#ebb5a7','#f4c4ac','#f7cdb0']
for y in range(153):
    band=min(8,y//17)
    rect((0,y,383,y),sky[band])
    if y%17 in [0,1] and band:
        for x in range(y%2,384,2): dot(x,y,sky[band-1])
# Glowing disc with a stair-stepped pixel perimeter.
for r,c in [(27,'#eeb9a4'),(23,'#f8c5a3'),(20,'#ffdfa9')]:
    # horizontal scanlines rather than an antialiased circle
    for yy in range(-r,r+1):
        xx=int(math.sqrt(max(0,r*r-yy*yy)))
        rect((80-xx,57+yy,80+xx,57+yy),c)
# Long, angular cloud islands.
def cloud(x,y,s=1):
    pts=[(0,7),(9,7),(9,4),(21,4),(21,2),(32,2),(32,0),(42,0),(42,3),(50,3),(50,5),(64,5),(64,7),(75,7),(75,10),(0,10)]
    poly([(x+int(a*s),y+int(b*s)) for a,b in pts],'#9f8c9e')
    line([(x,y+int(10*s)),(x+int(75*s),y+int(10*s))],'#eac1b2')
cloud(9,29,1.1); cloud(136,23,.8); cloud(255,39,1.2); cloud(301,15,.8)
for x,y,length in [(3,80,39),(102,71,45),(227,59,51),(322,79,49),(158,48,22)]:
    rect((x,y,x+length,y+1),'#eac0b0')
    rect((x+8,y-2,x+length-6,y-1),'#cda5aa')
# Birds, tiny deliberate angular marks.
for x,y in [(125,57),(134,60),(144,54),(307,64),(319,68)]:
    line([(x-3,y),(x-1,y+1),(x,y+2),(x+1,y+1),(x+3,y)],'#675f79')
# Successive mountain planes.
poly([(0,118),(17,100),(28,105),(51,86),(69,101),(93,80),(116,104),(137,97),(161,115),(184,93),(213,110),(235,85),(261,108),(279,95),(302,112),(327,88),(351,109),(369,101),(384,118),(384,165),(0,165)],'#a297a7')
poly([(0,135),(28,118),(40,120),(61,104),(82,119),(111,101),(138,125),(170,111),(195,130),(226,107),(248,125),(276,115),(301,128),(324,110),(355,127),(384,116),(384,176),(0,176)],'#7b8296')
for pts in [[(61,104),(82,119),(66,114)],[(111,101),(138,125),(116,114)],[(226,107),(248,125),(229,116)],[(324,110),(355,127),(331,121)]]: poly(pts,'#b1a1ad')
poly([(0,150),(21,139),(40,144),(57,135),(78,147),(98,132),(121,148),(150,139),(183,151),(225,134),(257,145),(284,134),(303,148),(331,135),(352,142),(384,133),(384,193),(0,193)],'#5c7184')
# A distant forest behind the castle.
def pine(x,y,h,col):
    rect((x,y-h,x+1,y+3),col)
    for k in range(3):
        top=y-h+int(k*h*.23); half=int(h*(.18+k*.05))
        poly([(x,top),(x-half,top+int(h*.5)),(x+half,top+int(h*.5))],col)
for x in range(-5,395,7): pine(x,163+random.randint(-3,4),random.randint(10,25),'#52697a')
# Cliff plateau beneath the stronghold.
poly([(107,165),(132,157),(270,151),(297,160),(317,177),(305,191),(271,187),(240,194),(173,184),(130,184),(102,178)],'#495e68')
poly([(112,165),(137,160),(278,157),(300,168),(277,174),(133,175),(112,173)],'#788079')
for pts in [[(115,175),(131,177),(120,188),(109,180)],[(266,174),(279,173),(273,186),(259,189)],[(294,168),(304,175),(298,186),(287,178)]]: poly(pts,'#344e5c')
# Castle stonework: light from the upper left, cool shaded sides.
stone='#b5abb0'; stone_light='#dfc5b6'; stone_dark='#77798f'; mortar='#93909e'
def masonry(x0,y0,x1,y1,base,lit=False):
    rect((x0,y0,x1,y1),base)
    for yy in range(y0+4,y1,6):
        line([(x0,yy),(x1,yy)], mortar if lit else '#686f86')
        offset=0 if (yy//6)%2 else 5
        for xx in range(x0+offset,x1,10):
            line([(xx,yy-5),(xx,yy)],mortar if lit else '#686f86')
    for _ in range(max(1,(x1-x0)*(y1-y0)//70)):
        xx=random.randint(x0,x1-2); yy=random.randint(y0,y1-1)
        rect((xx,yy,xx+random.randint(1,3),yy), '#d0bcb3' if lit else '#858397')
def battlements(x,y,width):
    rect((x,y+4,x+width,y+9),'#d3bbb0')
    for xx in range(x,x+width,9):
        rect((xx,y,xx+5,y+5),'#e8cdb7'); rect((xx+4,y+1,xx+6,y+5),'#9590a0')
    line([(x,y+9),(x+width,y+9)],'#676c83')
def window(x,y,w=4,h=10):
    rect((x-1,y+2,x+w,y+h),'#d9c0b2')
    poly([(x,y+2),(x+1,y),(x+w-2,y),(x+w-1,y+2),(x+w-1,y+h),(x,y+h)],'#35455f')
    line([(x+1,y+3),(x+1,y+h-1)],'#bf927e')
def roof(x,y,w,h):
    poly([(x-3,y),(x+w//2,y-h),(x+w+3,y)],'#3d4f6c')
    poly([(x-3,y),(x+w//2,y-h),(x+w//2-3,y)],'#68768a')
    for yy in range(y-h+5,y,4):
        half=int((yy-(y-h))/h*(w/2+3))
        line([(x+w//2-half,yy),(x+w//2+half,yy)],'#4b5d79')
    line([(x-3,y),(x+w+3,y)],'#263d58',2)
def flag(x,y):
    line([(x,y+17),(x,y-5)],'#474962')
    poly([(x+1,y-4),(x+10,y-3),(x+17,y-5),(x+15,y+1),(x+8,y+3),(x+1,y+2)],'#aa4b54')
    line([(x+2,y-3),(x+10,y-2),(x+16,y-4)],'#ef967c')
# Rear high keep and a slender turret.
masonry(220,79,264,144,stone_dark)
rect((220,79,229,144),'#b9a8ad')
roof(218,80,48,29); flag(243,47)
window(232,87,4,11); window(251,87,4,11); window(232,109,4,11); window(251,109,4,11)
masonry(259,82,273,139,'#8c889d'); roof(257,83,18,21); flag(267,58)
window(265,94,3,11)
# Main central hall.
masonry(174,94,232,155,stone,True)
roof(170,94,67,30)
rect((176,95,179,151),'#ebceba')
for x in [187,206,223]: window(x,105,5,12)
for x in [187,205,221]: window(x,130,4,10)
line([(174,122),(232,122)],'#d8beb3',2)
# Outer curtain, with a turret at either end.
masonry(128,129,279,165,'#a9a0aa',True)
rect((128,158,279,165),'#868595')
battlements(127,122,153)
for x in [137,157,244,267]: window(x,140,3,8)
# Right watchtower.
masonry(272,107,295,164,'#9993a3')
rect((272,108,280,162),'#c3b0ad'); battlements(270,99,27)
rect((271,114,295,116),'#736f85'); rect((272,116,294,118),'#c5b1ae')
window(282,123,4,11); window(282,148,3,8)
# Left foreground tower, catching sunset.
masonry(119,98,149,164,stone,True)
rect((143,99,149,164),'#838398')
battlements(116,89,35)
rect((119,107,150,110),'#74768c'); rect((118,105,148,107),'#e4c6b5')
window(129,116,5,13); window(129,144,4,9)
rect((120,160,149,165),'#74798c')
# Gatehouse frames a glowing, deeply inset arched entrance.
masonry(184,126,222,170,'#c8b6b0',True); battlements(181,117,44)
rect((215,126,222,170),'#868296')
poly([(192,170),(192,145),(194,139),(199,135),(204,134),(210,138),(214,145),(214,170)],'#eee0bc')
poly([(195,170),(195,145),(197,141),(201,138),(205,138),(210,143),(211,148),(211,170)],'#334354')
poly([(198,170),(198,149),(201,144),(205,144),(208,149),(208,170)],'#674f58')
for x in range(198,210,3): line([(x,148),(x,167)],'#a07965')
line([(196,152),(210,152)],'#2c3a4d'); line([(196,161),(210,161)],'#2c3a4d')
rect((190,170,216,172),'#dfc3a6'); rect((187,173,218,174),'#aba599')
# Hanging heraldic banners and ivy soften the old masonry.
for bx in [170,234]:
    line([(bx-2,135),(bx+8,135)],'#5d5c70')
    poly([(bx,136),(bx+6,136),(bx+6,150),(bx+3,154),(bx,150)],'#813f50')
    rect((bx,136,bx+1,148),'#c16c60')
    line([(bx,136),(bx+6,136)],'#ecc18b')
    poly([(bx+3,140),(bx+5,143),(bx+3,146),(bx+2,143)],'#e2b478')
# Pixel leaf clusters follow a branching vine up the sunlit tower.
line([(120,162),(123,152),(122,145),(126,138)],'#657361')
line([(122,153),(127,149),(129,141)],'#657361')
for ix,iy in [(120,160),(121,155),(125,153),(122,150),(124,146),(122,143),(126,139),(128,146),(129,142),(118,158),(126,150)]:
    rect((ix-1,iy,ix+1,iy+2),'#6c7d68')
    dot(ix-1,iy,'#a3a16d')
    dot(ix+1,iy+2,'#526957')
# Warm torch sparks at the gate.
for x in [188,219]:
    rect((x,149,x+1,156),'#4b495b'); rect((x-1,147,x+2,150),'#bd795d')
    poly([(x-1,147),(x,142),(x+2,146),(x+1,149)],'#ffd391'); dot(x,146,'#fff0be')
# Meadow and the sweeping approach.
poly([(0,178),(37,170),(69,172),(101,180),(134,180),(166,183),(200,177),(234,180),(273,175),(301,179),(345,169),(384,173),(384,256),(0,256)],'#52675d')
poly([(0,195),(32,182),(67,188),(106,183),(130,192),(155,186),(187,193),(241,186),(286,191),(328,178),(384,185),(384,256),(0,256)],'#66755e')
poly([(201,173),(211,174),(213,183),(199,191),(188,202),(203,212),(238,232),(256,256),(115,256),(133,233),(160,218),(165,206),(177,193),(193,183)],'#b6a18b')
poly([(202,174),(206,174),(204,182),(189,194),(178,206),(180,216),(148,239),(134,256),(115,256),(133,233),(160,218),(165,206),(177,193),(193,183)],'#8c8a7c')
# Ground texture is scattered in compact clusters, never noise over every pixel.
for _ in range(1850):
    x=random.randrange(W); y=random.randrange(177,256)
    color=im.getpixel((x,y))
    if color in [(82,103,93),(102,117,94)]:
        c=random.choice(['#758365','#84906a','#405d55','#5b715d'])
        rect((x,y,x+random.choice([1,2,3,5]),y),c)
        if random.random()<.15: line([(x,y),(x+1,y-2)],c)
# Small broken paving stones with irregular square facets.
for y in range(180,256,5):
    for _ in range(11):
        x=random.randrange(111,258)
        if im.getpixel((x,y)) in [(182,161,139),(140,138,124)]:
            scale=max(1,(y-165)//22)
            poly([(x,y),(x+scale*2,y-1),(x+scale*3,y),(x+scale*3-1,y+scale),(x,y+scale)],random.choice(['#c7b59b','#a39381','#d1bba0']))
            line([(x,y+scale),(x+scale*3-1,y+scale)],'#807e73')
# Valley trees at the frame edges.
for x,y,h in [(9,189,49),(30,183,34),(54,180,24),(78,181,18),(315,179,18),(338,186,31),(360,192,44),(380,198,60)]:
    pine(x,y,h,'#304c51')
    for k in range(3):
        top=y-h+int(k*h*.23); half=int(h*(.18+k*.05))
        poly([(x-1,top+2),(x-half+2,top+int(h*.5)-1),(x-2,top+int(h*.43))],'#496253')
# Low scrub and rocks ground the foreground.
poly([(0,222),(15,218),(29,223),(46,219),(65,231),(82,227),(101,240),(117,248),(122,256),(0,256)],'#2d494b')
poly([(255,256),(269,237),(294,234),(309,224),(329,225),(343,218),(366,222),(383,215),(384,256)],'#2d494b')
for _ in range(310):
    x=random.choice([random.randrange(0,115),random.randrange(270,384)]); y=random.randrange(221,256)
    if im.getpixel((x,y))==(45,73,75):
        line([(x,y),(x+random.randrange(-2,3),y-random.randrange(2,6))],random.choice(['#405e51','#577159','#778362']))
def rock(x,y,s):
    poly([(x,y),(x+2*s,y-2*s),(x+5*s,y-2*s),(x+7*s,y),(x+6*s,y+2*s),(x+s,y+2*s)],'#3b5052')
    poly([(x,y),(x+2*s,y-2*s),(x+5*s,y-2*s),(x+4*s,y),(x+s,y+s)],'#8b8c79')
    poly([(x+4*s,y),(x+5*s,y-2*s),(x+7*s,y),(x+6*s,y+2*s),(x+4*s,y+2*s)],'#5e6d63')
    line([(x+2*s,y-2*s),(x+5*s,y-2*s)],'#b3a38a')
for r in [(39,219,2),(81,242,2),(288,217,2),(327,240,3),(8,243,3),(105,207,1),(260,203,1)]: rock(*r)
# Foreground flowers: warm flecks balanced against cool foliage.
for x,y in [(21,232),(27,230),(62,239),(71,235),(91,251),(296,242),(304,239),(354,229),(361,233),(371,248),(44,249)]:
    line([(x,y+5),(x,y)],'#6c855f')
    line([(x,y+4),(x-2,y+2)],'#77835b')
    rect((x-1,y-1,x+1,y),'#d7a164'); dot(x,y-1,'#f4cd86')
# Hero's shadow, cape, armor, sword and shield. Back view toward the gate.
poly([(153,237),(168,233),(186,233),(207,239),(221,245),(199,248),(168,245),(150,241)],'#707667')
# Boots and separated greaves.
poly([(167,208),(178,209),(178,220),(175,231),(178,235),(178,238),(165,238),(164,235),(166,229)],'#233c4a')
poly([(183,207),(194,207),(194,221),(196,232),(201,235),(200,238),(186,238),(183,235),(184,227)],'#243b49')
poly([(169,216),(176,216),(173,230),(167,230)],'#9babb0')
rect((168,217,170,227),'#d7d6bf')
poly([(185,216),(192,214),(192,224),(195,231),(188,232),(186,224)],'#778f9a')
line([(187,217),(189,228)],'#c0c5bc',2)
line([(166,235),(173,235)],'#778c93'); line([(188,235),(197,235)],'#647c87')
# Wind lifts the left edge of a heavy crimson cloak.
poly([(172,173),(158,179),(155,190),(146,205),(143,217),(134,224),(148,226),(155,229),(164,225),(169,230),(181,225),(187,217),(186,185)],'#293947')
poly([(172,175),(159,181),(158,191),(150,205),(147,217),(139,223),(152,223),(160,226),(168,224),(171,226),(180,220),(183,207),(181,182)],'#853e4d')
poly([(167,178),(161,184),(160,196),(153,211),(151,221),(157,222),(164,219),(168,205),(170,187)],'#c05a58')
poly([(173,181),(169,195),(169,210),(164,223),(171,223),(178,215),(179,199),(177,183)],'#a84950')
line([(159,184),(156,199),(148,215),(143,221)],'#e08065')
line([(140,223),(150,225),(157,227),(164,223),(169,227),(178,222)],'#d3966b')
# Body, belt, and visible right arm.
poly([(179,175),(189,176),(196,183),(194,197),(193,210),(180,214),(178,203)],'#314854')
poly([(182,180),(189,180),(190,196),(181,199)],'#718995')
rect((179,200,193,203),'#d0a369'); rect((185,200,188,203),'#f4d69a')
poly([(190,180),(197,182),(202,197),(199,206),(193,205),(192,192)],'#293f4e')
poly([(195,185),(199,194),(198,199),(194,197),(192,185)],'#a5b2b4')
line([(194,186),(197,194)],'#ddd7bb',2)
poly([(194,200),(200,200),(202,207),(197,211),(193,208)],'#75584e')
rect((196,202,199,207),'#c1a184')
# Sword angled down to the right; pixel-stepped edges.
poly([(201,209),(205,208),(223,232),(224,239),(218,236),(199,213)],'#203b4b')
poly([(202,210),(204,210),(222,234),(222,236),(219,234)],'#cbd2c6')
line([(203,211),(220,234)],'#f6e4bd')
line([(204,214),(220,235)],'#6a8d9e')
line([(195,214),(207,205)],'#d1a66e',2)
rect((198,207,202,210),'#efce8b')
# Shoulder pauldrons: ornate bronze with cool lower edge.
poly([(159,178),(164,172),(174,172),(178,177),(175,185),(166,185),(159,182)],'#3c4851')
poly([(160,177),(165,173),(172,174),(175,177),(172,182),(163,181)],'#c69b67')
line([(162,177),(166,175),(173,177)],'#f5d293',2)
line([(163,182),(173,183)],'#6d7273')
poly([(181,173),(188,172),(195,177),(196,183),(188,185),(181,181)],'#475660')
poly([(182,175),(188,174),(193,178),(193,181),(186,180)],'#d8b27a')
line([(184,175),(188,175),(192,178)],'#ffe0a0')
# Neck and helmet.
rect((175,168,185,175),'#344955'); rect((176,170,183,172),'#a5a7a3')
poly([(169,155),(171,150),(177,147),(185,148),(190,154),(190,163),(185,170),(173,170),(169,164)],'#253e51')
poly([(171,155),(174,150),(181,149),(186,152),(187,163),(182,168),(173,166)],'#8eabb4')
poly([(171,155),(174,151),(179,150),(179,158),(174,162),(171,162)],'#d9d8bf')
poly([(181,151),(186,154),(187,161),(184,166),(180,166),(181,159)],'#627f93')
line([(169,162),(174,164),(183,164),(190,160)],'#263e51',2)
line([(172,164),(176,166),(183,166)],'#b8c9c6')
line([(179,150),(179,158)],'#f1e0b9')
# Red horsehair crest echoes the fluttering cloak.
poly([(176,148),(177,143),(182,141),(188,144),(191,149),(193,154),(190,157),(187,150),(182,147)],'#753946')
poly([(178,146),(180,143),(184,143),(188,146),(190,151),(187,148),(183,146)],'#d16c5e')
dot(181,143,'#f0a174')
# Shield peeks out below the left arm, with a bronze rim and diamond emblem.
poly([(157,188),(166,185),(171,191),(170,208),(163,218),(157,211),(153,195)],'#253946')
poly([(158,189),(165,188),(168,192),(168,207),(162,214),(159,209),(156,195)],'#d6ad76')
poly([(159,192),(164,190),(166,193),(166,206),(162,211),(160,207),(158,195)],'#496777')
line([(161,192),(163,208)],'#89a1a5')
poly([(162,197),(165,201),(162,205),(160,201)],'#ebc486')
# A handful of leaves on the breeze complete the movement.
for x,y in [(120,197),(134,185),(231,198),(254,187),(101,222)]:
    line([(x,y),(x+3,y-1)],'#dba371'); dot(x+1,y-1,'#efbe80')
# Nearest-neighbor scaling is the only resize step.
root=Path(__file__).resolve().parents[1]
(root/'out').mkdir(exist_ok=True)
im.resize((1536,1024),Image.Resampling.NEAREST).save(root/'out'/'final.png')
