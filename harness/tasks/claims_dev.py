"""dev 集细则初稿（我起草，待两个模型交叉检查、用户抽查）。

每题 5–10 条能看图判是或否的说法。权重 2：题目里明确要求的内容；权重 1：合理性和质量。
写法：每条只核对一件事，用肯定句，裁判只看图回答 yes / no。
"""
R, Q = 2, 1   # 明确要求 / 质量与合理性

CLAIMS = {
    # ---------------- 风景
    "dev-001": [("A river winds through the scene between hills", R), ("The hills are covered with pink cherry blossom trees", R), ("A small wooden bridge crosses the river", R), ("Mountains are visible in the distance", R), ("The distant mountains look softened by haze", R), ("The scene reads as a Japanese spring landscape", Q), ("The perspective and scale of river, hills and bridge are consistent", Q)],
    "dev-002": [("The sky is violet or purple", R), ("Exactly two moons are visible in the sky", R), ("Crystalline rock formations are present", R), ("A small spaceship is parked on a ridge", R), ("A planet with rings is visible on the horizon", R), ("The terrain looks alien rather than Earth-like", Q), ("The spaceship is small relative to the landscape", Q)],
    "dev-003": [("A small sailing boat is present", R), ("The boat is on the face of a large wave with its bow pointing up toward the crest", R), ("The sky looks stormy", R), ("Both airborne spray and white foam are visible at the wave crest", R), ("The wave is clearly much larger than the boat", Q), ("The water looks like moving ocean water", Q)],
    "dev-004": [("The scene shows open ocean with no land in the foreground", R), ("The viewpoint is just above the water surface", R), ("The light is warm golden-hour light", R), ("Rolling swells are visible across the water", R), ("Sun glitter or sparkling reflections appear on the water", R), ("A few clouds are in the distance", R), ("The water surface looks realistic", Q)],
    "dev-005": [("Snow-capped mountains are present", R), ("A calm lake is in front of the mountains", R), ("The mountains are reflected in the lake", R), ("The lighting suggests sunset", R), ("The reflection is roughly a mirror image of the mountains", Q)],
    "dev-006": [("The scene is a bamboo forest", R), ("Mist or fog fills part of the scene", R), ("A narrow stone path leads into the fog", R), ("Rays of light fall between the bamboo stalks", R), ("The lighting suggests dawn", Q), ("Bamboo stalks have visible segment joints", Q)],
    "dev-007": [("It is night", R), ("The Milky Way is visible in the sky", R), ("Tall sand dunes are present", R), ("A single tree stands in silhouette", R), ("A small oasis pool reflects some stars", R), ("Only one tree is visible", Q), ("The tree has the flat-topped, umbrella-shaped crown of an acacia", R)],
    "dev-008": [("Red and orange maple trees line a river", R), ("Fallen leaves float on the water", R), ("A small waterfall is in the background", R), ("The season clearly reads as autumn", Q)],
    "dev-009": [("A volcano emits smoke", R), ("Glowing lava streams run down to the sea", R), ("Steam rises where lava meets the water", R), ("The lighting suggests dusk", R), ("The volcano is on an island surrounded by sea", R), ("The lava glows brighter than its surroundings", Q)],
    "dev-010": [("Green rolling hills fill the landscape", R), ("A single winding road crosses the hills", R), ("A red farmhouse is present", R), ("Big white clouds are in the sky", R), ("The vegetation is lush and green, with no autumn colors, bare branches or snow", Q)],
    "dev-011": [("A tall waterfall falls into a pool", R), ("The pool is turquoise", R), ("Canyon walls covered in moss surround the waterfall", R), ("The view looks upward from below", R), ("A rainbow appears in the mist", R)],
    "dev-012": [("Green aurora curtains fill the sky", R), ("Icebergs are present", R), ("The sea is frozen", R), ("A small red cabin is on the shore", R), ("The cabin's windows are lit", R)],
    "dev-013": [("A Möbius strip shape (a loop with a single twist) is the main structure", R), ("The structure floats in the sky", R), ("A road runs along the center of the strip", R), ("Trees and flower beds grow along both edges", R), ("The twist of the strip is visible", Q), ("The road follows the twist continuously", Q)],
    "dev-014": [("Terraced rice fields step down a mountainside", R), ("The terraces are flooded with water", R), ("The water reflects a pink sky", R), ("The lighting suggests sunrise", R), ("A few huts are on the slope", R), ("Terrace edges follow the contours of the slope", Q)],
    # ---------------- 街景
    "dev-015": [("A wide panoramic city skyline is shown", R), ("The sky shows sunset colors", R), ("A tall, slender, pointed pyramid skyscraper recognizable as the Transamerica Pyramid is near the center", R), ("A red-orange suspension bridge with two tall towers, recognizable as the Golden Gate Bridge, is on the left side", R), ("The style is crisp vector illustration with clean lines", R), ("The image shows many detailed buildings", Q)],
    "dev-016": [("The scene is a narrow alley at night", R), ("Red paper lanterns hang in the alley", R), ("A glowing vending machine is present", R), ("The stone pavement looks wet", R), ("Lights reflect on the wet pavement", Q), ("The alley looks Japanese", Q)],
    "dev-017": [("A café terrace with small round tables is shown", R), ("Striped awnings are present", R), ("It is evening and raining", R), ("Warm window light reflects on wet cobblestones", R), ("The street is paved with cobblestones", Q), ("The architecture reads as Parisian", Q)],
    "dev-018": [("The street slopes steeply", R), ("Houses are whitewashed", R), ("Doors are blue", R), ("Bougainvillea flowers hang over walls", R), ("The sea is visible at the bottom of the street", R)],
    "dev-019": [("Food stalls line the scene", R), ("Steam rises from food stalls", R), ("Hanging light bulbs are visible", R), ("Handwritten signs are present", R), ("A crowd of people walks between the stalls", R), ("It is night", Q), ("The signs in the market use Chinese characters", R)],
    "dev-020": [("Neon signs in several colors are present", R), ("It is raining", R), ("Flying cars appear between tall buildings", R), ("Puddles reflect the lights", R), ("The scene reads as a cyberpunk city", Q)],
    "dev-021": [("The street is in a quiet suburb with two-story houses", R), ("A row of yellow-leaved trees lines the street", R), ("A mailbox is present", R), ("A child's bicycle leans on a fence", R), ("The season reads as autumn", Q)],
    "dev-022": [("A canal runs through the scene", R), ("Gondolas are moored to striped poles", R), ("Old buildings in pastel colors line the canal", R), ("A small arched bridge crosses the canal", R), ("The lighting suggests sunset", R)],
    "dev-023": [("An old town square is covered in snow", R), ("A lit Christmas tree stands in the center", R), ("A wooden market stall is present", R), ("Windows glow warmly", R), ("Footprints are visible in the snow", R)],
    "dev-024": [("Neon signs overhang the street", R), ("A red-and-cream double-decker tram is present", R), ("Tall narrow apartment blocks line the street", R), ("The lighting suggests dusk", R), ("The street feels crowded with signs", Q)],
    "dev-025": [("Fishing boats are tied to a wooden pier", R), ("A lighthouse is present", R), ("Seagulls are in the scene", R), ("Lobster traps are stacked on the pier or shore", R), ("The lighting suggests morning", Q)],
    "dev-026": [("A Gothic cathedral facade fills much of the image", R), ("A round rose window is visible", R), ("Pointed arches are visible", R), ("Gargoyle sculptures are present", R), ("The facade is lit from below at night", R), ("A few small people stand on the steps", R), ("The people are tiny compared with the cathedral", Q)],
    "dev-027": [("Grey brick walls line a narrow lane", R), ("A red wooden door with brass knockers is present", R), ("A bicycle is present", R), ("Persimmons hang on a bare tree", R), ("The season reads as winter", Q)],
    "dev-028": [("Narrow gabled houses line a canal", R), ("Bicycles are parked along a railing", R), ("Houseboats are on the water", R), ("The houses are tall and narrow", Q), ("The scene reads as Amsterdam", Q)],
    # ---------------- 动物
    "dev-029": [("A shiba inu dog is lying in grass", R), ("A butterfly rests on the dog's nose", R), ("The dog looks sleepy or relaxed", R), ("The mood is cute and calm", Q), ("The dog is recognizable as a Shiba Inu: fox-like face, pointed upright ears and compact build (any typical Shiba coat color is acceptable)", Q)],
    "dev-030": [("A pigeon is flying", R), ("Its wings are spread", R), ("A city is visible below or behind it", R), ("The neck feathers are iridescent (green or purple sheen)", R), ("The pigeon is rendered in a realistic style", R), ("The bird's anatomy is plausible (two wings, one head, a tail; legs may be tucked out of sight)", Q), ("Individual feathers are clearly rendered on the wings and body, not just flat color shapes", R)],
    "dev-031": [("A domestic cat is shown in side view", R), ("The full body of the cat is visible", R), ("The cat is standing", R), ("The background is plain and light", R), ("The cat has no extra legs or tails, and no leg or tail is missing beyond natural overlap in side view", Q)],
    "dev-032": [("A red fox is present", R), ("The fox is in snow", R), ("The fox is looking back over its shoulder", R), ("The fox's body faces away from where its head is turned", Q)],
    "dev-033": [("An orange tabby cat is present", R), ("The cat is on a windowsill", R), ("Sunlight falls on the cat", R), ("The cat's fur shows tabby stripes", Q)],
    "dev-034": [("A humpback whale is leaping out of the ocean", R), ("Water streams off the whale's body", R), ("A small boat is in the distance", R), ("The boat is much smaller than the whale", Q), ("The whale has humpback features, most notably very long pectoral fins", Q)],
    "dev-035": [("A snowy owl (white owl) is present", R), ("It perches on a frosted branch", R), ("It is night", R), ("The owl's eyes are yellow", R), ("The owl looks straight at the viewer", R)],
    "dev-036": [("Several zebras are present", R), ("The zebras are drinking at a waterhole", R), ("The setting is savanna", R), ("The lighting suggests sunset", R), ("The zebras' reflections are visible in the water", R)],
    "dev-037": [("A hummingbird is hovering", R), ("The hummingbird hovers in front of a red hibiscus flower", R), ("The wings are blurred with motion", R), ("The bird is close to the flower", Q)],
    "dev-038": [("A tiger is walking", R), ("Tall grass surrounds the tiger", R), ("The setting is a forest clearing", R), ("Bands or patches of sunlight and shadow fall across the tiger's body", R), ("The tiger has black stripes on orange fur", Q)],
    "dev-039": [("A sea turtle is swimming", R), ("A coral reef is below it", R), ("Small tropical fish are around it", R), ("Light rays come down through the water", R)],
    "dev-040": [("A golden retriever puppy is sitting", R), ("Autumn leaves surround it", R), ("Its head is tilted", R), ("Its tongue is out", R)],
    "dev-041": [("A flamingo stands on one leg", R), ("It stands in a shallow pink lake", R), ("A reflection directly below the flamingo mirrors its pose, including the single standing leg", R), ("The water is still", Q)],
    "dev-042": [("A pelican is present", R), ("A bicycle is present", R), ("The pelican is riding the bicycle (seated on it, feet near the pedals)", R), ("The scene is along a seaside road", R), ("The bicycle has two wheels, a frame and handlebars", Q), ("The pelican has a long beak with a throat pouch", Q)],
    # ---------------- 人物
    "dev-043": [("An elderly man is present", R), ("He is reading a book", R), ("He is by a window", R)],
    "dev-044": [("A young woman is the main subject", R), ("She wears a yellow raincoat", R), ("She holds a clear (transparent) umbrella", R), ("It is raining", R), ("City lights are blurred behind her", R), ("The setting is a city street (e.g. wet pavement, sidewalk, buildings or traffic visible behind her)", R)],
    "dev-045": [("A musician plays a violin", R), ("The setting is a subway station", R), ("An open violin case with a few coins is present", R), ("Passing commuters are shown with motion blur", R)],
    "dev-046": [("Exactly four people sit around a table", R), ("The table is wooden", R), ("Dishes on the table are steaming", R), ("The scene is lit by warm lamp light at night", R), ("The people are laughing", R), ("The people have plates or bowls of food in front of them, as at a shared meal", Q)],
    "dev-047": [("A climber hangs from an overhanging cliff", R), ("A rope is visible", R), ("A chalk bag is visible", R), ("The ocean is far below", R)],
    "dev-048": [("Two children are present", R), ("They are flying a kite", R), ("The setting is a beach", R), ("The kite is high in the sky", R), ("The kite has a long tail", R), ("Besides the kite, something else shows wind, such as blowing hair, flapping clothing, blown sand or whitecapped waves", R)],
    "dev-049": [("A chef in a white uniform is present", R), ("The chef is arranging food on a plate", R), ("The setting is a restaurant kitchen", R), ("Flames rise from a pan in the background", R), ("Other kitchen staff or several active cooking stations are visible besides the chef", R)],
    "dev-050": [("A woman is jogging", R), ("She is on a riverside path", R), ("A city skyline is across the river", R), ("The lighting suggests sunrise", R)],
    "dev-051": [("The image is a close-up of a face", R), ("The subject is an old man with a weathered face", R), ("He wears a knitted cap", R), ("He has a grey beard", R), ("The lighting comes from the side", R)],
    "dev-052": [("An astronaut floats inside a space station", R), ("A large round window is behind the astronaut", R), ("Earth is visible through the window", R), ("The astronaut is not standing on the floor", Q)],
    "dev-053": [("A ballet dancer is in mid-leap", R), ("The stage is otherwise empty", R), ("A single spotlight shines from above", R), ("Dust particles are visible in the light beam", R)],
    "dev-054": [("A potter shapes a bowl on a spinning wheel", R), ("The potter's hands are covered in wet clay", R), ("Shelves of finished pots are in the background", R)],
    "dev-055": [("The image is a portrait-like depiction of a single subject", R), ("The subject is not a recognizable specific real person", Q), ("The image is a deliberate composed picture, not random noise", Q), ("The subject has a recognizable face, eye, or focal point", Q)],
    "dev-056": [("A group of hikers is on a mountain summit", R), ("One hiker is taking a photo", R), ("A sea of clouds is below them", R), ("The lighting suggests sunrise", R), ("The hikers appear to be resting", Q)],
    # ---------------- 静物
    "dev-057": [("A silver goblet is present", R), ("A lemon with its peel partly or fully removed (e.g. peel spiraling off) is present", R), ("Grapes are present", R), ("A half-eaten pie is present", R), ("The tablecloth is dark", R), ("The light comes from the left", R), ("The style resembles a Dutch Golden Age painting", R)],
    "dev-058": [("A cup of coffee with latte art is present", R), ("A croissant is on a small plate beside it", R), ("The table is wooden", R), ("The light feels like morning light", Q)],
    "dev-059": [("An open notebook is present", R), ("A fountain pen is present", R), ("An ink bottle is present", R), ("A brass desk lamp is present", R), ("A pair of round glasses is present", R), ("The desk looks vintage", Q)],
    "dev-060": [("A glass vase holds sunflowers", R), ("Water is visible inside the vase", R), ("Stems are visible through the glass", R), ("A few petals have fallen on the table", R)],
    "dev-061": [("The bowl is viewed from above (top-down or a high overhead angle), with its contents visible", R), ("Noodles are visible", R), ("A soft-boiled egg cut in half is present", R), ("Slices of pork are present", R), ("Nori (seaweed sheet) is present", R), ("Chopped green onions are present", R)],
    "dev-062": [("A wine glass is half filled with red wine", R), ("It stands on a marble surface", R), ("The glass shows sharp reflections", R), ("A caustic light pattern appears on the marble", R)],
    "dev-063": [("Several seashells are present", R), ("A starfish is present", R), ("A piece of driftwood is present", R), ("The objects lie on sand", R)],
    "dev-064": [("Exactly three books are stacked", R), ("The books look old", R), ("A red apple sits on top of the stack", R), ("The background is a plain grey wall", R)],
    "dev-065": [("A clay teapot is present", R), ("Exactly four small cups are present", R), ("They sit on a bamboo tray", R), ("Steam rises", R), ("A few loose tea leaves are scattered", R), ("The small cups are handleless, in the style of a Chinese gongfu tea set", R)],
    "dev-066": [("A slice of cake is on a plate", R), ("Strawberries are part of the cake", R), ("Layers of cream and sponge are visible on the cut side", R), ("A fork is present", R)],
    "dev-067": [("An old film camera is present", R), ("A roll of film is present", R), ("A few printed photographs are scattered", R), ("The table is wooden", R)],
    "dev-068": [("A transparent glass sphere is present", R), ("The floor has a checkered pattern", R), ("The checkered pattern is visible through the sphere", R), ("The checkered pattern seen through the sphere appears inverted (flipped upside down)", R)],
    "dev-069": [("Exactly five small succulents are present", R), ("Each succulent is in a terracotta pot", R), ("The succulents are of different kinds", R), ("They sit on a sunny windowsill", R)],
    "dev-070": [("A pocket watch lies open", R), ("Gears and springs inside are visible", R), ("It lies on dark velvet cloth", R)],
    # ---------------- 多物体
    "dev-071": [("A cat drinks milk from a bowl", R), ("The cat is by a window", R), ("A boy is outside the window", R), ("The boy is looking at the cat", R), ("The lighting suggests morning", R), ("The window separates the boy from the cat", Q)],
    "dev-072": [("The scene is in a voxel (blocky cube) style", R), ("A five-story pagoda is present", R), ("Cherry blossom trees are present", R), ("A red torii gate is present", R), ("A koi pond with a small bridge is present", R), ("A few tiny villagers are present", R), ("The pagoda has exactly five roof tiers", Q)],
    "dev-073": [("The room is shown in isometric view", R), ("A bed with a quilt is present", R), ("A desk with a computer is present", R), ("A lamp is on the desk", R), ("A bookshelf is present", R), ("A potted plant is present", R), ("A rug is present", R), ("A window shows evening light", R)],
    "dev-074": [("A mechanical butterfly is the main subject", R), ("Its wings are transparent", R), ("Brass gears are visible through the wings", R), ("The butterfly rests on a flower", R), ("The background is a workshop with tools", R)],
    "dev-075": [("A small mechanical boy sits at a desk", R), ("He writes with a quill pen", R), ("A panel in his back is open", R), ("Gears and cams are visible through the open panel", R), ("The figure looks antique", Q)],
    "dev-076": [("A whale flies through clouds", R), ("The whale's body is made of riveted brass plates", R), ("Portholes are on the whale's body", R), ("Propellers are on its fins", R), ("A small airship flies beside it", R)],
    "dev-077": [("A sailing ship is under full sail", R), ("A black flag flies on the ship", R), ("Cannons line the ship's side", R), ("The sea is rough", R), ("The sky is stormy", R), ("The ship looks like an 18th-century sailing ship", Q)],
    "dev-078": [("A two-door sports coupe is shown", R), ("The car is shown in side view", R), ("The car is deep metallic blue", R), ("The background is a plain studio background", R), ("A soft shadow is under the car", R), ("The car has contemporary styling (low sleek body, modern headlights and wheels), not a vintage or classic design", Q)],
    "dev-079": [("A handheld game console is shown", R), ("A separate controller module is attached on each side of the console, divided from the main body by a visible seam or gap", R), ("The controllers are colored", R), ("The screen shows a star-shaped logo", R)],
    "dev-080": [("A checkered blanket is present", R), ("A wicker basket is present", R), ("Sandwiches are present", R), ("A bottle of lemonade is present", R), ("A dog is present", R), ("Two people are reading under a tree", R)],
    "dev-081": [("Several clocks of different shapes hang on a wall", R), ("Tools are on the workbench", R), ("A magnifying lamp is present", R), ("An opened clock with its parts laid out is present", R)],
    "dev-082": [("A slide is present", R), ("Swings are present", R), ("A sandbox with a bucket and spade is present", R), ("A seesaw is present", R), ("An adult sits on a bench", R), ("The lighting suggests afternoon", Q)],
    "dev-083": [("The image shows an underground cross-section", R), ("Tunnels connect chambers", R), ("A chamber contains eggs", R), ("Ants carry leaves", R), ("Grassy surface is visible above", R)],
    "dev-084": [("A donut planet is present", R), ("A watermelon planet is present", R), ("A pizza planet is present", R), ("A cookie planet is present", R), ("An orange serves as the sun", R), ("A small rocket is present", R), ("The food planets appear to orbit the orange sun", Q)],
    "dev-085": [("Tall wooden bookshelves fill the room", R), ("A rolling ladder leans on a shelf", R), ("A cat sleeps on a stack of books", R), ("A reading armchair with a lamp is present", R), ("The space feels cozy and warm", Q)],
    # ---------------- 指定画风
    "dev-086": [("The image is in Chinese ink-wash style", R), ("A lone boat is on water", R), ("A fisherman is in the boat", R), ("A moon is in the sky", R), ("Distant mountains are present", R), ("Reeds are present", R), ("A red seal stamp is present", R)],
    "dev-087": [("The image is pixel art", R), ("A castle is present", R), ("The lighting suggests dusk", R), ("A knight walks along a path toward the castle", R), ("Pixels are visibly blocky at the image's scale", Q)],
    "dev-088": [("The image is pixel art", R), ("A fox is in a forest clearing", R), ("Mushrooms are present", R), ("Fireflies are present", R), ("A small stream is present", R), ("The image uses a small set of flat colors: shading is done in a few distinct color steps, with no smooth gradients", R), ("The fox looks cute, e.g. a large head or big eyes relative to its body and a friendly expression", Q), ("The scene is richly detailed, with many small pixel-level details (such as grass tufts, leaves, mushroom spots, ripples) rather than a few large flat shapes", Q)],
    "dev-089": [("The image is pixel art", R), ("A wizard holds a staff", R), ("The wizard appears to be casting a spell", R), ("Glowing particles surround the staff", R), ("The image uses a small set of flat colors: shading is done in a few distinct color steps, with no smooth gradients", R)],
    "dev-090": [("The sky is painted with swirling strokes like Van Gogh's Starry Night", R), ("A small town is below the sky", R), ("A cypress tree is present", R), ("A church spire is present", R), ("It is night", R), ("Visible brush-stroke texture is present", Q)],
    "dev-091": [("The scene looks like claymation (clay figures and props)", R), ("A small clay house with a garden is present", R), ("A clay mailman is delivering a letter", R), ("Fingerprint-like impressions (small curved ridges or thumb smudges) are visible on the clay surfaces", R)],
    "dev-092": [("The image looks like sand art on a backlit glass table", R), ("An adult woman and a small child are shown walking together", R), ("A tree is present", R), ("Shading is made from different densities of sand", R)],
    "dev-093": [("The image is in watercolor style", R), ("A lighthouse stands on a rocky coast", R), ("Loose washes are visible", R), ("Paper texture is visible", R), ("Soft bleeding edges are visible", R)],
    "dev-094": [("The image looks like an impasto oil painting", R), ("A wheat field is shown", R), ("The sky is stormy", R), ("Many thick, visible brush strokes make up the image", R)],
    "dev-095": [("The style is cel-shaded anime background art", R), ("A small rural railway station is shown", R), ("Cumulus clouds are in the sky", R), ("Power lines are present", R), ("The season reads as summer", R), ("Leafy green trees are visible near the station", R)],
    "dev-096": [("The image looks like a ukiyo-e woodblock print", R), ("Fishing boats are on big waves", R), ("A snowy mountain is in the distance", R), ("Colors are flat with bold outlines", R)],
    "dev-097": [("The image is low-poly with visible flat triangles", R), ("Faceted mountains are present", R), ("A lake is present", R), ("Pine trees are present", R), ("The sky shows sunset colors", R)],
    "dev-098": [("The image is a blueprint: white lines on blue", R), ("A steam locomotive is shown in side view", R), ("Dimension lines are present", R), ("Text labels are present", R)],
    "dev-099": [("A 3D fractal shape like a Mandelbulb is shown", R), ("The fractal is golden", R), ("The background is dark", R), ("Soft lighting with shadowed crevices (ambient occlusion) is visible", R)],
    "dev-100": [("The illustration is isometric and flat-shaded", R), ("A tiny island is shown", R), ("A lighthouse is present", R), ("A cottage is present", R), ("A dock is present", R), ("A sailboat is present", R), ("The colors are pastel", R)],
}

# ---------------- 代码该赢：数量、文字、布局、精确修改
CLAIMS.update({
    # 精确数量
    "dev-101": [("Exactly 7 apples are visible", R), ("All apples are red", R), ("The apples sit on a wooden table", R), ("Each apple is separate and countable", R)],
    "dev-102": [("Exactly 5 hot-air balloons are visible", R), ("Each balloon has a different color", R), ("A green valley is below them", R)],
    "dev-103": [("The bookshelf has exactly 3 shelves", R), ("The top shelf holds exactly 4 books", R), ("The middle shelf holds exactly 6 books", R), ("The bottom shelf holds exactly 2 books", R), ("The bottom shelf also holds a plant", R)],
    "dev-104": [("Exactly 12 stars are visible", R), ("Exactly one crescent moon is visible", R), ("A dark hill is below the sky", R)],
    "dev-105": [("Exactly 9 sheep are visible", R), ("Exactly 1 sheep is black", R), ("The other sheep are white", R), ("The sheep are in a field", R)],
    "dev-106": [("A birthday cake is present", R), ("Exactly 8 candles are on the cake", R), ("All candles are lit", R)],
    "dev-107": [("The parking lot is seen from above", R), ("Exactly 10 cars are visible", R), ("Exactly 4 cars are red", R), ("Exactly 3 cars are white", R), ("Exactly 2 cars are blue", R), ("Exactly 1 car is yellow", R)],
    "dev-108": [("A tree is present", R), ("Exactly 6 birds sit on the branches", R), ("Exactly 3 birds fly above the tree", R)],
    "dev-109": [("Lanterns hang in a row under eaves", R), ("Exactly 4 lanterns are lit", R), ("Exactly 2 lanterns are unlit", R), ("The building is a teahouse", Q)],
    "dev-110": [("The town is painted in Van Gogh style", R), ("It is night", R), ("Exactly 5 cats are visible in the scene", R), ("Cats appear in different places (roof, window, street)", R)],
    "dev-111": [("Exactly 6 colored pencils are visible", R), ("The pencils lie side by side", R), ("From left to right the pencils are red, orange, yellow, green, blue and violet/purple", R)],
    "dev-112": [("A chessboard with 8×8 alternating squares is shown", R), ("All 32 pieces are on the board", R), ("Each side has 8 pawns on its second rank", R), ("Viewed from White's side, both back ranks read rook, knight, bishop, queen, king, bishop, knight, rook from left to right", R), ("Each queen stands on a square of its own color", R), ("The board is oriented so that each player has a light square at the right-hand corner of their back rank", Q)],
    # 画面文字
    "dev-113": [('The title "MIDNIGHT ECHOES" is spelled correctly at the top', R), ('The line "Live at the Riverside Hall · Oct 18" is spelled correctly at the bottom', R), ("The design is minimalist", R), ("No other visible text is misspelled or garbled", R)],
    "dev-114": [("A bakery storefront is shown", R), ('A sign above the window reads exactly "Fresh Bread Daily"', R), ('A chalkboard reads exactly "Croissant $3"', R), ("The main sign looks hand-painted", R), ("No other visible text is misspelled or garbled", R)],
    "dev-115": [("A vertical calligraphy scroll is shown", R), ("The characters are exactly 山高水长, in that order", R), ("The characters are written vertically", R), ("A red seal is at the bottom", R), ("The characters are correctly formed with no missing or extra strokes", R)],
    "dev-116": [("A coffee mug is shown", R), ('The text "Hello, World" is printed on its side, spelled correctly with the comma', R), ("The text follows the curve or surface of the mug plausibly", Q)],
    "dev-117": [("A green highway sign is shown", R), ("The text is white", R), ('The sign reads "Exit 42 – Lakeview" exactly', R), ("An arrow points right", R)],
    "dev-118": [("A ramen shop at night is shown", R), ("A noren curtain shows the characters ラーメン exactly", R), ("A lantern shows the character 麺", R), ("The characters are correctly formed", R)],
    "dev-119": [("A vintage travel poster is shown", R), ('The title "VISIT AURELIA" is spelled correctly', R), ('The line "By Sea · By Air · By Rail" is spelled correctly', R), ("The style looks vintage", R), ("The line \"By Sea \u00b7 By Air \u00b7 By Rail\" is set in noticeably smaller lettering than \"VISIT AURELIA\"", R)],
    "dev-120": [("A classroom blackboard is shown", R), ('The equation "E = mc²" is written with a superscript 2', R), ('The date "October 2" appears in a corner', R), ("The writing looks like chalk", R)],
    "dev-121": [("A birthday card is shown", R), ('It reads "Happy Birthday, Mia!" spelled correctly with the exclamation mark', R), ("Balloons surround the text", R), ("The lettering looks playful", Q)],
    "dev-122": [("A neon sign is mounted on a brick wall", R), ("The sign reads OPEN 24 HOURS", R), ("The letter U is dark (not lit)", R), ("All other characters, including the digits 2 and 4, glow pink", R)],
    "dev-123": [("A book cover is shown", R), ('The title "The Quiet Orbit" is spelled correctly', R), ('The author name "L. Moreau" is spelled correctly', R), ("A small planet and a moon are illustrated", R)],
    "dev-124": [("A train departure board is shown", R), ('It lists "08:15 Lyon"', R), ('It lists "08:40 Geneva"', R), ('It lists "09:05 Milan"', R), ("Exactly three trains are listed", R)],
    "dev-125": [("A square app icon with rounded corners is shown", R), ("A stylized white cloud is the main shape", R), ("A small sun appears with the cloud", R), ("The background is a blue gradient", R), ('The name "Nimbus" appears, spelled correctly', R)],
    # 几何布局
    "dev-126": [("The image consists of three vertical stripes", R), ("The stripes are of equal width", R), ("The left stripe is green", R), ("The middle stripe is white", R), ("The right stripe is orange", R), ("The stripes fill the whole canvas", R)],
    "dev-127": [("The image is in watercolor style", R), ("A fountain in a square is on the left half", R), ("A red Japanese temple gate is on the right half", R), ("Cherry blossoms frame both sides", R), ("Behind the fountain on the left stands an academic-looking building (e.g. classical facade, columns or a clock tower), suggesting a university square", Q)],
    "dev-128": [("A single butterfly is centered", R), ("The whole butterfly is mirror-symmetric about a vertical center line: the left and right wings (shape and pattern) and the antennae match", R), ("The background is plain white", R)],
    "dev-129": [("A sea horizon is visible", R), ("The horizon is at about one third of the image height from the bottom", R), ("The sun is in the right third of the image", R), ("The scene shows sunset", R)],
    "dev-130": [("The image shows a 3×3 grid of nine squares", R), ("The squares are equal in size", R), ("Each square contains a different fruit icon", R), ("Thin white gaps separate the squares", R), ("The background is dark", R), ("The fruit icons are simple flat graphics made of a few shapes and colors, not detailed or photorealistic renderings", Q)],
    "dev-131": [("The top quarter is a solid deep red band", R), ("The red band contains nothing else", R), ("A large white circle is below the band", R), ("The circle is horizontally centered", R), ("The background below the band is black", R)],
    "dev-132": [("Exactly three houses are in a row", R), ("The houses look identical apart from size", R), ("The houses get smaller toward the right", R), ("The arrangement reads as one-point perspective along a street", R), ("The houses are evenly spaced (gaps shrink consistently with the perspective)", R)],
    "dev-133": [("A clock face is shown", R), ("The time shown is 3:40 (hour hand between 3 and 4, closer to 4; minute hand on 8)", R), ("All 12 hour marks are present", R), ("The numbers 1 to 12 are present in the correct positions", R)],
    "dev-134": [("The background is plain sky blue", R), ("A single small red kite is in the upper-left corner", R), ("Nothing else is in the image", R)],
    "dev-135": [("The image is split vertically at the center", R), ("The left half shows summer with green trees", R), ("The right half shows winter with snow", R), ("Both halves show the same scene", R)],
    "dev-136": [("The Sun is on the far left", R), ("Eight planets are arranged to the right", R), ("The planets are in the correct order from the Sun", R), ("Saturn has rings", R), ("Jupiter is the largest planet", R)],
    "dev-137": [("Counting the central disk and each ring around it (not the background), there are exactly five concentric color bands", R), ("The circles alternate red and white", R), ("The circles are centered on the canvas", R), ("The innermost disk is red", R)],
    "dev-138": [("A black city skyline silhouette is shown", R), ("The sky is orange", R), ("The tallest building is at the horizontal center of the image", R)],
    # 精确修改（框外不变由程序判；细则只看改动本身）
    "dev-139": [("The sun has been replaced by a crescent moon", R), ("The crescent is in the same position as the old sun", R), ("The crescent is about the same size as the old sun", R), ("The rest of the scene looks unchanged", Q)],
    "dev-140": [("The two flags on top of the castle are blue", R), ("No red flag remains on the castle top", R), ("The flags keep their shape and position", R), ("Apart from the flags' color, the image looks the same as the original, including the flagpoles and the tower top", Q)],
    "dev-141": [("The knight's cape is green", R), ("The cape keeps its shape", R), ("The rest of the knight is unchanged in color", R)],
    "dev-142": [("The roof of the rightmost tower is blue", R), ("Its blue matches the small turrets' roofs", R), ("The other roofs keep their original colors: the left tower's roof is still red and the central and small turret roofs are still blue", Q)],
    "dev-143": [("The setting sun is gone", R), ("Sky and hills fill the place where the sun was, without a hole or artifact", R), ("The sky colors around that area look natural", Q), ("Apart from the removed sun, the image matches the original, including the mountains and trees next to where the sun was", Q)],
    "dev-144": [("The flag on the left tower is red", R), ("The flag keeps its shape and position", R), ("The flag on the right tower is still yellow and the flag on the central tower is still red", Q)],
    "dev-145": [("The boat is gone", R), ("The boatman is gone", R), ("Calm water fills the area without visible artifacts", R)],
    "dev-146": [("The moon is a thin crescent", R), ("The crescent is in the same place as the old moon", R), ("The rest of the painting is unchanged", Q)],
    "dev-147": [("The larger seal below the poem is blue", R), ("The seal keeps its shape, size and characters", R), ("The smaller seal below the title is still red", Q)],
    "dev-148": [("The vertical title now reads 江上清风", R), ("The old title 月下孤舟 is gone", R), ("The new title is in the same position, size and style", R), ("The characters are correctly formed", R)],
    "dev-149": [("The large lantern at the upper left now shows 茶屋", R), ("The characters 提灯 are gone from that lantern", R), ("The lantern keeps its shape, color and glow", R), ("The characters are correctly formed", R)],
    "dev-150": [("A small bat flies in front of the moon", R), ("The bat's wingspan is smaller than the moon's diameter", Q), ("The moon is otherwise unchanged", R), ("Apart from the added bat, the image matches the original, including the tower spire and red flag next to the moon", Q)],
})

# 每题都加的通用质量细则
COMMON = [("The image has no obvious rendering artifacts, glitches, or broken shapes", Q),
          ("The image has a clear main subject and a readable composition", Q)]

# 更难的质量细则（2026-10-02 用户定"细则当门槛、两两比较当主分，再加质量细则"）。
# 阶段 4 实跑里原有细则大多只核对"有没有"，一张干净的扁平插画就能全部满足，60 次里 52 次满分。
# 这些说法核对"做得好不好"：光影一致、纵深、材质、解剖结构、完成度。按类别加，精确修改题不加（画面是底稿的）。
# 2026-10-03 一度删过 7 条看似没区分度的说法，后来全部恢复：光影一致、完成度、纵深能把 Sonnet 5 分出来；
# 材质、遮挡、比例一致、文字清晰各只有 2–3 题、也没测过更弱的模型，证据不够，不删（用户定）。见 docs/PHASE4.md。
QUALITY_ALL = [("Lighting is consistent across the scene: highlights and shadows agree on where the light comes from", Q),
               ("The image has a finished, professional level of detail rather than looking like simple placeholder shapes", Q)]
QUALITY = {
    "landscape": [("Depth reads convincingly: distant elements are smaller, softer or hazier than near ones", Q),
                  ("Surfaces such as foliage, rock, water or sky have believable texture rather than flat uniform fills", Q)],
    "street": [("Buildings and the street follow a consistent perspective", Q),
               ("Surfaces such as walls, pavement, glass or signs have believable texture rather than flat uniform fills", Q)],
    "animal": [("The animal's anatomy is correct for its species: proportions, limbs, eyes and ears look right", Q),
               ("Fur, feathers or skin are rendered with visible texture rather than flat fills", Q)],
    "people": [("Faces are well formed: eyes, nose and mouth are correctly placed and proportioned", Q),
               ("Any visible hands have a plausible shape and number of fingers (yes if no hands are visible)", Q),
               ("Body proportions and poses are anatomically plausible", Q)],
    "still_life": [("Different materials are distinguishable: glass, metal, fabric, wood or food each look like their material", Q),
                   ("Objects cast shadows or contact shadows that ground them on the surface they rest on", Q)],
    "multi_object": [("All objects share a consistent scale and perspective", Q),
                     ("Where objects overlap, the nearer one correctly hides the farther one (yes if nothing overlaps)", Q)],
    "style": [("The style is executed convincingly with techniques characteristic of it (brushwork, palette, line quality), "
               "not just a generic filter look", Q)],
    "count": [("Shapes have clean edges with no stray marks, gaps or misalignments", Q)],
    "layout": [("Shapes have clean edges with no stray marks, gaps or misalignments", Q)],
    "text": [("All text is crisp and legible with even letter spacing and no malformed characters", Q)],
}


def quality_claims(category, subtype):
    """一道题要加的质量细则；精确修改题不加。"""
    if subtype == "edit":
        return []
    key = subtype if category == "code_wins" else category
    return QUALITY_ALL + QUALITY.get(key, [])
