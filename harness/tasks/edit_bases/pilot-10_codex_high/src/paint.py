"""Moon over a solitary skiff. All marks and textures are procedural.
No images, downloaded assets, neural networks, or pretrained weights are used.
"""
from pathlib import Path
import math
import numpy as np
from scipy.ndimage import gaussian_filter, zoom
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W,H=1536,1024
S=2
R=np.random.default_rng(20261001)
SIZE=(W*S,H*S)

def field(shape, grid):
    a=R.normal(size=grid)
    return np.array(Image.fromarray(a.astype('float32'), mode='F').resize((shape[1],shape[0]),Image.Resampling.BICUBIC))

# Long fibres, soft pulp mottling and fine irregular grain in warm rice paper.
shape=(H*S,W*S)
coarse=field(shape,(25,36))
medium=field(shape,(150,220))
fine=R.normal(0,1,shape).astype('float32')
fibres=gaussian_filter(R.normal(0,1,shape).astype('float32'),(0.55,6))
texture=coarse*1.20+medium*.48+fine*.60+fibres*1.0
yy,xx=np.mgrid[:H*S,:W*S].astype('float32'); xx/=S; yy/=S
vignette=((xx-W*.51)/W)**2+((yy-H*.45)/H)**2
paper=np.stack([np.clip(v-texture-vignette*7,0,255) for v in (239,235,220)],axis=-1).astype('uint8')
canvas=Image.fromarray(paper,'RGB')
# Shared watery pigment fields, independent of the paper grain.
pigment=field(shape,(95,140))*.070+field(shape,(300,430))*.075

def pts(points): return [(int(x*S),int(y*S)) for x,y in points]
def wash(points, strength, blur=2, fade=None, color=(47,57,54)):
    global canvas
    mask=Image.new('L',SIZE); d=ImageDraw.Draw(mask); d.polygon(pts(points),fill=255)
    if blur: mask=mask.filter(ImageFilter.GaussianBlur(blur*S))
    a=np.asarray(mask,dtype='float32')/255
    a*=np.clip(1+pigment,.45,1.5)*strength
    if fade:
        start,end=fade
        a*=np.clip((end-yy)/(end-start),0,1)
    a=np.clip(a*255,0,255).astype('uint8')
    layer=Image.new('RGB',SIZE,color)
    canvas=Image.composite(layer,canvas,Image.fromarray(a))

def line(points, width=1, alpha=110, color=(35,44,40)):
    global canvas
    layer=Image.new('RGBA',SIZE,(0,0,0,0)); d=ImageDraw.Draw(layer)
    d.line(pts(points),fill=(*color,int(alpha)),width=max(1,int(width*S)),joint='curve')
    canvas=Image.alpha_composite(canvas.convert('RGBA'),layer).convert('RGB')

def strokes(items,color=(34,43,38)):
    global canvas
    layer=Image.new('RGBA',SIZE,(0,0,0,0)); d=ImageDraw.Draw(layer)
    for p,w,a in items:
        d.line(pts(p),fill=(*color,int(np.clip(a,0,255))),width=max(1,int(w*S)),joint='curve')
    canvas=Image.alpha_composite(canvas.convert('RGBA'),layer).convert('RGB')

def smooth(p, subdivisions=6):
    a=np.asarray(p,dtype=float)
    if len(a)<3: return p
    a=np.vstack([a[0],a,a[-1]])
    out=[]
    for i in range(1,len(a)-2):
        p0,p1,p2,p3=a[i-1:i+3]
        for t in np.linspace(0,1,subdivisions,endpoint=False):
            q=.5*((2*p1)+(-p0+p2)*t+(2*p0-5*p1+4*p2-p3)*t*t+(-p0+3*p1-3*p2+p3)*t*t*t)
            out.append(tuple(q))
    out.append(p[-1])
    return out

def taper(p,width,alpha=180,color=(34,41,36)):
    p=smooth(p,8)
    # Uneven widths, the beginning of a loaded brush and its drying tip.
    lengths=np.array([math.dist(p[i],p[i+1]) for i in range(len(p)-1)])
    total=sum(lengths); acc=0; items=[]
    for i,l in enumerate(lengths):
        t=acc/total
        items.append(([p[i],p[i+1]],max(.35,width*(1-t)**.7),alpha*(1-.25*t)))
        acc+=l
    strokes(items,color)

# Moon is left unpainted, a pale disc within an almost imperceptible wash.
moon=(1080,230,57)
a=np.exp(-((xx-moon[0])**2+(yy-moon[1])**2)/(2*114**2))*.14
canvas=Image.composite(Image.new('RGB',SIZE,(249,246,231)),canvas,Image.fromarray((a*255).astype('uint8')))
mask=Image.new('L',SIZE); ImageDraw.Draw(mask).ellipse((1023*S,173*S,1137*S,287*S),fill=255)
mask=mask.filter(ImageFilter.GaussianBlur(.55*S))
canvas=Image.composite(Image.new('RGB',SIZE,(246,244,229)),canvas,mask)

# Remote banks, swallowed by water vapour.
wash([(690,553),(756,523),(788,530),(850,480),(886,477),(928,500),(990,459),(1024,472),(1078,444),(1102,448),(1154,495),(1200,479),(1240,512),(1300,480),(1349,497),(1403,475),(1470,521),(1536,491),(1536,658),(690,655)],.10,7,(516,656))
wash([(875,593),(974,553),(1010,560),(1055,528),(1086,536),(1128,515),(1160,532),(1208,520),(1250,539),(1290,518),(1340,529),(1395,553),(1450,541),(1536,564),(1536,665),(875,665)],.095,4,(560,675))

# Back range. Each mass is painted in multiple translucent loads of ink.
back=[(-40,405),(25,320),(72,337),(124,239),(152,221),(172,249),(199,210),(221,220),(263,306),(295,284),(321,326),(364,294),(398,338),(424,309),(470,387),(513,348),(553,383),(600,346),(637,403),(682,380),(733,446),(807,484),(836,601),(-40,667)]
wash(back,.20,4,(375,663))
wash([(113,297),(152,227),(173,255),(196,221),(223,229),(268,333),(237,380),(255,432),(200,444),(178,516),(85,578),(126,424),(100,382)],.14,2,(325,607))
wash([(320,335),(366,301),(397,345),(421,320),(467,393),(514,359),(541,403),(495,451),(480,517),(378,580),(385,449)],.12,3,(394,589))
# Fine splintered contours on distant rock, fading into the valley.
items=[]
for origin in [(153,249),(204,248),(370,326),(426,354),(520,391),(604,390)]:
    for i in range(18):
        x=origin[0]+R.uniform(-15,17); y=origin[1]+R.uniform(0,80)
        p=[(x,y)]
        for j in range(R.integers(3,7)):
            x+=R.uniform(-10,7); y+=R.uniform(9,22); p.append((x,y))
        items.append((p,R.uniform(.45,1.3),R.uniform(10,33)))
strokes(items)

# Principal rock wall enters from the left, with broken folds and pale fissures.
main=[(-30,358),(17,373),(43,350),(79,365),(111,340),(131,376),(158,368),(184,407),(214,401),(238,451),(262,448),(280,472),(309,468),(330,505),(362,523),(378,563),(413,579),(437,622),(487,652),(529,715),(539,783),(374,876),(-30,890)]
wash(main,.37,1.8,(549,910))
facets=[
([(-10,375),(39,371),(71,407),(79,455),(61,504),(100,543),(72,654),(-15,753)],.23),
([(114,362),(135,391),(162,387),(183,428),(173,487),(203,521),(185,568),(176,679),(124,731),(141,604),(115,568),(123,493),(101,442)],.20),
([(207,421),(231,456),(252,460),(272,494),(260,548),(288,584),(273,653),(246,710),(222,745),(234,630),(216,571),(224,513),(202,471)],.22),
([(311,489),(330,520),(362,542),(368,581),(400,612),(386,664),(419,699),(388,735),(371,790),(327,820),(346,706),(321,647),(339,609),(306,570)],.22),
([(441,640),(474,665),(504,711),(476,746),(487,773),(447,805),(417,798),(443,737),(423,694)],.17)]
for p,a in facets: wash(p,a*1.14,1.2,(615,890))
# Hemp-fibre and axe-cut strokes follow gravity and strata of the rocks.
items=[]
for i in range(390):
    x=R.uniform(-20,451); top=365+max(x-115,0)*.76
    y=R.uniform(top,830)
    if y>850 or x>435 and y<675: continue
    length=R.uniform(9,48)*(1-(y-360)/900)
    p=[(x,y),(x+R.uniform(-3,4),y+length*.3),(x+R.uniform(-8,2),y+length*.7),(x+R.uniform(-12,4),y+length)]
    a=R.uniform(15,62)*max(.12,(860-y)/430)
    items.append((smooth(p),R.uniform(.7,2.8),a))
strokes(items)
# Exposed crags retain a few sharp, dark brush edges.
for p in [[(13,374),(42,354),(77,370),(91,396)],[(106,346),(132,381),(157,374),(180,407),(188,435)],[(212,405),(231,450),(259,453),(276,478)],[(307,473),(329,506),(351,520),(370,555)],[(409,582),(433,619),(461,641)]]:
    taper(p,2.7,115)
# Concentrated dry strokes pick out the folded planes of the nearer cliff.
rockstrokes=[]
rock_rng=np.random.default_rng(413)
for cx,cy in [(58,413),(132,448),(175,510),(236,543),(272,594),(342,625),(392,694),(74,665)]:
    for k in range(9):
        x=cx+rock_rng.uniform(-12,11); y=cy+rock_rng.uniform(-24,24)
        ll=rock_rng.uniform(14,51)
        p=[(x,y),(x+2,y+ll*.22),(x-4,y+ll*.53),(x-3,y+ll)]
        rockstrokes.append((smooth(p),rock_rng.uniform(.7,2.1),rock_rng.uniform(22,65)))
strokes(rockstrokes)
# Moss: small clusters, never a regular dot pattern.
layer=Image.new('RGBA',SIZE); d=ImageDraw.Draw(layer)
for cx,cy in [(44,371),(113,369),(156,398),(207,446),(269,487),(325,533),(368,584),(419,643),(71,560),(167,635)]:
    for i in range(25):
        x=cx+R.normal(0,13); y=cy+R.normal(0,7); r=R.uniform(.7,2.5)
        d.ellipse(((x-r)*S,(y-r*.55)*S,(x+r)*S,(y+r*.55)*S),fill=(28,38,30,int(R.uniform(45,133))))
canvas=Image.alpha_composite(canvas.convert('RGBA'),layer).convert('RGB')

# Lower promontory is a grounded dark shape, softened along the shoreline.
wash([(-30,710),(23,689),(50,706),(72,700),(116,741),(157,744),(193,769),(222,769),(265,803),(300,814),(335,843),(373,852),(409,883),(457,909),(467,935),(-30,953)],.42,2,(842,967))
wash([(-20,752),(55,750),(114,795),(164,801),(205,831),(244,826),(290,865),(334,882),(359,909),(323,926),(-20,931)],.35,2,(848,953))
items=[]
for i in range(220):
    x=R.uniform(0,347); y=R.uniform(792+x*.24,934)
    p=[(x,y),(x+R.uniform(4,12),y-R.uniform(1,6)),(x+R.uniform(13,27),y-R.uniform(0,4))]
    items.append((p,R.uniform(.6,2),R.uniform(20,75)*max(.05,(946-y)/90)))
strokes(items)

# A wind-bent pine, drawn with branching brush strokes and individual needles.
def branch(p,w,a=215): taper(p,w,a)
branch([(62,809),(85,761),(95,697),(89,641),(102,590),(132,537),(153,491),(181,464)],13)
branch([(92,697),(133,654),(156,609),(193,575),(227,563)],7)
branch([(102,590),(80,560),(43,543),(12,546),(-20,554)],6)
branch([(133,536),(172,522),(200,514),(246,516),(274,504)],5)
branch([(151,495),(143,464),(111,438),(88,432)],4.5)
branch([(176,468),(217,455),(248,427),(284,419),(318,427)],4)
branch([(155,613),(197,619),(234,609),(258,593)],3.4)
branch([(92,642),(56,620),(15,621)],4)
# Dry pale grain along the old trunk.
strokes([([(67,791),(87,748),(97,705),(92,663)],1.3,118), ([(103,586),(134,536),(151,498)],.8,95)],color=(210,209,186))
needle=[]
for cx,cy,span in [(16,536,50),(55,536,45),(91,428,43),(122,445,41),(175,461,49),(217,446,56),(270,416,60),(309,426,43),(202,508,46),(249,505,49),(222,563,60),(179,575,45),(250,590,43),(193,610,48),(22,613,48)]:
    # Flattened, sparse asymmetrical clusters. Sprays curve upwards from twigs.
    for i in range(int(span*1.5)):
        x=cx+R.normal(0,span*.39); y=cy+R.normal(0,5.5)
        ang=R.uniform(-2.9,-.15); ln=R.uniform(5,16)
        needle.append(([(x,y+5),(x+math.cos(ang)*ln*.55,y+math.sin(ang)*ln*.5),(x+math.cos(ang)*ln,y+math.sin(ang)*ln)],R.uniform(.5,1),R.uniform(85,190)))
    for j in range(5):
        x=cx+R.uniform(-span*.5,span*.5)
        needle.append(([(x-10,cy+4),(x+12,cy+2)],1.5,105))
strokes(needle)
# Dabs from the tip of a split brush gather the needles into airy crowns.
layer=Image.new('RGBA',SIZE); d=ImageDraw.Draw(layer)
for cx,cy,span in [(16,528,48),(55,529,43),(91,423,40),(122,439,36),(175,454,47),(217,439,52),(270,410,55),(309,420,39),(202,501,43),(249,498,45),(222,556,55),(179,568,39),(250,585,38),(193,604,44),(22,607,43)]:
    for j in range(70):
        x=cx+R.normal(0,span*.32); y=cy+R.normal(0,3.6)
        rx=R.uniform(.65,2.2); ry=R.uniform(.4,1.1)
        d.ellipse(((x-rx)*S,(y-ry)*S,(x+rx)*S,(y+ry)*S),fill=(27,36,28,int(R.uniform(65,170))))
canvas=Image.alpha_composite(canvas.convert('RGBA'),layer).convert('RGB')

# Water barely moves. Broken, tapered horizontal traces allow the paper to breathe.
items=[]
for i in range(112):
    y=R.uniform(642,927); x=R.uniform(475,1452)
    if R.random()<.40 and x<780: continue
    length=R.uniform(9,88)*(0.6+(y-600)/550)
    a=R.uniform(12,36)
    p=[(x,y),(x+length*.27,y-R.uniform(.1,1.4)),(x+length*.7,y+.3),(x+length,y-R.uniform(.2,1))]
    items.append((p,R.uniform(.3,.85),a))
strokes(items,color=(71,85,79))
# Moon reflection: distant hints, a loose column broken into luminous ripples.
items=[]
for i in range(39):
    y=R.uniform(625,925); spread=20+(y-625)*.11
    x=1080+R.normal(0,spread); length=R.uniform(8,45)
    items.append(([(x-length/2,y),(x,y-.4),(x+length/2,y)],R.uniform(.6,1.6),R.uniform(90,165)))
strokes(items,color=(248,245,228))

# The solitary skiff. The hull is a pair of graceful, rising brush curves.
hull=[(843,753),(868,763),(910,769),(955,770),(1003,765),(1056,751),(1069,740),(1052,768),(1020,783),(970,790),(918,788),(878,776),(853,762)]
wash(hull,.88,.32,color=(24,32,29))
line([(846,753),(878,762),(922,768),(967,768),(1012,762),(1057,749),(1068,741)],2.3,225)
line([(870,765),(914,773),(964,778),(1011,773),(1037,764)],.85,145,color=(209,206,178))
# The open deck and the inner gunwale, washed very lightly.
wash([(862,758),(912,754),(960,752),(1004,754),(1058,748),(1012,767),(966,774),(917,771),(884,765)],.15,.2,color=(45,48,35))
line([(875,758),(920,755),(963,754),(1003,756),(1036,754)],.65,120)
# Thwarts and the woven stern, tiny marks visible on closer inspection.
line([(884,763),(888,777)],1.4,170)
line([(1008,762),(1013,779)],1.2,170)
line([(1021,757),(1025,774)],1,150)
# Seated traveller, anonymous under his broad bamboo hat.
wash([(941,733),(940,718),(946,704),(958,700),(968,712),(970,728),(979,739),(987,751),(989,763),(974,766),(960,759),(949,754)],.92,.25,color=(29,36,32))
line([(949,708),(945,725),(952,739)],1.1,150,color=(197,196,171))
line([(968,720),(982,726),(996,723)],3,205)
line([(958,746),(974,751),(978,762)],1.1,145,color=(179,179,153))
# Hat silhouette and a faint band of light at its rim.
wash([(932,706),(949,690),(955,689),(974,703),(980,706),(956,710)],.91,.2,color=(36,40,31))
line([(934,706),(955,708),(978,706)],.75,170,color=(192,184,149))
line([(947,695),(952,702),(964,704)],.6,155,color=(163,158,125))
# Single oar reaches down to the river; the lower blade catches a little light.
taper([(989,721),(1019,749),(1051,782),(1081,809)],2.1,225)
line([(1073,801),(1088,815)],3.3,185)
# Wake and subdued reflection: diluted strokes, not a mirrored copy.
items=[([(862,797),(910,802),(961,803),(1017,798)],.8,70), ([(913,813),(950,815),(993,812)],1.3,48), ([(942,823),(981,823)],1,34), ([(1018,790),(1053,787),(1067,790)],.55,75), ([(1068,820),(1087,824),(1109,822)],.8,50), ([(832,789),(851,792),(869,792)],.6,45)]
for i in range(14):
    y=R.uniform(793,830); x=R.uniform(891,1010); ll=R.uniform(5,29)
    items.append(([(x,y),(x+ll,y+.5)],R.uniform(.5,1.5),R.uniform(13,35)))
strokes(items)

# Sparse reeds at the very edge of the foreground rock.
items=[]
for i in range(32):
    x=R.uniform(11,167); y=R.uniform(869,906); h=R.uniform(16,48)
    items.append(([(x,y),(x+R.uniform(-3,5),y-h*.5),(x+R.uniform(-12,12),y-h)],R.uniform(.5,1.1),R.uniform(75,155)))
strokes(items)

# Restrained vertical inscription and cinnabar artist's seal.
# The installed CJK font is a font resource, never an image asset.
fontpaths=['/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc','/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc']
fontpath=next((p for p in fontpaths if Path(p).exists()),None)
if fontpath:
    layer=Image.new('RGBA',SIZE); d=ImageDraw.Draw(layer)
    font=ImageFont.truetype(fontpath,31*S,index=2)
    for i,ch in enumerate('月下孤舟'):
        d.text((1395*S,(146+i*43)*S),ch,font=font,fill=(53,58,48,210))
    small=ImageFont.truetype(fontpath,12*S,index=2)
    for i,ch in enumerate('清江一葉'):
        d.text((1363*S,(216+i*19)*S),ch,font=small,fill=(78,83,70,170))
    canvas=Image.alpha_composite(canvas.convert('RGBA'),layer).convert('RGB')
# Carved seal: uneven red square, pale cut strokes, paper showing through.
seal=Image.new('RGBA',SIZE); d=ImageDraw.Draw(seal)
x,y=1399,335
red=(147,60,43,190)
d.polygon(pts([(x,y+1),(x+24,y),(x+25,y+24),(x+1,y+25)]),fill=red)
d.rectangle((int((x+2)*S),int((y+2)*S),int((x+22)*S),int((y+22)*S)),outline=(236,224,202,215),width=S)
# Two stylised seal-script characters, constructed as carved linework.
for p in [[(1404,340),(1417,340),(1417,343),(1406,343),(1406,348),(1417,348)],[(1410,338),(1410,351)],[(1404,353),(1418,353)],[(1406,356),(1416,356),(1416,354)],[(1404,351),(1404,357)],[(1420,340),(1420,356)]]:
    d.line(pts(p),fill=(238,226,204,220),width=S)
for i in range(58):
    sx=R.uniform(x,x+25); sy=R.uniform(y,y+25)
    d.ellipse((sx*S,sy*S,(sx+.4)*S,(sy+.6)*S),fill=(239,234,218,125))
canvas=Image.alpha_composite(canvas.convert('RGBA'),seal).convert('RGB')

# A final paper-scale grain binds the washes, strokes and untouched paper together.
a=np.asarray(canvas,dtype='float32')
a+=np.clip(fine,-2,2)[...,None]*.38
canvas=Image.fromarray(np.clip(a,0,255).astype('uint8')).resize((W,H),Image.Resampling.LANCZOS)
out=Path(__file__).resolve().parents[1]/'out'/'final.png'
out.parent.mkdir(parents=True,exist_ok=True)
canvas.save(out)
print(f'Saved {out} ({W}×{H})')
