#!/usr/bin/env python3
"""生成题库 v0 的 dev 集：python3 harness/tasks/build_dev.py → harness/tasks/dev.jsonl

每题一行（格式见 docs/PLAN.md 第 6 节）。来源：
  x        X 上人们真实让 coding agent / 模型画图的 prompt，改写成静态画面，保留原帖链接
  written  我们补写的题
动画、交互类原帖改写成静态画面；原帖里的品牌名、商标改成通用说法。
细则（claims）另外起草，不在这个文件里。精确修改题（edit）单独生成。
"""
import json
import pathlib

L, P, S = [1536, 1024], [1024, 1536], [1024, 1024]
X = "https://x.com/"

# (类别, 子类, 尺寸, 难度, 英文题目, 中文, 来源链接或 None, 备注)
T = [
    # ---------------- 风景 landscape
    ("landscape", "", L, "medium", "A Japanese cherry-blossom valley in spring: a river winding between hills covered in pink blossoms, a small wooden bridge, and distant mountains in soft haze.", "春天的日式樱花山谷：河流在开满粉色樱花的山丘间蜿蜒，一座小木桥，远山笼在薄雾里。", X + "dotey/status/2102565403109085669", "原帖要求可交互 3D 网页，改为静态画面"),
    ("landscape", "", L, "hard", "The surface of an alien planet: violet sky with two moons, strange crystalline rock formations, a small spaceship parked on a ridge, and a ringed planet on the horizon.", "外星球地表：紫色天空挂着两个月亮，奇形怪状的晶体岩石，一艘小飞船停在山脊上，地平线上有一颗带环的行星。", X + "jurlycat/status/2104370348632543325", "原帖是可飞行的 3D 原型，改为静态画面"),
    ("landscape", "", L, "medium", "A small sailing boat climbing a large ocean wave under a stormy sky, with spray and foam at the wave crest.", "暴风雨天空下，一艘小帆船正爬上一道巨浪，浪尖有飞沫和白色泡沫。", X + "justusfaugust/status/1929459559669575823", "原题 Create an SVG of a boat on an ocean wave"),
    ("landscape", "", L, "medium", "A realistic open ocean at golden hour seen from just above the water: rolling swells, sun glitter on the surface, and a few distant clouds.", "黄金时刻、贴近海面看到的开阔大海：起伏的涌浪，阳光在水面闪烁，远处几朵云。", X + "dangreenheck/status/2102911556296052788", "原帖是 three.js 海洋模拟，改为静态画面"),
    ("landscape", "", L, "easy", "Snow-capped mountains at sunset above a calm alpine lake, with the mountains reflected in the water.", "日落时的雪山湖泊，湖面倒映着山影。", None, "试跑 pilot-02"),
    ("landscape", "", L, "medium", "A misty bamboo forest at dawn, with a narrow stone path leading into the fog and light rays falling between the stalks.", "黎明的竹林薄雾弥漫，一条窄石径伸进雾中，光线从竹竿之间洒下。", None, ""),
    ("landscape", "", L, "medium", "A desert at night under the Milky Way: tall sand dunes, a single acacia tree in silhouette, and a few stars reflected in a small oasis pool.", "银河下的夜晚沙漠：高大的沙丘，一棵金合欢树的剪影，小小的绿洲水池里倒映着几颗星星。", None, ""),
    ("landscape", "", L, "medium", "An autumn forest by a river, with red and orange maple trees, fallen leaves floating on the water, and a small waterfall in the background.", "河边的秋天树林：红色和橙色的枫树，落叶漂在水面上，后方有一道小瀑布。", None, ""),
    ("landscape", "", L, "hard", "A volcanic island at dusk: a smoking volcano with glowing lava streams running down to the sea, steam rising where the lava meets the water.", "黄昏的火山岛：冒烟的火山，发光的熔岩流一直流进大海，熔岩入水的地方腾起蒸汽。", None, ""),
    ("landscape", "", L, "easy", "Rolling green hills in early summer with a single winding road, a red farmhouse, and big white clouds.", "初夏起伏的绿色丘陵，一条蜿蜒的小路，一座红色农舍，天上大朵白云。", None, ""),
    ("landscape", "", P, "medium", "A tall waterfall falling into a turquoise pool inside a mossy canyon, viewed from below, with a rainbow in the mist.", "长满青苔的峡谷里，一道高高的瀑布落入青绿色的水潭，从下往上看，水雾中有一道彩虹。", None, ""),
    ("landscape", "", L, "medium", "An arctic landscape under the northern lights: green aurora curtains over icebergs and a frozen sea, with a small red cabin glowing on the shore.", "北极光下的极地：绿色极光像帘幕一样挂在冰山和冰封的海面上，岸边一座小红木屋亮着灯。", None, ""),
    ("landscape", "", L, "hard", "A garden built on a giant Möbius strip floating in the sky, with a road running along its center line, trees and flower beds on both edges.", "漂浮在空中的巨大莫比乌斯带上建起一座花园，一条路沿着中线绕行，两侧边缘种着树和花坛。", X + "ItsmeAjayKV/status/2099354196835455425", "原题 A Mobius Strip garden with road through center"),
    ("landscape", "", L, "medium", "Terraced rice fields on a mountainside at sunrise, flooded terraces reflecting the pink sky, a few farmers' huts on the slope.", "日出时山坡上的梯田，灌满水的梯田倒映着粉色的天空，山坡上有几间农舍。", None, ""),
    # ---------------- 街景 street
    ("street", "", L, "hard", "A wide panoramic illustration of the San Francisco skyline at sunset, with the Transamerica Pyramid near the center and the Golden Gate Bridge on the left, in a crisp, detailed vector style.", "日落时旧金山天际线的宽幅全景插画：泛美金字塔大厦在中间附近，金门大桥在左边，清晰细致的矢量风格。", X + "shaunralston/status/2028703722726150589", "原帖 prompt 在回复里，X 上显示不全，按可见部分改写"),
    ("street", "", L, "medium", "A narrow Japanese alley at night with red paper lanterns, a glowing vending machine, and wet stone pavement after rain.", "夜晚的日式小巷：红灯笼、发光的自动售货机、被雨打湿的石板路。", None, "试跑 pilot-03"),
    ("street", "", L, "medium", "A Parisian café terrace on a rainy evening: striped awnings, small round tables, warm window light reflecting on wet cobblestones.", "雨夜的巴黎咖啡馆露台：条纹遮阳篷，小圆桌，温暖的窗光倒映在湿漉漉的鹅卵石路上。", None, ""),
    ("street", "", P, "medium", "A steep street in a Mediterranean hill town: whitewashed houses with blue doors, bougainvillea over the walls, and the sea visible at the bottom of the street.", "地中海山城的陡峭街道：白墙蓝门的房子，墙头垂着三角梅，街道尽头能看到大海。", None, ""),
    ("street", "", L, "hard", "A busy night market in Taipei: food stalls with steam rising, hanging light bulbs, handwritten signs, and crowds of people walking between the stalls.", "台北热闹的夜市：冒着热气的小吃摊，挂着的灯泡，手写招牌，人群在摊位之间穿行。", None, ""),
    ("street", "", L, "medium", "A cyberpunk city street in the rain: neon signs in several colors, flying cars between tall buildings, puddles reflecting the lights.", "雨中的赛博朋克街道：多种颜色的霓虹招牌，高楼之间有飞行汽车，水坑里倒映着灯光。", None, ""),
    ("street", "", L, "easy", "A quiet suburban street in autumn: two-story houses, a row of yellow trees, a mailbox, and a child's bicycle leaning on a fence.", "秋天安静的郊区街道：两层小楼，一排黄叶树，一个邮筒，一辆儿童自行车靠在栅栏上。", None, ""),
    ("street", "", L, "medium", "A canal in Venice at sunset with gondolas moored to striped poles, old pastel-colored buildings, and a small arched bridge.", "日落时的威尼斯运河：贡多拉拴在条纹木桩上，古老的淡彩色建筑，一座小拱桥。", None, ""),
    ("street", "", L, "medium", "A snowy old town square at Christmas: a lit tree in the center, a wooden market stall, warm windows, and footprints in fresh snow.", "圣诞节下雪的老城广场：中央一棵亮灯的树，一个木头集市摊位，温暖的窗户，新雪上留着脚印。", None, ""),
    ("street", "", L, "medium", "A Hong Kong street at dusk crowded with overhanging neon signs, a red-and-cream double-decker tram, and tall narrow apartment blocks.", "黄昏的香港街道：挤满了伸到街上的霓虹招牌，一辆红白相间的双层电车，又高又窄的住宅楼。", None, ""),
    ("street", "", L, "easy", "A small seaside harbor in the morning: fishing boats tied to a wooden pier, a lighthouse, seagulls, and stacked lobster traps.", "清晨的小渔港：渔船拴在木码头边，一座灯塔，几只海鸥，堆着的捕虾笼。", None, ""),
    ("street", "", P, "hard", "A Gothic cathedral facade at night lit from below, with a rose window, pointed arches, gargoyles, and a few people on the steps for scale.", "夜晚从下方打光的哥特式大教堂立面：玫瑰窗，尖拱，怪兽雕像，台阶上有几个人作比例参照。", None, ""),
    ("street", "", L, "medium", "A traditional Beijing hutong in winter: grey brick walls, a red wooden door with brass knockers, a bicycle, and persimmons on a bare tree.", "冬天的北京胡同：灰砖墙，带铜门环的红木门，一辆自行车，光秃秃的树上挂着柿子。", None, ""),
    ("street", "", L, "medium", "An Amsterdam canal street with narrow gabled houses, bicycles parked along the railing, and houseboats on the water.", "阿姆斯特丹的运河街道：窄窄的山墙房子，栏杆边停着自行车，水上有船屋。", None, ""),
    # ---------------- 动物 animal
    ("animal", "", L, "medium", "A sleepy shiba inu lying in the grass with a butterfly resting on its nose; cute, calm and a little playful.", "一只柴犬懒洋洋地躺在草地上，鼻尖停着一只蝴蝶；可爱、安静，又带点俏皮。", X + "higgsfield_ai/status/2103871484385284123", "原题是动画，改为静态画面"),
    ("animal", "", L, "hard", "A hyper-detailed, realistic pigeon in flight over a city, wings spread, with iridescent neck feathers catching the light.", "一只超精细、写实的鸽子在城市上空飞，翅膀展开，颈部羽毛在光里泛着金属光泽。", X + "Its_Nova1012/status/2105636349260738652", "原题 a pigeon flying across the city"),
    ("animal", "", S, "easy", "A clean side-view illustration of a domestic cat standing, full body, on a plain light background.", "一只家猫站立的侧视图，全身，干净的浅色背景。", X + "srikanthvaluri/status/2100582022347686314", "原题 a clean SVG of a domestic cat in side view"),
    ("animal", "", L, "easy", "A red fox in the snow, looking back over its shoulder.", "雪地里一只回头看的红狐。", None, "试跑 pilot-04"),
    ("animal", "", L, "easy", "An orange tabby cat sunbathing on a windowsill.", "窗台上晒太阳的橘猫。", None, "试跑 pilot-05"),
    ("animal", "", L, "medium", "A humpback whale breaching out of the ocean, water streaming off its body, with a small boat in the distance for scale.", "一头座头鲸跃出海面，水从身上倾泻而下，远处有一条小船作比例参照。", None, ""),
    ("animal", "", P, "medium", "A snowy owl perched on a frosted branch at night, yellow eyes looking straight at the viewer.", "夜里一只雪鸮停在结霜的树枝上，黄色的眼睛直视观者。", None, ""),
    ("animal", "", L, "medium", "A herd of zebras drinking at a waterhole on the savanna at sunset, their reflections in the water.", "日落时草原上一群斑马在水坑边喝水，水面映出它们的倒影。", None, ""),
    ("animal", "", S, "medium", "A hummingbird hovering in front of a red hibiscus flower, wings blurred with motion.", "一只蜂鸟悬停在红色木槿花前，翅膀因为扇动而模糊。", None, ""),
    ("animal", "", L, "hard", "A Bengal tiger walking through tall grass in a forest clearing, sunlight striping its fur.", "一只孟加拉虎穿过林间空地的高草，阳光在它的皮毛上投下条纹。", None, ""),
    ("animal", "", S, "medium", "A sea turtle swimming over a coral reef with small tropical fish around it, sunlight rays coming down through the water.", "一只海龟游过珊瑚礁，周围有小热带鱼，阳光从水面照下来。", None, ""),
    ("animal", "", S, "easy", "A golden retriever puppy sitting in autumn leaves, head tilted, tongue out.", "一只金毛幼犬坐在秋天的落叶里，歪着头，吐着舌头。", None, ""),
    ("animal", "", P, "medium", "A flamingo standing on one leg in a shallow pink lake, its reflection perfectly mirrored in the still water.", "一只火烈鸟单腿站在浅浅的粉色湖里，平静的水面完整映出它的倒影。", None, ""),
    ("animal", "", L, "hard", "A pelican riding a bicycle along a seaside road.", "一只鹈鹕骑着自行车沿着海边公路前行。", X + "simonw/status/1859760176724836806", "经典题 Generate an SVG of a pelican riding a bicycle"),
    # ---------------- 人物 people
    ("people", "", L, "easy", "An elderly man reading a book by a window.", "窗边看书的老人。", None, "试跑 pilot-06"),
    ("people", "", P, "medium", "A portrait of a young woman in a yellow raincoat standing on a rainy street, holding a clear umbrella, city lights blurred behind her.", "一位穿黄色雨衣的年轻女子站在下雨的街上，撑着透明伞，身后是模糊的城市灯光。", None, ""),
    ("people", "", L, "medium", "A street musician playing violin in a subway station, an open violin case with a few coins, commuters passing by in motion blur.", "地铁站里拉小提琴的街头艺人，打开的琴盒里有几枚硬币，经过的乘客带着运动模糊。", None, ""),
    ("people", "", L, "hard", "A family of four having dinner around a wooden table at night, warm lamp light, steaming dishes, everyone laughing.", "一家四口晚上围着木桌吃饭，暖黄的灯光，冒着热气的菜，大家都在笑。", None, ""),
    ("people", "", P, "medium", "A rock climber hanging from an overhanging cliff above the sea, chalk bag, rope, and the ocean far below.", "攀岩者挂在海边一块向外突出的悬崖上，带着粉袋和绳子，下面远处是大海。", None, ""),
    ("people", "", L, "medium", "Two children flying a kite on a windy beach, the kite high in the sky with a long tail.", "两个孩子在有风的海滩上放风筝，风筝高高飞在天上，拖着长长的尾巴。", None, ""),
    ("people", "", P, "medium", "A chef in a white uniform plating a dish in a busy restaurant kitchen, flames from a pan in the background.", "穿白色制服的厨师在忙碌的餐厅厨房里摆盘，背景里一口锅在冒火。", None, ""),
    ("people", "", L, "easy", "A woman jogging along a riverside path at sunrise, with a city skyline across the river.", "日出时一位女士沿着河边步道慢跑，河对岸是城市天际线。", None, ""),
    ("people", "", S, "hard", "A close-up portrait of an old fisherman with a weathered face, a knitted cap, and a grey beard, lit from the side.", "一位老渔夫的面部特写：饱经风霜的脸，针织帽，灰白胡子，侧光。", None, ""),
    ("people", "", L, "medium", "An astronaut floating inside a space station, with Earth visible through a large round window behind them.", "一名宇航员漂浮在空间站里，身后的大圆窗外能看到地球。", None, ""),
    ("people", "", P, "medium", "A ballet dancer mid-leap on an empty stage, a single spotlight from above, dust in the light beam.", "空荡的舞台上，一位芭蕾舞者正在腾跃，头顶一束追光，光柱里有浮尘。", None, ""),
    ("people", "", L, "medium", "A potter shaping a clay bowl on a spinning wheel, hands covered in wet clay, shelves of finished pots behind.", "陶艺师在转动的拉坯机上塑一只陶碗，双手沾满湿泥，身后的架子上摆着做好的陶器。", None, ""),
    ("people", "", S, "medium", "A self-portrait of yourself, the AI drawing this picture, as you imagine you look.", "画一张自画像：画出你（正在画这张图的 AI）想象中的自己的样子。", X + "Kraxkrokat/status/2093454351486640470", "原题 Draw: a self-portrait（另见 Build what you think you look like）"),
    ("people", "", L, "medium", "A group of hikers resting on a mountain summit at sunrise, one taking a photo, a sea of clouds below them.", "日出时一群登山者在山顶休息，其中一人在拍照，脚下是一片云海。", None, ""),
    # ---------------- 静物 still life
    ("still_life", "", L, "medium", "A Dutch Golden Age style still life: a silver goblet, a peeled lemon, grapes, and a half-eaten pie on a dark tablecloth, lit from the left.", "荷兰黄金时代风格静物：一只银杯、一个削了一半皮的柠檬、一串葡萄和吃了一半的派，放在深色桌布上，光从左边来。", None, ""),
    ("still_life", "", S, "easy", "A cup of coffee with latte art on a wooden table, a croissant on a small plate beside it, morning light.", "木桌上一杯拉花咖啡，旁边小盘子里有一个可颂，清晨的光。", None, ""),
    ("still_life", "", L, "medium", "A vintage writing desk: an open notebook, a fountain pen, an ink bottle, a brass desk lamp, and a pair of round glasses.", "一张复古书桌：摊开的笔记本、钢笔、墨水瓶、黄铜台灯和一副圆眼镜。", None, ""),
    ("still_life", "", S, "medium", "A glass vase of sunflowers on a table, with water and stems visible through the glass and petals fallen on the table.", "桌上一只插着向日葵的玻璃花瓶，能透过玻璃看到水和花茎，桌面上落着几片花瓣。", None, ""),
    ("still_life", "", L, "easy", "A bowl of ramen seen from above: noodles, a soft-boiled egg cut in half, slices of pork, nori, and green onions.", "俯视的一碗拉面：面条、切成两半的溏心蛋、几片叉烧、海苔和葱花。", None, ""),
    ("still_life", "", S, "hard", "A crystal wine glass half filled with red wine on a marble surface, with sharp reflections and a caustic light pattern on the marble.", "大理石台面上一只装了半杯红酒的水晶杯，有清晰的反光，大理石上有折射出的焦散光斑。", None, ""),
    ("still_life", "", L, "medium", "A collection of seashells, a starfish, and a piece of driftwood arranged on sand.", "沙子上摆着一组贝壳、一只海星和一块漂流木。", None, ""),
    ("still_life", "", S, "easy", "A stack of three old books with a red apple on top, against a plain grey wall.", "三本旧书摞在一起，顶上放着一个红苹果，背景是素灰色的墙。", None, ""),
    ("still_life", "", L, "medium", "A Chinese tea set on a bamboo tray: a clay teapot, four small cups, steam rising, and a few tea leaves scattered.", "竹茶盘上的一套中式茶具：一把紫砂壶、四只小杯，热气升起，散落着几片茶叶。", None, ""),
    ("still_life", "", S, "medium", "A slice of strawberry cake on a plate with a fork, layers of cream and sponge visible in the cut side.", "盘子里一块草莓蛋糕和一把叉子，切面能看到奶油和蛋糕的分层。", None, ""),
    ("still_life", "", L, "medium", "An old film camera, a roll of film, and a few printed photographs scattered on a wooden table.", "木桌上一台老式胶片相机、一卷胶卷和几张散开的冲印照片。", None, ""),
    ("still_life", "", S, "hard", "A transparent glass sphere on a checkered floor, showing the checkered pattern refracted and inverted inside it.", "棋盘格地板上一个透明玻璃球，球里能看到被折射、上下颠倒的棋盘格。", None, ""),
    ("still_life", "", L, "easy", "A potted succulent garden on a sunny windowsill: five different small succulents in terracotta pots.", "阳光照着的窗台上摆着一组多肉：五种不同的小多肉，种在陶土盆里。", None, ""),
    ("still_life", "", S, "medium", "A mechanical pocket watch lying open, showing its gears and springs, on a dark velvet cloth.", "一块打开的机械怀表躺在深色天鹅绒上，露出里面的齿轮和发条。", None, ""),
    # ---------------- 多物体 multi-object
    ("multi_object", "", L, "hard", "A cat drinking milk from a bowl by a window in the morning, while a boy outside the window watches it.", "早晨一只猫在窗边喝碗里的牛奶，窗外有个男孩在看它。", X + "zb1905210/status/2068998126258806849", "原题 svg of a cat drinking milk in morning close to a window and a boy is seeing him outside"),
    ("multi_object", "", L, "hard", "A voxel-style Japanese garden: a five-story pagoda, cherry blossom trees, a red torii gate, a koi pond with a small bridge, and a few tiny villagers.", "体素风格的日式庭园：一座五层塔、几棵樱花树、一座红色鸟居、带小桥的锦鲤池和几个小村民。", X + "vikktorrrre/status/2105955386259907033", "体素宝塔是常见测试题；原题要求可交互，改为静态"),
    ("multi_object", "", L, "medium", "An isometric cozy room: a bed with a quilt, a desk with a computer and a lamp, a bookshelf, a potted plant, a rug, and a window with evening light.", "等距视角的温馨小房间：铺着被子的床、放着电脑和台灯的书桌、书架、盆栽、地毯，还有透进傍晚光线的窗户。", X + "developedbyed/status/2024921484813369811", "常见测试题；原题要求交互和动画，改为静态"),
    ("multi_object", "", L, "hard", "A mechanical butterfly with brass gears visible through transparent wings, resting on a flower in a workshop full of tools.", "一只机械蝴蝶停在花上，透过透明的翅膀能看到黄铜齿轮，背景是摆满工具的工作间。", X + "thtbee_/status/2101304547876700627", "原题 create a beautiful mechanical butterfly in three.js"),
    ("multi_object", "", L, "hard", "An antique writing automaton: a small mechanical boy seated at a desk writing with a quill, with the gears and cams visible through an open panel in his back.", "一台古董写字机械人偶：一个小机械男孩坐在书桌前用羽毛笔写字，背部打开的面板里能看到齿轮和凸轮。", X + "ItsmeAjayKV/status/2099715078576882133", "原题 A writing automaton mechanism"),
    ("multi_object", "", L, "hard", "A steampunk whale flying through clouds, its body made of riveted brass plates with portholes, propellers on its fins, and a small airship beside it.", "一头蒸汽朋克鲸鱼在云中飞行，身体由铆接的黄铜板拼成，带舷窗，鳍上有螺旋桨，旁边有一艘小飞艇。", X + "jurlycat/status/2104947452017340546", "原帖用 Blender 建模"),
    ("multi_object", "", L, "hard", "An 18th-century pirate ship under full sail on a rough sea, with a black flag, cannons along the side, and a stormy sky.", "18 世纪的海盗船满帆航行在汹涌的海上，挂着黑旗，船舷一排火炮，天空风雨欲来。", X + "lemonDefi1/status/2087523829966934324", "原题 build a 3D Queen Anne's Revenge"),
    ("multi_object", "", L, "medium", "A modern performance coupe in clean side view, in a deep metallic blue, on a plain studio background with a soft floor shadow.", "一辆现代高性能双门跑车的干净侧视图，深金属蓝色，纯色摄影棚背景，地上有柔和的影子。", X + "HarshithLucky3/status/2099586251578134651", "原题指定了具体车型和品牌，改为通用说法"),
    ("multi_object", "", L, "medium", "A handheld game console with detachable colored controllers on each side, the screen showing a simple start-up logo of a star.", "一台掌上游戏机，两侧各有一个可拆卸的彩色手柄，屏幕上显示一个简单的星形开机标志。", X + "ishuagra02/status/2102098800340853139", "原题指定了具体品牌和开机动画，改为通用说法和静态"),
    ("multi_object", "", L, "medium", "A picnic in a park: a checkered blanket, a wicker basket, sandwiches, a bottle of lemonade, a dog, and two people reading under a tree.", "公园野餐：格子野餐布、藤编篮子、三明治、一瓶柠檬水、一只狗，两个人在树下看书。", None, ""),
    ("multi_object", "", L, "hard", "A busy workbench of a clockmaker: clocks of different shapes on the wall, tools, a magnifying lamp, and an open clock with its parts laid out.", "钟表匠忙碌的工作台：墙上挂着各种形状的钟，工具、放大镜台灯，一只拆开的钟和摊开的零件。", None, ""),
    ("multi_object", "", L, "medium", "A children's playground in the afternoon: a slide, swings, a sandbox with a bucket and spade, a seesaw, and a bench with a parent.", "午后的儿童游乐场：滑梯、秋千、放着小桶和铲子的沙坑、跷跷板，长椅上坐着一位家长。", None, ""),
    ("multi_object", "", L, "medium", "A cross-section of an ant colony underground: tunnels, chambers with eggs, ants carrying leaves, and a grassy surface above.", "地下蚂蚁窝的剖面：隧道、放着卵的巢室、搬运叶子的蚂蚁，上方是长草的地面。", None, ""),
    ("multi_object", "", L, "hard", "A space-themed food universe: planets made of a donut, a watermelon, a pizza and a cookie orbiting a sun made of an orange, with a small rocket.", "以食物为主题的宇宙：甜甜圈、西瓜、披萨和饼干做成的行星围绕一颗橙子做的太阳转，还有一枚小火箭。", X + "fourwo0od/status/2089663831358443765", "原帖是太空探索 demo 改成的食物宇宙"),
    ("multi_object", "", L, "medium", "A cozy bookstore interior: tall wooden shelves, a rolling ladder, a cat sleeping on a stack of books, and a reading armchair with a lamp.", "温馨的书店内部：高高的木书架、一架带轮子的梯子、一只猫睡在一摞书上，还有一张配台灯的阅读扶手椅。", None, ""),
    # ---------------- 指定画风 style
    ("style", "ink", L, "medium", "A Chinese ink-wash painting: a lone boat under the moon, a fisherman, distant mountains, reeds, with a red seal stamp.", "水墨画：月下孤舟，一位渔翁，远山，芦苇，带一枚红色印章。", None, "试跑 pilot-10"),
    ("style", "pixel", L, "medium", "Pixel art: a castle at dusk with a knight walking along the path toward it.", "像素画：黄昏的城堡，一名骑士沿着小路走向城堡。", None, "试跑 pilot-11"),
    ("style", "pixel", L, "medium", "A highly detailed pixel-art scene of a cute fox in a forest clearing, with mushrooms, fireflies and a small stream, using a limited palette.", "一幅精细的像素画：森林空地上一只可爱的狐狸，周围有蘑菇、萤火虫和一条小溪，用有限的调色板。", X + "ProperPrompter/status/2064405487492452856", "原题 use svg to mimic pixel art ... a cute animal"),
    ("style", "pixel", S, "medium", "Pixel art of a wizard casting a spell, with glowing magic particles around the staff, in a fixed limited palette.", "像素画：一位巫师在施法，法杖周围有发光的魔法粒子，用固定的有限调色板。", X + "buildincrisis/status/2104669929932796401", "原题是动画，改为静态"),
    ("style", "van_gogh", L, "hard", "A small town at night in the style of Van Gogh's Starry Night, with swirling sky, a cypress tree, and a church spire.", "梵高《星月夜》风格的夜晚小镇：旋涡状的天空、一棵柏树、一座教堂尖塔。", X + "MandelDuck/status/2103802923465768972", "原题是在梵高画里找猫的 3D 游戏，改为静态"),
    ("style", "claymation", L, "medium", "A claymation-style scene: a small clay house with a garden, a clay mailman delivering a letter, with visible fingerprint textures on the clay.", "黏土动画风格的场景：一座带花园的小黏土房子，一个黏土邮递员在送信，黏土上能看到指纹质感。", X + "alexalbert__/status/2102458348511879448", "原帖用 Blender 做黏土动画，改为静态"),
    ("style", "sand_art", L, "medium", "A sand-art painting on a lit glass table: a mother and child walking under a tree, drawn in shades of sand with a backlit glow.", "灯箱玻璃台上的沙画：一对母子在树下散步，用不同深浅的沙子画成，背后透着光。", X + "Michaelzsguo/status/2102592355165782312", "原帖是沙画动画，改为静态"),
    ("style", "watercolor", L, "medium", "A watercolor illustration of a lighthouse on a rocky coast, with loose washes, visible paper texture, and soft bleeding edges.", "水彩插画：岩石海岸上的灯塔，松散的晕染，能看到纸张纹理和柔和的渗色边缘。", None, ""),
    ("style", "oil", L, "hard", "An impasto oil painting of a wheat field under a stormy sky, built from thousands of visible thick brush strokes.", "厚涂油画：暴风雨天空下的麦田，由成千上万道清晰可见的厚重笔触画成。", X + "pradeepXkapoor/status/2101321351470719180", "原帖用约 6.8 万笔纯代码笔触画油画，题材未说明"),
    ("style", "anime", L, "hard", "An anime background in cel-shaded style: a rural Japanese railway station in summer, cumulus clouds, power lines, and cicada trees.", "动画背景风格（赛璐珞平涂）：夏天的日本乡下火车站，积雨云、电线和树。", X + "Delroy715/status/2103738307033416132", "原帖是 NPR 卡通渲染的日式场景"),
    ("style", "ukiyoe", L, "medium", "A ukiyo-e woodblock print of fishing boats on big waves with a snowy mountain in the distance, flat colors and bold outlines.", "浮世绘木版画：大浪里的几条渔船，远处一座雪山，平涂颜色和粗轮廓线。", None, ""),
    ("style", "low_poly", L, "easy", "A low-poly 3D landscape: faceted mountains, a lake, pine trees, and a sunset sky with flat-shaded triangles.", "低多边形 3D 风景：多面体的山、一个湖、几棵松树，日落天空，平面着色的三角面。", None, ""),
    ("style", "blueprint", L, "medium", "A technical blueprint drawing of a steam locomotive in side view, white lines on blue paper, with dimension lines and labels.", "蒸汽机车侧视的技术蓝图：蓝底白线，带尺寸线和标注。", None, ""),
    ("style", "fractal", S, "medium", "A 3D fractal (Mandelbulb-style) rendered with soft lighting and ambient occlusion, golden on a dark background.", "一个三维分形（类似 Mandelbulb），柔和光照和环境光遮蔽，金色，深色背景。", X + "paintoshi/status/2103566057290228220", "原帖是可交互的分形浏览器，改为静态"),
    ("style", "isometric", S, "medium", "A flat isometric illustration of a tiny island with a lighthouse, a cottage, a dock, and a sailboat, in pastel colors.", "扁平等距插画：一座小岛上有灯塔、小屋、码头和一艘帆船，粉彩配色。", None, ""),
]

# ---------------- 代码该赢：精确数量（数量写进题目，细则里逐个核对）
COUNT = [
    ("easy", S, "Exactly 7 red apples on a wooden table, clearly separated so each one can be counted.", "木桌上正好 7 个红苹果，彼此分开，能一个个数清。"),
    ("easy", L, "Exactly 5 hot-air balloons over a green valley, each a different color.", "绿色山谷上空正好 5 个热气球，每个颜色不同。"),
    ("medium", L, "A bookshelf with exactly 3 shelves; the top shelf has 4 books, the middle shelf 6 books, and the bottom shelf 2 books and a plant.", "一个正好 3 层的书架：上层 4 本书，中层 6 本书，下层 2 本书和一盆植物。"),
    ("medium", L, "A night sky with exactly 12 stars and one crescent moon above a dark hill.", "黑色山丘上方的夜空，正好 12 颗星星和一弯新月。"),
    ("medium", L, "Exactly 9 sheep in a field, with 1 black sheep among them and the rest white.", "草地上正好 9 只羊，其中 1 只黑羊，其余是白羊。"),
    ("easy", S, "A birthday cake with exactly 8 lit candles.", "一个插着正好 8 根点燃蜡烛的生日蛋糕。"),
    ("medium", L, "A parking lot seen from above with exactly 10 cars: 4 red, 3 white, 2 blue, and 1 yellow.", "俯视的停车场，正好 10 辆车：4 辆红色、3 辆白色、2 辆蓝色、1 辆黄色。"),
    ("hard", L, "A tree with exactly 6 birds on its branches and exactly 3 more birds flying above it.", "一棵树的树枝上正好有 6 只鸟，树上方另有正好 3 只鸟在飞。"),
    ("medium", L, "Exactly 4 lit lanterns and 2 unlit lanterns hanging in a row under the eaves of a teahouse.", "茶馆屋檐下挂成一排的灯笼：正好 4 盏亮着、2 盏没亮。"),
    ("hard", L, "A Van Gogh style night town with exactly 5 cats hidden in the scene (on roofs, in windows, on the street).", "梵高风格的夜晚小镇，画面里藏着正好 5 只猫（在屋顶、窗口、街上）。"),
    ("easy", L, "A row of exactly 6 colored pencils lying side by side, in rainbow order from left to right.", "并排躺着的正好 6 支彩色铅笔，从左到右按彩虹顺序排列。"),
    ("hard", L, "A chessboard in the standard starting position, with all 32 pieces on the board.", "国际象棋棋盘的标准开局摆放，32 个棋子全部在盘上。"),
]
# ---------------- 代码该赢：画面里的文字（文字写进题目，要求拼写完全正确）
TEXT = [
    ("easy", P, 'A minimalist concert poster with the title "MIDNIGHT ECHOES" at the top and "Live at the Riverside Hall · Oct 18" at the bottom.', '一张极简风格的音乐会海报：顶部标题 "MIDNIGHT ECHOES"，底部写 "Live at the Riverside Hall · Oct 18"。'),
    ("medium", L, 'A bakery storefront with a hand-painted sign reading "Fresh Bread Daily" above the window and a chalkboard reading "Croissant $3".', '一家面包店门面：橱窗上方手绘招牌写着 "Fresh Bread Daily"，旁边小黑板写着 "Croissant $3"。'),
    ("medium", P, "A Chinese calligraphy scroll with the four characters 山高水长 written vertically, with a red seal at the bottom.", "一幅竖写的中文书法条幅，写着「山高水长」四个字，下方盖一枚红印。"),
    ("easy", S, 'A coffee mug with the text "Hello, World" printed on its side.', '一只侧面印着 "Hello, World" 的咖啡杯。'),
    ("medium", L, 'A highway road sign in green with white text: "Exit 42 – Lakeview" with an arrow pointing right.', '高速公路的绿底白字路牌："Exit 42 – Lakeview"，箭头指向右边。'),
    ("medium", L, "A Japanese ramen shop at night with a noren curtain showing the characters ラーメン and a lantern with the character 麺.", "夜晚的日本拉面店：门帘上写着「ラーメン」，灯笼上写着「麺」字。"),
    ("hard", P, 'A vintage travel poster for an imaginary city with the title "VISIT AURELIA" and the smaller line "By Sea · By Air · By Rail".', '一张虚构城市的复古旅行海报：标题 "VISIT AURELIA"，下面小字 "By Sea · By Air · By Rail"。'),
    ("medium", L, 'A blackboard in a classroom with the equation "E = mc²" written in chalk and the date "October 2" in the corner.', '教室黑板上用粉笔写着方程 "E = mc²"，角落写着日期 "October 2"。'),
    ("easy", S, 'A birthday card with "Happy Birthday, Mia!" written in playful lettering, surrounded by balloons.', '一张生日贺卡，用活泼的字体写着 "Happy Birthday, Mia!"，四周有气球。'),
    ("hard", L, "A neon sign on a brick wall that reads OPEN 24 HOURS, with the letter U flickering off (dark) while the rest glow pink.", "砖墙上一块霓虹灯牌写着 OPEN 24 HOURS，其中字母 U 不亮，其余字母发粉光。"),
    ("medium", P, 'A book cover with the title "The Quiet Orbit" and the author name "L. Moreau", showing a small planet and a moon.', '一本书的封面：书名 "The Quiet Orbit"，作者 "L. Moreau"，画着一颗小行星和一个月亮。'),
    ("hard", L, 'A train station departure board listing three trains: "08:15 Lyon", "08:40 Geneva", "09:05 Milan".', '火车站的发车显示屏上列出三班车："08:15 Lyon"、"08:40 Geneva"、"09:05 Milan"。'),
    ("medium", S, 'A square app icon for a weather app: a stylized white cloud with a small sun, on a blue gradient, with rounded corners, and the word "Nimbus" written under the cloud.', '一个天气 App 的方形图标：风格化的白云配一个小太阳，蓝色渐变底，圆角，云下方写着 "Nimbus"。'),
]
# ---------------- 代码该赢：几何布局（能程序检查的写进 checks）
LAYOUT = [
    ("easy", L, "A national-flag style design with three vertical stripes of equal width: green on the left, white in the middle, orange on the right, filling the whole canvas.", "一面三色竖条旗样式的图：三条等宽竖条铺满画面，左绿、中白、右橙。",
     [{"type": "region_color", "box": [0.03, 0.05, 0.30, 0.95], "rgb": [0, 140, 69], "tol": 70},
      {"type": "region_color", "box": [0.37, 0.05, 0.63, 0.95], "rgb": [255, 255, 255], "tol": 40},
      {"type": "region_color", "box": [0.70, 0.05, 0.97, 0.95], "rgb": [255, 136, 62], "tol": 70}]),
    ("medium", L, "A watercolor illustration with a fountain in a university square on the left half and a red Japanese temple gate on the right half, cherry blossoms framing both.", "一幅水彩插画：左半边是大学广场上的喷泉，右半边是一座红色的日式寺庙山门，两边都有樱花环绕。", None),
    ("easy", S, "A perfectly symmetric butterfly centered on a plain white background, its left and right wings mirror images of each other.", "白色背景正中一只完全对称的蝴蝶，左右翅膀互为镜像。",
     [{"type": "region_color", "box": [0.0, 0.0, 0.08, 0.08], "rgb": [255, 255, 255], "tol": 25},
      {"type": "region_color", "box": [0.92, 0.92, 1.0, 1.0], "rgb": [255, 255, 255], "tol": 25}]),
    ("medium", L, "A sunset seascape where the horizon line sits exactly at one third of the image height from the bottom, and the sun is in the right third.", "一幅日落海景：海平线正好在从底部往上三分之一高度处，太阳在画面右三分之一区域。", None),
    ("easy", S, "A 3×3 grid of nine equal squares, each containing a different simple fruit icon, separated by thin white gaps on a dark background.", "九宫格：九个等大的方格，每格一个不同的简单水果图标，方格之间是细白缝，深色背景。", None),
    ("medium", P, "A poster layout: the top quarter is a solid deep red band with nothing in it; below it, a large white circle centered horizontally on a black background.", "海报版式：上四分之一是一条纯深红色色带，里面什么都没有；下面黑色背景上一个水平居中的大白圆。",
     [{"type": "region_color", "box": [0.05, 0.02, 0.95, 0.22], "rgb": [140, 0, 20], "tol": 70}]),
    ("medium", L, "Three identical houses in a row, evenly spaced, getting smaller toward the right as if receding along a street in one-point perspective.", "一排三座一模一样的房子，间距均匀，越往右越小，像是沿着街道按一点透视往远处退去。", None),
    ("hard", S, "A clock face showing exactly 3:40, with all 12 hour marks, numbered 1 to 12.", "一个钟面，指针正好指向 3:40，有 12 个小时刻度，标着 1 到 12。", None),
    ("easy", L, "A plain sky-blue background with a single small red kite in the upper-left corner and nothing else.", "纯天蓝色背景，左上角只有一只小红风筝，别的什么都没有。",
     [{"type": "region_color", "box": [0.45, 0.45, 0.95, 0.95], "rgb": [135, 206, 235], "tol": 50}]),
    ("medium", L, "A landscape split exactly in half vertically: the left half is a summer scene with green trees, the right half the same scene in winter with snow.", "一幅从中间竖着正好一分为二的风景：左半边是夏天、绿树，右半边是同一处风景的冬天、积雪。", None),
    ("hard", L, "A solar system diagram with the Sun on the far left and the eight planets in the correct order to the right, with Saturn's rings and Jupiter visibly the largest planet.", "太阳系示意图：太阳在最左边，八大行星按正确顺序向右排开，土星有环，木星明显最大。", None),
    ("medium", S, "Five concentric circles alternating red and white, centered on the canvas like a target.", "五个同心圆红白相间，居中排布，像一个靶子。",
     [{"type": "region_color", "box": [0.47, 0.47, 0.53, 0.53], "rgb": [220, 20, 30], "tol": 80}]),
    ("medium", L, "A city skyline silhouette in black against an orange sky, where the tallest building is exactly in the center of the image.", "橙色天空下的黑色城市天际线剪影，最高的楼正好在画面中央。", None),
]

# ---------------- 代码该赢：精确修改（工作区里给一份底稿程序，按一句话修改；edit_box 以外不能变）
# (底稿, 难度, 英文, 中文, edit_box)。底稿在 edit_bases/，参考图由 build_edit_refs.py 生成
EDIT = [
    ("pilot-11_codex_low", "medium", "Turn the sun into a crescent moon of about the same size, in the same place. Change nothing else.", "把太阳改成大小差不多、位置不变的一弯新月。别的都不要改。", [0.10, 0.08, 0.32, 0.36]),
    ("pilot-11_codex_low", "easy", "Change the two red flags on top of the castle to blue. Change nothing else.", "把城堡顶上的两面红旗改成蓝色。别的都不要改。", [0.60, 0.13, 0.73, 0.26]),
    ("pilot-11_claude_nolook", "easy", "Make the knight's red cape green. Change nothing else.", "把骑士的红披风改成绿色。别的都不要改。", [0.20, 0.64, 0.40, 0.98]),
    ("pilot-11_claude_nolook", "medium", "Make the roof of the rightmost tower blue instead of red, matching the blue of the small turrets. Change nothing else.", "把最右边那座塔的红屋顶改成蓝色，和小塔楼的蓝色一致。别的都不要改。", [0.70, 0.15, 0.90, 0.33]),
    ("pilot-11_claude_low", "medium", "Remove the setting sun, leaving the sky and hills behind it. Change nothing else.", "去掉正在落下的太阳，原位置露出后面的天空和山。别的都不要改。", [0.12, 0.40, 0.34, 0.66]),
    ("pilot-11_claude_low", "easy", "Change the yellow flag on the left tower to red. Change nothing else.", "把左边塔上的黄旗改成红色。别的都不要改。", [0.41, 0.13, 0.50, 0.25]),
    ("pilot-10_codex_high", "medium", "Remove the boat and the boatman, leaving calm water in their place. Change nothing else.", "去掉小船和船夫，原位置只留平静的水面。别的都不要改。", [0.52, 0.62, 0.74, 0.84]),
    ("pilot-10_codex_high", "medium", "Make the moon a thin crescent instead of a full moon, in the same place. Change nothing else.", "把满月改成一弯细细的新月，位置不变。别的都不要改。", [0.63, 0.12, 0.78, 0.32]),
    ("pilot-10_claude_low", "easy", "Change the larger red seal stamp below the poem into a blue stamp. Change nothing else.", "把诗句下方那枚较大的红色印章改成蓝色。别的都不要改。", [0.83, 0.30, 0.90, 0.40]),
    ("pilot-10_claude_low", "hard", "Replace the vertical title 月下孤舟 with 江上清风, in the same position, size and style. Change nothing else.", "把竖排标题「月下孤舟」换成「江上清风」，位置、大小、字体风格不变。别的都不要改。", [0.92, 0.05, 0.995, 0.32]),
    ("pilot-03_claude_low", "hard", "Change the characters on the large lantern at the upper left from 提灯 to 茶屋. Change nothing else.", "把左上方大灯笼上的字从「提灯」改成「茶屋」。别的都不要改。", [0.18, 0.08, 0.31, 0.31]),
    ("pilot-11_codex_nolook", "medium", "Add a small bat flying in front of the moon. Change nothing else.", "在月亮前面加一只小蝙蝠在飞。别的都不要改。", [0.66, 0.06, 0.86, 0.30]),
]


def row(i, cat, sub, size, diff, en, zh, src, note, checks=None, track_type="main"):
    return {
        "prompt": [{"role": "user", "content": en}],
        "reward_model": {"gate": {"size": size, "regen": "exact", "track": "main", "checks": checks or []},
                         "claims": []},
        "extra_info": {"task_id": f"dev-{i:03d}", "split": "dev", "track": "main", "category": cat,
                       "subtype": sub, "difficulty": diff, "prompt_zh": zh,
                       "source": {"type": "x" if src else "written", "url": src, "note": note},
                       "docker_image": "code2pixel/env:0.1"},
    }


def main():
    rows = []
    for t in T:
        rows.append(row(len(rows) + 1, *t))
    for diff, size, en, zh in COUNT:
        src = X + "MandelDuck/status/2103802923465768972" if "Van Gogh" in en else None
        rows.append(row(len(rows) + 1, "code_wins", "count", size, diff, en, zh, src,
                        "改写自梵高找猫游戏" if src else ""))
    for diff, size, en, zh in TEXT:
        src = X + "dotey/status/2104107699583463686" if "app icon" in en else None
        rows.append(row(len(rows) + 1, "code_wins", "text", size, diff, en, zh, src,
                        "改写自用 Canvas 设计 App 图标" if src else ""))
    for diff, size, en, zh, checks in LAYOUT:
        src = X + "Chi_Wang_/status/2039147221762154776" if "fountain" in en else None
        rows.append(row(len(rows) + 1, "code_wins", "layout", size, diff, en, zh, src,
                        "原题：左边喷泉、右边浅草寺的水彩，改为通用地点" if src else "", checks))
    for base, diff, en, zh, box in EDIT:
        r = row(len(rows) + 1, "code_wins", "edit", L, diff, en, zh, None, f"底稿：阶段 1 验收作品 {base}",
                [{"type": "unchanged_region", "ref": f"edit_bases/{base}/ref.png", "edit_box": box,
                  "tol": 12, "max_frac": 0.002}])
        r["extra_info"]["edit_base"] = f"edit_bases/{base}"
        rows.append(r)
    from claims_dev import CLAIMS, COMMON   # 细则初稿，见 claims_dev.py
    for r in rows:
        r["reward_model"]["claims"] = [{"text": t, "weight": w} for t, w in CLAIMS[r["extra_info"]["task_id"]] + COMMON]
    out = pathlib.Path(__file__).with_name("dev.jsonl")
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    print(f"{len(rows)} 题 → {out}")


if __name__ == "__main__":
    main()
