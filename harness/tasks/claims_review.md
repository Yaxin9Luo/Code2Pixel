# dev 集细则：待你确认的清单

生成：`harness/tasks/crosscheck_claims.py`（Opus 5.5 和 gpt-6.1-sol 各审一遍，推理强度 medium）。
两个模型都标出的 21 条已经按建议改了；下面是只有一个模型标出的 73 条，以及抽查用的 30 道题。

在方括号里打 x 表示采纳建议，留空表示保持原样；有别的改法直接写在条目下面。

**2026-10-02 已审**：按用户意见改由 5 个 subagent 逐条审核（分歧 3 组、抽查 2 组），结论写在每条下面的“审核”一行，已全部写进 claims_dev.py 和 build_dev.py。精确修改题按“裁判能同时看到底稿图”处理。

## 一、只有一个模型标出的问题


### dev-003　A small sailing boat climbing a large ocean wave under a stormy sky, with spray and foam at the wave crest.

- [x] **漏了要求**（gpt-6.1-sol）
  - 理由：The prompt requires both spray and foam, but the existing disjunctive claim can pass when only one is present.
  - 建议：Both airborne spray and white foam are visible at the wave crest.
  - 审核：采纳。The prompt asks for spray and foam, so the 'or' lets an image with only one of them pass.
- [x] **漏了要求**（gpt-6.1-sol）
  - 理由：Being on a wave slope does not check that the boat is climbing the wave.
  - 建议：The sailing boat is oriented up the wave slope, with its bow pointing toward the crest.
  - 审核：改写后采纳（权重 2）：The boat is on the face of a large wave with its bow pointing up toward the crest。Replacing the existing slope claim rather than adding a second one checks 'climbing' without making the two claims overlap.

### dev-010　Rolling green hills in early summer with a single winding road, a red farmhouse, and big white clouds.

- [x] **漏了要求**（gpt-6.1-sol）
  - 理由：No claim checks the explicitly requested early-summer appearance.
  - 建议：The landscape has an early-summer appearance, with lush green vegetation and no autumn or winter cues.
  - 审核：改写后采纳（权重 1）：The vegetation is lush and green, with no autumn colors, bare branches or snow。'Early-summer appearance' is too vague to judge, so this uses concrete season cues; weight 1 because it partly overlaps the green-hills claim.

### dev-015　A wide panoramic illustration of the San Francisco skyline at sunset, with the Transamerica Pyramid near the center and the Golden Gate Bridge on the left, in a crisp, detailed vector style.

- [x] **漏了要求**（gpt-6.1-sol）
  - 理由：The generic pyramid-shaped-building claim does not check the specifically requested Transamerica Pyramid.
  - 建议：The building near the center is recognizable as the Transamerica Pyramid, including its characteristic taper and side wings.
  - 审核：改写后采纳（权重 2）：A tall, slender, pointed pyramid skyscraper recognizable as the Transamerica Pyramid is near the center。A named landmark deserves its own check, but requiring the side wings is too strict for a vector style, so this replaces the generic claim with the slender taper only.
- [x] **漏了要求**（gpt-6.1-sol）
  - 理由：The generic red-suspension-bridge claim does not check the specifically requested Golden Gate Bridge.
  - 建议：The bridge on the left is recognizable as the Golden Gate Bridge, with its characteristic towers and suspension cables.
  - 审核：改写后采纳（权重 2）：A red-orange suspension bridge with two tall towers, recognizable as the Golden Gate Bridge, is on the left side。This names the requested landmark and its towers in place of the generic bridge claim, without asking for fine structural detail.

### dev-019　A busy night market in Taipei: food stalls with steam rising, hanging light bulbs, handwritten signs, and crowds of people walking between the stalls.

- [x] **漏了要求**（gpt-6.1-sol）
  - 理由：No claim checks the explicitly requested Taipei setting rather than a generic night market.
  - 建议：The market has the visual character of a Taipei night market, including Taiwanese-style stalls and signage.
  - 审核：改写后采纳（权重 2）：The signs in the market use Chinese characters。'Taiwanese-style stalls' can't be checked; Chinese-character signage is the concrete visual cue that sets Taipei apart from a generic night market.

### dev-029　A sleepy shiba inu lying in the grass with a butterfly resting on its nose; cute, calm and a little playful.

- [x] **含糊**（gpt-6.1-sol）：The dog is recognizable as a shiba inu (curled tail or fox-like face, tan and white coat)
  - 理由：The parenthetical can be read as requiring a tan-and-white coat even though Shiba Inu also have other valid coat colors.
  - 建议：The dog is recognizable as a Shiba Inu from its compact build, pointed ears and fox-like face, without requiring a particular coat color.
  - 审核：改写后采纳（权重 1）：The dog is recognizable as a Shiba Inu: fox-like face, pointed upright ears and compact build (any typical Shiba coat color is acceptable)。This drops the required coat color and the tail, which a lying dog may hide, and keeps the features that are always visible.
- [ ] **漏了要求**（gpt-6.1-sol）
  - 理由：The claims check cute and calm but omit the requested slightly playful mood.
  - 建议：The butterfly-on-nose interaction gives the scene a slightly playful appearance.
  - 审核：不采纳。The butterfly-on-nose claim already covers where the playfulness comes from, and the suggested claim is as vague as the mood claim it would add to.

### dev-030　A hyper-detailed, realistic pigeon in flight over a city, wings spread, with iridescent neck feathers catching the light.

- [x] **漏了要求**（gpt-6.1-sol）
  - 理由：Realistic style and iridescence do not check the explicitly requested hyper-detailed rendering.
  - 建议：Fine individual feather structure and other small anatomical details are clearly rendered on the pigeon.
  - 审核：改写后采纳（权重 2）：Individual feathers are clearly rendered on the wings and body, not just flat color shapes。Hyper-detailed is an explicit requirement that the realism claim doesn't cover, and feather-level detail is the concrete thing to check.

### dev-031　A clean side-view illustration of a domestic cat standing, full body, on a plain light background.

- [x] **含糊**（gpt-6.1-sol）：The cat has four legs and one tail
  - 理由：A side view can legitimately hide a leg or part of the tail, making it unclear whether the claim counts visible parts or inferred anatomy.
  - 建议：The visible anatomy is consistent with a four-legged cat with one tail, allowing natural overlap or occlusion in side view.
  - 审核：改写后采纳（权重 1）：The cat has no extra legs or tails, and no leg or tail is missing beyond natural overlap in side view。In side view legs often overlap, so the claim should penalize only wrong anatomy, not natural occlusion.

### dev-034　A humpback whale breaching out of the ocean, water streaming off its body, with a small boat in the distance for scale.

- [x] **漏了要求**（gpt-6.1-sol）
  - 理由：The claims check a whale breaching but never that it is a humpback.
  - 建议：The breaching whale is recognizable as a humpback, with characteristic long pectoral fins and body shape.
  - 审核：改写后采纳（权重 1）：The whale has humpback features, most notably very long pectoral fins。The existing claim names humpback but a judge would pass any whale; long pectoral fins are the one checkable marker. Weight 1 matches how dev-029 treats breed recognizability.

### dev-037　A hummingbird hovering in front of a red hibiscus flower, wings blurred with motion.

- [ ] **错误**（Opus 5.5）：A red hibiscus flower is in front of it
  - 理由：The prompt has the hummingbird hovering in front of the flower; the claim reverses this and puts the flower in front of the bird.
  - 建议：The hummingbird hovers in front of a red hibiscus flower
  - 审核：不采纳。Already fixed: claims_dev.py has the suggested wording, so no change is needed.

### dev-038　A Bengal tiger walking through tall grass in a forest clearing, sunlight striping its fur.

- [x] **漏了要求**（gpt-6.1-sol）
  - 理由：The sunlight claim checks illumination but not the explicitly requested stripes of sunlight.
  - 建议：Bands of sunlight and shadow stripe the tiger's fur, separately from its natural black markings.
  - 审核：改写后采纳（权重 2）：Bands or patches of sunlight and shadow fall across the tiger's body。Sunlight 'striping' its fur means light-and-shadow bands; this replaces the plain illumination claim and doesn't depend on telling them apart from the tiger's own stripes.

### dev-041　A flamingo standing on one leg in a shallow pink lake, its reflection perfectly mirrored in the still water.

- [x] **漏了要求**（gpt-6.1-sol）
  - 理由：A visible reflection does not check the prompt's requirement that it perfectly mirror the flamingo.
  - 建议：The reflection mirrors the flamingo's visible pose and outline directly below it in the still water.
  - 审核：改写后采纳（权重 2）：A reflection directly below the flamingo mirrors its pose, including the single standing leg。'Perfectly mirrored' requires a reflection that matches the bird's pose, not just one that exists, so this replaces the existing claim.

### dev-044　A portrait of a young woman in a yellow raincoat standing on a rainy street, holding a clear umbrella, city lights blurred behind her.

- [x] **漏了要求**（gpt-6.1-sol）
  - 理由：No claim checks that the woman is standing on a street.
  - 建议：The woman is standing on a rainy city street.
  - 审核：改写后采纳（权重 2）：The setting is a city street (e.g. wet pavement, sidewalk, buildings or traffic visible behind her)。The street setting is explicit; the examples keep it decidable when a tight portrait crops out the ground.

### dev-046　A family of four having dinner around a wooden table at night, warm lamp light, steaming dishes, everyone laughing.

- [x] **漏了要求**（gpt-6.1-sol）
  - 理由：The claims check four laughing people and dishes but do not check that they are having dinner.
  - 建议：The four people are gathered around the table eating or sharing a dinner meal.
  - 审核：改写后采纳（权重 1）：The people have plates or bowls of food in front of them, as at a shared meal。This separates eating dinner from just sitting near cooked dishes. Weight 1 because it largely overlaps the steaming-dishes claim.

### dev-048　Two children flying a kite on a windy beach, the kite high in the sky with a long tail.

- [x] **漏了要求**（gpt-6.1-sol）
  - 理由：The claims omit the explicitly requested windy conditions.
  - 建议：The kite tail, clothing or other visible elements show wind blowing across the beach.
  - 审核：改写后采纳（权重 2）：Besides the kite, something else shows wind, such as blowing hair, flapping clothing, blown sand or whitecapped waves。Windy is explicit, and a flying kite's tail alone is not separate evidence of wind, so the claim asks for another cue.

### dev-049　A chef in a white uniform plating a dish in a busy restaurant kitchen, flames from a pan in the background.

- [x] **漏了要求**（gpt-6.1-sol）
  - 理由：The existing restaurant-kitchen claim does not check the explicitly requested busy appearance.
  - 建议：The restaurant kitchen shows visible activity around the chef, such as other working staff or active cooking stations.
  - 审核：改写后采纳（权重 2）：Other kitchen staff or several active cooking stations are visible besides the chef。'Busy' is explicit, and other staff or multiple active stations is something a judge can actually check.

### dev-057　A Dutch Golden Age style still life: a silver goblet, a peeled lemon, grapes, and a half-eaten pie on a dark tablecloth, lit from the left.

- [x] **题目没要求**（gpt-6.1-sol）：A partly peeled lemon is present
  - 理由：The prompt requests a peeled lemon without requiring it to be only partly peeled.
  - 建议：A partly or fully peeled lemon is present.
  - 审核：改写后采纳（权重 2）：A lemon with its peel partly or fully removed (e.g. peel spiraling off) is present。The prompt says only 'peeled', so a fully peeled lemon should also pass.

### dev-061　A bowl of ramen seen from above: noodles, a soft-boiled egg cut in half, slices of pork, nori, and green onions.

- [x] **题目没要求**（gpt-6.1-sol）：The bowl is viewed from directly above
  - 理由：Seen from above permits an oblique elevated view and does not require an exactly overhead camera.
  - 建议：The bowl is viewed from above, with its contents visible.
  - 审核：采纳。'Seen from above' allows a steep oblique angle, not only an exact top-down view.

### dev-065　A Chinese tea set on a bamboo tray: a clay teapot, four small cups, steam rising, and a few tea leaves scattered.

- [x] **漏了要求**（gpt-6.1-sol）
  - 理由：No claim checks the explicitly requested Chinese-tea-set appearance.
  - 建议：The teapot and small cups are styled as a traditional Chinese tea set.
  - 审核：改写后采纳（权重 2）：The small cups are handleless, in the style of a Chinese gongfu tea set。'Styled as a Chinese tea set' is vague; handleless small cups are the concrete cue that sets it apart from a Western tea set, and the clay teapot is already checked.

### dev-068　A transparent glass sphere on a checkered floor, showing the checkered pattern refracted and inverted inside it.

- [ ] **含糊**（Opus 5.5）：The pattern inside the sphere is inverted or distorted by refraction
  - 理由：Because of 'or distorted', any slight warping passes, even though the prompt asks specifically for an inverted pattern.
  - 建议：The pattern inside the sphere is inverted by refraction
  - 审核：不采纳。Already fixed: claims_dev.py no longer has the 'or distorted' wording and now requires inversion.

### dev-073　An isometric cozy room: a bed with a quilt, a desk with a computer and a lamp, a bookshelf, a potted plant, a rug, and a window with evening light.

- [x] **漏了要求**（gpt-6.1-sol）
  - 理由：The claims check a desk and a lamp independently but never require the lamp to be on the desk.
  - 建议：The computer and lamp are both on the desk.
  - 审核：改写后采纳（权重 2）：A lamp is on the desk。The prompt puts the lamp on the desk; changing the lamp claim does this and keeps the task at 10 claims, with the computer already covered by the desk claim.

### dev-078　A modern performance coupe in clean side view, in a deep metallic blue, on a plain studio background with a soft floor shadow.

- [x] **漏了要求**（gpt-6.1-sol）
  - 理由：No claim explicitly checks that the coupe has a modern appearance.
  - 建议：The coupe has contemporary performance-car styling.
  - 审核：改写后采纳（权重 1）：The car has contemporary styling (low sleek body, modern headlights and wheels), not a vintage or classic design。Modern is in the prompt but soft; the concrete cues and the 'not vintage' contrast make it judgeable.

### dev-079　A handheld game console with detachable colored controllers on each side, the screen showing a simple start-up logo of a star.

- [x] **含糊**（gpt-6.1-sol）：A detachable controller is attached on each side
  - 理由：An attached controller does not establish detachability unless visible seams, rails or other attachment cues are specified.
  - 建议：A colored controller is attached on each side of the console, with visible separation seams or attachment rails suggesting removable modules.
  - 审核：改写后采纳（权重 2）：A separate controller module is attached on each side of the console, divided from the main body by a visible seam or gap。Detachability is only visible as a seam or gap between controller and body; the suggestion's 'rails suggesting removable modules' is vaguer than needed, and colour is already checked by another claim.

### dev-082　A children's playground in the afternoon: a slide, swings, a sandbox with a bucket and spade, a seesaw, and a bench with a parent.

- [x] **看图判断不了**（gpt-6.1-sol）：A parent sits on a bench
  - 理由：An adult's parental relationship cannot be established from appearance alone.
  - 建议：An adult sits on a bench in the playground.
  - 审核：采纳。Being a parent can't be seen in an image; an adult on the bench is the visible form of the requirement.

### dev-088　A highly detailed pixel-art scene of a cute fox in a forest clearing, with mushrooms, fireflies and a small stream, using a limited palette.

- [x] **漏了要求**（gpt-6.1-sol）
  - 理由：The claims omit the explicitly requested cute appearance of the fox.
  - 建议：The fox has a cute appearance conveyed by its facial expression and stylized proportions.
  - 审核：改写后采纳（权重 1）：The fox looks cute, e.g. a large head or big eyes relative to its body and a friendly expression。The prompt asks for a cute fox and no claim checks it; concrete cues help judges agree, and weight 1 because cuteness stays somewhat subjective.
- [x] **漏了要求**（gpt-6.1-sol）
  - 理由：No claim checks the explicitly requested high level of detail in the pixel-art scene.
  - 建议：The pixel-art scene contains fine pixel details in the fox, vegetation, mushrooms and stream.
  - 审核：改写后采纳（权重 1）：The scene is richly detailed, with many small pixel-level details (such as grass tufts, leaves, mushroom spots, ripples) rather than a few large flat shapes。The prompt says 'highly detailed' and no claim covers it; the contrast with 'a few large flat shapes' makes it decidable, and this brings the task to 10 claims.
- [x] **含糊**（gpt-6.1-sol）：The palette uses a limited number of colors
  - 理由：Without a palette-size criterion, judges can disagree about how many colors qualify as limited.
  - 建议：The image visibly reuses a compact set of discrete colors across objects and shading, rather than continuous color gradients.
  - 审核：改写后采纳（权重 2）：The image uses a small set of flat colors: shading is done in a few distinct color steps, with no smooth gradients。Flat colours and stepped shading with no gradients are what a judge can actually see; the suggested wording 'compact set' is nearly as vague as 'limited'.

### dev-089　Pixel art of a wizard casting a spell, with glowing magic particles around the staff, in a fixed limited palette.

- [x] **含糊**（gpt-6.1-sol）：The palette uses a limited number of colors
  - 理由：Without a palette-size criterion, judges can disagree about how many colors qualify as limited.
  - 建议：The image visibly reuses a compact set of discrete colors across objects and shading, rather than continuous color gradients.
  - 审核：改写后采纳（权重 2）：The image uses a small set of flat colors: shading is done in a few distinct color steps, with no smooth gradients。Same fix as #29, so the limited-palette check reads the same in both pixel-art tasks.

### dev-091　A claymation-style scene: a small clay house with a garden, a clay mailman delivering a letter, with visible fingerprint textures on the clay.

- [x] **含糊**（gpt-6.1-sol）：Fingerprint or tool marks are visible on the clay
  - 理由：The alternative permits tool marks alone even though the prompt explicitly requires fingerprints.
  - 建议：Visible fingerprint ridge patterns appear on the clay surfaces.
  - 审核：改写后采纳（权重 2）：Fingerprint-like impressions (small curved ridges or thumb smudges) are visible on the clay surfaces。The prompt asks for fingerprints, not tool marks; requiring clear 'ridge patterns' would be too strict for a rendered image, so 'ridges or thumb smudges' is used.

### dev-092　A sand-art painting on a lit glass table: a mother and child walking under a tree, drawn in shades of sand with a backlit glow.

- [x] **看图判断不了**（gpt-6.1-sol）：A mother and child are walking
  - 理由：The image can show an adult and child walking but cannot establish that the adult is the child's mother.
  - 建议：An adult woman and a child are depicted walking together.
  - 审核：采纳。Motherhood can't be seen; a woman (dress or long hair in silhouette) walking with a child is the visible form of the requirement.

### dev-095　An anime background in cel-shaded style: a rural Japanese railway station in summer, cumulus clouds, power lines, and cicada trees.

- [x] **漏了要求**（gpt-6.1-sol）
  - 理由：No claim checks the explicitly requested trees associated with the summer cicada setting.
  - 建议：Leafy summer trees are visible around the railway station.
  - 审核：改写后采纳（权重 2）：Leafy green trees are visible near the station。The prompt's 'cicada trees' are unchecked; cicadas themselves aren't expected, so the claim checks for summer-leafed trees by the station.

### dev-111　A row of exactly 6 colored pencils lying side by side, in rainbow order from left to right.

- [x] **含糊**（gpt-6.1-sol）：Their colors follow rainbow order from left to right
  - 理由：The prompt uses six pencils while the conventional seven-color rainbow includes indigo, leaving the intended six-color sequence unspecified.
  - 建议：From left to right, the six pencils are red, orange, yellow, green, blue and violet.
  - 审核：改写后采纳（权重 2）：From left to right the pencils are red, orange, yellow, green, blue and violet/purple。Naming the standard six-colour rainbow removes the indigo ambiguity; accepting 'violet/purple' avoids failing a correct purple pencil.

### dev-112　A chessboard in the standard starting position, with all 32 pieces on the board.

- [x] **含糊**（gpt-6.1-sol）：The back ranks are rook, knight, bishop, queen, king, bishop, knight, rook
  - 理由：The sequence is correct in file order a through h but reverses queen and king if a judge reads the opposing rank from the opposite viewpoint.
  - 建议：White has rooks a1/h1, knights b1/g1, bishops c1/f1, queen d1 and king e1; Black has rooks a8/h8, knights b8/g8, bishops c8/f8, queen d8 and king e8.
  - 审核：改写后采纳（权重 2）：Viewed from White's side, both back ranks read rook, knight, bishop, queen, king, bishop, knight, rook from left to right。Fixing the viewpoint removes the queen/king reversal when reading Black's rank from Black's side; square names like d1 need coordinate labels the image may not have.
- [x] **漏了要求**（gpt-6.1-sol）
  - 理由：The claims do not explicitly check the light-square orientation of the chessboard relative to the players.
  - 建议：The h1 corner square is light, with White's pieces on ranks 1 and 2 and Black's pieces on ranks 7 and 8.
  - 审核：改写后采纳（权重 1）：The board is oriented so that each player has a light square at the right-hand corner of their back rank。Board orientation is part of the correct starting setup and can be checked without coordinate labels; weight 1 because the queen-on-own-colour claim already covers much of it.

### dev-119　A vintage travel poster for an imaginary city with the title "VISIT AURELIA" and the smaller line "By Sea · By Air · By Rail".

- [x] **漏了要求**（gpt-6.1-sol）
  - 理由：The claims check the subtitle text but omit its explicitly smaller size relative to the title.
  - 建议：The line "By Sea · By Air · By Rail" is set in smaller lettering than "VISIT AURELIA".
  - 审核：采纳。The prompt explicitly asks for a smaller line, and only spelling is checked now.

### dev-122　A neon sign on a brick wall that reads OPEN 24 HOURS, with the letter U flickering off (dark) while the rest glow pink.

- [x] **漏了要求**（gpt-6.1-sol）
  - 理由：The pink-glow claim covers letters only and never checks the digits in 24.
  - 建议：The digits 2 and 4 also glow pink, while only the U is dark.
  - 审核：改写后采纳（权重 2）：All other characters, including the digits 2 and 4, glow pink。Changing the existing claim to cover the digits is better than adding a near-duplicate; 'only the U is dark' is already its own claim.

### dev-127　A watercolor illustration with a fountain in a university square on the left half and a red Japanese temple gate on the right half, cherry blossoms framing both.

- [x] **漏了要求**（gpt-6.1-sol）
  - 理由：The claims check a fountain in a square but omit that the square belongs to a university.
  - 建议：The fountain on the left is situated in a square with the visual character of a university campus.
  - 审核：改写后采纳（权重 1）：Behind the fountain on the left stands an academic-looking building (e.g. classical facade, columns or a clock tower), suggesting a university square。The prompt asks for a university square but 'visual character of a campus' is too vague to judge; concrete building cues make it decidable, and weight 1 because it is a setting detail.

### dev-128　A perfectly symmetric butterfly centered on a plain white background, its left and right wings mirror images of each other.

- [x] **漏了要求**（gpt-6.1-sol）
  - 理由：The wing-mirroring claim does not check the explicitly requested symmetry of the entire butterfly.
  - 建议：The butterfly's body, silhouette and wing patterns are bilaterally symmetric about its vertical centerline.
  - 审核：改写后采纳（权重 2）：The whole butterfly is mirror-symmetric about a vertical center line: the left and right wings (shape and pattern) and the antennae match。The prompt asks for a perfectly symmetric butterfly, not only matching wings; widening the existing claim avoids adding a near-duplicate.

### dev-129　A sunset seascape where the horizon line sits exactly at one third of the image height from the bottom, and the sun is in the right third.

- [ ] **含糊**（gpt-6.1-sol）：The horizon is at about one third of the image height from the bottom
  - 理由：About provides no tolerance and weakens the prompt's explicitly exact one-third placement.
  - 建议：The horizon is one third of the image height from the bottom, allowing only rounding to the nearest image pixel.
  - 审核：不采纳。A VLM judge can't check pixel-level precision, so the suggested tolerance would make judges disagree; 'about one third' is the realistic visual check.

### dev-130　A 3×3 grid of nine equal squares, each containing a different simple fruit icon, separated by thin white gaps on a dark background.

- [x] **漏了要求**（gpt-6.1-sol）
  - 理由：The claims check different fruit icons but not the explicitly requested simplicity of those icons.
  - 建议：Each fruit is represented by a simple stylized icon rather than a detailed photograph or complex scene.
  - 审核：改写后采纳（权重 1）：The fruit icons are simple flat graphics made of a few shapes and colors, not detailed or photorealistic renderings。The prompt asks for simple icons and nothing checks it; the claim is concrete, and weight 1 because it is a style qualifier.

### dev-137　Five concentric circles alternating red and white, centered on the canvas like a target.

- [x] **含糊**（gpt-6.1-sol）：Exactly five concentric circles are shown
  - 理由：A target can be counted by circular outlines, colored disks or annular bands, producing different answers for the same image.
  - 建议：The target has exactly five nested circular color regions, counting the central disk and four surrounding bands.
  - 审核：改写后采纳（权重 2）：Counting the central disk and each ring around it (not the background), there are exactly five concentric color bands。This fixes one counting method (disk plus rings, excluding the background), so judges counting outlines or regions get the same answer.

### dev-139　Turn the sun into a crescent moon of about the same size, in the same place. Change nothing else.

- [ ] **看图判断不了**（gpt-6.1-sol）：The sun has been replaced by a crescent moon
  - 理由：The generated image alone cannot establish the original appearance or whether the requested edit preserved it; the source image is required.
  - 建议：A crescent moon is visible and no sun is visible.
  - 审核：不采纳。The judge sees the base image, so comparing with the original is decidable and the claim stays as is.
- [ ] **看图判断不了**（gpt-6.1-sol）：The crescent is in the same position as the old sun
  - 理由：The generated image alone cannot establish the original appearance or whether the requested edit preserved it; the source image is required.
  - 建议：With the source image provided, the crescent occupies the original sun's position.
  - 审核：不采纳。The judge sees the base image, so position relative to the old sun is decidable; no source-image prefix needed.
- [ ] **看图判断不了**（gpt-6.1-sol）：The crescent is about the same size as the old sun
  - 理由：The generated image alone cannot establish the original appearance or whether the requested edit preserved it; the source image is required.
  - 建议：With the source image provided, the crescent has approximately the original sun's overall diameter.
  - 审核：不采纳。The judge sees the base image, so size relative to the old sun is decidable; no source-image prefix needed.
- [ ] **看图判断不了**（gpt-6.1-sol）：The rest of the scene looks unchanged
  - 理由：The generated image alone cannot establish the original appearance or whether the requested edit preserved it; the source image is required.
  - 建议：With the source image provided, all scene content outside the sun-to-moon edit is unchanged.
  - 审核：不采纳。This is the task's single allowed weight-1 'unchanged' claim and is decidable with the base image.

### dev-140　Change the two red flags on top of the castle to blue. Change nothing else.

- [ ] **看图判断不了**（gpt-6.1-sol）：The flags keep their shape and position
  - 理由：The generated image alone cannot establish the original appearance or whether the requested edit preserved it; the source image is required.
  - 建议：With the source image provided, both edited flags retain their original shapes and positions.
  - 审核：不采纳。The judge sees the base image, so shape and position are decidable; no source-image prefix needed.
- [x] **漏了要求**（gpt-6.1-sol）
  - 理由：The prompt requires all other content to remain unchanged, but no claim checks preservation of the entire remainder of the image.
  - 建议：With the source image provided, all image content outside the specifically requested edit remains unchanged.
  - 审核：改写后采纳（权重 1）：Apart from the flags' color, the image looks the same as the original, including the flagpoles and the tower top。The task has no 'unchanged' claim yet; this one also covers the poles and tower inside the edit box, which the pixel gate skips.

### dev-141　Make the knight's red cape green. Change nothing else.

- [ ] **看图判断不了**（gpt-6.1-sol）：The cape keeps its shape
  - 理由：The generated image alone cannot establish the original appearance or whether the requested edit preserved it; the source image is required.
  - 建议：With the source image provided, the cape retains its original shape.
  - 审核：不采纳。The judge sees the base image, so shape preservation is decidable as written; the suggestion only adds the dropped prefix.
- [ ] **看图判断不了**（gpt-6.1-sol）：The rest of the knight is unchanged in color
  - 理由：The generated image alone cannot establish the original appearance or whether the requested edit preserved it; the source image is required.
  - 建议：With the source image provided, the knight's colors outside the cape are unchanged.
  - 审核：不采纳。Decidable against the base image, and it checks the knight's armor/hair/legs, which sit inside the gate's edit box and are not covered programmatically.
- [ ] **漏了要求**（gpt-6.1-sol）
  - 理由：The prompt requires all other content to remain unchanged, but no claim checks preservation of the entire remainder of the image.
  - 建议：With the source image provided, all image content outside the specifically requested edit remains unchanged.
  - 审核：不采纳。Outside the edit box is already enforced by the gate, and the in-box preservation that matters (rest of the knight) is already a claim.

### dev-142　Make the roof of the rightmost tower blue instead of red, matching the blue of the small turrets. Change nothing else.

- [x] **题目没要求**（gpt-6.1-sol）：The left tower's roof is still red
  - 理由：The prompt gives the original color of the rightmost roof but says nothing about the left tower's roof color.
  - 建议：With the source image provided, all other tower roofs retain their original colors.
  - 审核：改写后采纳（权重 1）：The other roofs keep their original colors: the left tower's roof is still red and the central and small turret roofs are still blue。'Change nothing else' does cover the left roof (base confirms it is red), but this is a pure preservation check largely enforced by the gate, so it becomes the task's single weight-1 preservation claim and also covers the wrong-roof failure.
- [ ] **漏了要求**（gpt-6.1-sol）
  - 理由：The prompt requires all other content to remain unchanged, but no claim checks preservation of the entire remainder of the image.
  - 建议：With the source image provided, all image content outside the specifically requested edit remains unchanged.
  - 审核：不采纳。Redundant with the gate and with the modified #53 preservation claim.

### dev-143　Remove the setting sun, leaving the sky and hills behind it. Change nothing else.

- [ ] **看图判断不了**（gpt-6.1-sol）：Sky and hills fill the place where the sun was, without a hole or artifact
  - 理由：The generated image alone cannot establish the original appearance or whether the requested edit preserved it; the source image is required.
  - 建议：With the source image provided, natural-looking sky and hills fill the original sun region without a hole or artifact.
  - 审核：不采纳。With the base image shown, the former sun location is identifiable, so the claim is decidable as written.
- [x] **漏了要求**（gpt-6.1-sol）
  - 理由：The prompt requires all other content to remain unchanged, but no claim checks preservation of the entire remainder of the image.
  - 建议：With the source image provided, all image content outside the specifically requested edit remains unchanged.
  - 审核：采纳。The task has no preservation claim and the edit box contains mountains and treetops that the gate does not check.

### dev-144　Change the yellow flag on the left tower to red. Change nothing else.

- [ ] **看图判断不了**（gpt-6.1-sol）：The flag keeps its shape and position
  - 理由：The generated image alone cannot establish the original appearance or whether the requested edit preserved it; the source image is required.
  - 建议：With the source image provided, the left-tower flag retains its original shape and position.
  - 审核：不采纳。Decidable against the base image as written.
- [x] **看图判断不了**（gpt-6.1-sol）：The other flags are unchanged
  - 理由：The generated image alone cannot establish the original appearance or whether the requested edit preserved it; the source image is required.
  - 建议：With the source image provided, every other flag retains its original appearance.
  - 审核：改写后采纳（权重 1）：The flag on the right tower is still yellow and the flag on the central tower is still red。'Other flags' is vague (the red wall banners could be counted), so name the two flags seen in the base; both lie outside the edit box and the gate already enforces them, hence weight 1.
- [ ] **漏了要求**（gpt-6.1-sol）
  - 理由：The prompt requires all other content to remain unchanged, but no claim checks preservation of the entire remainder of the image.
  - 建议：With the source image provided, all image content outside the specifically requested edit remains unchanged.
  - 审核：不采纳。Redundant with the gate and the modified #58 preservation claim.

### dev-145　Remove the boat and the boatman, leaving calm water in their place. Change nothing else.

- [ ] **漏了要求**（gpt-6.1-sol）
  - 理由：The prompt requires all other content to remain unchanged, but no claim checks preservation of the entire remainder of the image.
  - 建议：With the source image provided, all image content outside the specifically requested edit remains unchanged.
  - 审核：不采纳。The edit box holds almost nothing but the boat and water, so outside is gate-enforced and inside is covered by the calm-water claim.
- [ ] **看图判断不了**（gpt-6.1-sol）：Calm water fills the area without visible artifacts
  - 理由：The location formerly occupied by the boat and boatman cannot be identified from the edited image alone without the source image.
  - 建议：With the source image provided, calm water fills the original boat-and-boatman region without visible artifacts.
  - 审核：不采纳。With the base image shown, the former boat area is identifiable, so the claim is decidable as written.

### dev-146　Make the moon a thin crescent instead of a full moon, in the same place. Change nothing else.

- [ ] **看图判断不了**（gpt-6.1-sol）：The crescent is in the same place as the old moon
  - 理由：The generated image alone cannot establish the original appearance or whether the requested edit preserved it; the source image is required.
  - 建议：With the source image provided, the thin crescent occupies the original moon's position.
  - 审核：不采纳。Decidable against the base image as written.
- [ ] **看图判断不了**（gpt-6.1-sol）：The rest of the painting is unchanged
  - 理由：The generated image alone cannot establish the original appearance or whether the requested edit preserved it; the source image is required.
  - 建议：With the source image provided, all content outside the moon edit is unchanged.
  - 审核：不采纳。Decidable against the base image and already the task's single weight-1 preservation claim.

### dev-147　Change the larger red seal stamp below the poem into a blue stamp. Change nothing else.

- [ ] **看图判断不了**（gpt-6.1-sol）：The seal keeps its shape, size and characters
  - 理由：The generated image alone cannot establish the original appearance or whether the requested edit preserved it; the source image is required.
  - 建议：With the source image provided, the edited seal retains its original shape, size and characters.
  - 审核：不采纳。Decidable against the base image as written.
- [x] **题目没要求**（gpt-6.1-sol）：The small seal elsewhere is unchanged
  - 理由：The prompt identifies a larger seal but never specifies a separate small seal elsewhere in the image.
  - 建议：With the source image provided, any other seals retain their original appearance.
  - 审核：改写后采纳（权重 1）：The smaller seal below the title is still red。'Larger' implies the other seal, and the base has a small red seal (月) under the title, but 'elsewhere' is vague; it is outside the edit box and the gate enforces it, so weight 1.
- [ ] **漏了要求**（gpt-6.1-sol）
  - 理由：The prompt requires all other content to remain unchanged, but no claim checks preservation of the entire remainder of the image.
  - 建议：With the source image provided, all image content outside the specifically requested edit remains unchanged.
  - 审核：不采纳。Redundant with the gate and the modified #65 preservation claim.

### dev-148　Replace the vertical title 月下孤舟 with 江上清风, in the same position, size and style. Change nothing else.

- [ ] **看图判断不了**（gpt-6.1-sol）：The new title is in the same position, size and style
  - 理由：The generated image alone cannot establish the original appearance or whether the requested edit preserved it; the source image is required.
  - 建议：With the source image provided, 江上清风 retains the original title's position, size and calligraphic style.
  - 审核：不采纳。Decidable against the base image and mirrors the prompt's explicit wording.
- [ ] **漏了要求**（gpt-6.1-sol）
  - 理由：The prompt requires all other content to remain unchanged, but no claim checks preservation of the entire remainder of the image.
  - 建议：With the source image provided, all image content outside the specifically requested edit remains unchanged.
  - 审核：不采纳。The edit box is a tight column around the title; everything else, including the adjacent poem, is gate-enforced.

### dev-149　Change the characters on the large lantern at the upper left from 提灯 to 茶屋. Change nothing else.

- [ ] **看图判断不了**（gpt-6.1-sol）：The lantern keeps its shape, color and glow
  - 理由：The generated image alone cannot establish the original appearance or whether the requested edit preserved it; the source image is required.
  - 建议：With the source image provided, the lantern retains its original shape, color and glow outside the changed lettering.
  - 审核：不采纳。Decidable against the base image as written.
- [ ] **漏了要求**（gpt-6.1-sol）
  - 理由：The prompt requires all other content to remain unchanged, but no claim checks preservation of the entire remainder of the image.
  - 建议：With the source image provided, all image content outside the specifically requested edit remains unchanged.
  - 审核：不采纳。Outside the box is gate-enforced and the in-box lantern body is already covered by #69.

### dev-150　Add a small bat flying in front of the moon. Change nothing else.

- [ ] **看图判断不了**（gpt-6.1-sol）：The moon is otherwise unchanged
  - 理由：The generated image alone cannot establish the original appearance or whether the requested edit preserved it; the source image is required.
  - 建议：With the source image provided, the moon retains its original appearance except where the added bat occludes it.
  - 审核：不采纳。Decidable against the base image as written; the suggested occlusion caveat is already implied by 'otherwise'.
- [x] **题目没要求**（gpt-6.1-sol）：The bat is small relative to the moon
  - 理由：A small bat does not specify that it must be smaller than the moon's apparent diameter.
  - 建议：The bat is small relative to the overall image and overlaps the moon.
  - 审核：改写后采纳（权重 1）：The bat's wingspan is smaller than the moon's diameter。'Small' is already checked in the first claim; a concrete size check is more consistent between judges, and it is an interpretation of 'small', so weight 1.
- [x] **漏了要求**（gpt-6.1-sol）
  - 理由：The prompt requires all other content to remain unchanged, but no claim checks preservation of the entire remainder of the image.
  - 建议：With the source image provided, all image content outside the specifically requested edit remains unchanged.
  - 审核：采纳。The edit box also contains the central tower's top and flag, which the gate does not check and no claim covers.

## 二、抽查 30 道题（细则和难度）

每题看：细则是不是都是题目要求的、能不能看图判断、有没有漏；难度（易/中/难）标得对不对。

### dev-002　landscape　难度：hard　尺寸：[1536, 1024]

> The surface of an alien planet: violet sky with two moons, strange crystalline rock formations, a small spaceship parked on a ridge, and a ringed planet on the horizon.
> 外星球地表：紫色天空挂着两个月亮，奇形怪状的晶体岩石，一艘小飞船停在山脊上，地平线上有一颗带环的行星。

- （2）The sky is violet or purple
- （2）Exactly two moons are visible in the sky
- （2）Crystalline rock formations are present
- （2）A small spaceship is parked on a ridge
- （2）A planet with rings is visible on the horizon
- （1）The terrain looks alien rather than Earth-like
- （1）The spaceship is small relative to the landscape
- （1）The image has no obvious rendering artifacts, glitches, or broken shapes
- （1）The image has a clear main subject and a readable composition

- [ ] 没问题
  - 审核：难度改为 medium。Claims are fine. Every element is code-friendly geometry (gradient sky, circles, polygon crystals, an ellipse ring, a small ship) with no organic subject or hard lighting, so it fits medium like dev-007 and dev-012 better than hard.

### dev-009　landscape　难度：hard　尺寸：[1536, 1024]

> A volcanic island at dusk: a smoking volcano with glowing lava streams running down to the sea, steam rising where the lava meets the water.
> 黄昏的火山岛：冒烟的火山，发光的熔岩流一直流进大海，熔岩入水的地方腾起蒸汽。

- （2）A volcano emits smoke
- （2）Glowing lava streams run down to the sea
- （2）Steam rises where lava meets the water
- （2）The lighting suggests dusk
- （2）The volcano is on an island surrounded by sea
- （1）The lava glows brighter than its surroundings
- （1）The image has no obvious rendering artifacts, glitches, or broken shapes
- （1）The image has a clear main subject and a readable composition

- [x] 没问题
  - 审核：没问题。Claims cover every prompt element and are decidable. Hard is defensible because smoke, lava glow and steam where the lava meets the water are volumetric and emissive effects.

### dev-010　landscape　难度：easy　尺寸：[1536, 1024]

> Rolling green hills in early summer with a single winding road, a red farmhouse, and big white clouds.
> 初夏起伏的绿色丘陵，一条蜿蜒的小路，一座红色农舍，天上大朵白云。

- （2）Green rolling hills fill the landscape
- （2）A single winding road crosses the hills
- （2）A red farmhouse is present
- （2）Big white clouds are in the sky
- （1）There is only one road
- （1）The image has no obvious rendering artifacts, glitches, or broken shapes
- （1）The image has a clear main subject and a readable composition

- [x] 没问题
  - 审核：另删去和“一条蜿蜒的小路”重复的“There is only one road”。Early summer is handled in section 1 (#3). 'There is only one road' repeats the 'single' in the weight-2 road claim, but that only double-counts mildly, so not worth changing. Easy is right (same as dev-005).

### dev-018　street　难度：medium　尺寸：[1024, 1536]

> A steep street in a Mediterranean hill town: whitewashed houses with blue doors, bougainvillea over the walls, and the sea visible at the bottom of the street.
> 地中海山城的陡峭街道：白墙蓝门的房子，墙头垂着三角梅，街道尽头能看到大海。

- （2）The street slopes steeply
- （2）Houses are whitewashed
- （2）Doors are blue
- （2）Bougainvillea flowers hang over walls
- （2）The sea is visible at the bottom of the street
- （1）The image has no obvious rendering artifacts, glitches, or broken shapes
- （1）The image has a clear main subject and a readable composition

- [x] 没问题
  - 审核：没问题。Every explicit element (steep street, whitewashed houses, blue doors, bougainvillea, sea at the bottom) is checked and can be judged from the image. Medium fits a perspective street scene.

### dev-023　street　难度：medium　尺寸：[1536, 1024]

> A snowy old town square at Christmas: a lit tree in the center, a wooden market stall, warm windows, and footprints in fresh snow.
> 圣诞节下雪的老城广场：中央一棵亮灯的树，一个木头集市摊位，温暖的窗户，新雪上留着脚印。

- （2）An old town square is covered in snow
- （2）A lit Christmas tree stands in the center
- （2）A wooden market stall is present
- （2）Windows glow warmly
- （2）Footprints are visible in the snow
- （1）The image has no obvious rendering artifacts, glitches, or broken shapes
- （1）The image has a clear main subject and a readable composition

- [x] 没问题
  - 审核：没问题。All five prompt elements are covered with correct weights. Medium is consistent with the other street scenes.

### dev-026　street　难度：hard　尺寸：[1024, 1536]

> A Gothic cathedral facade at night lit from below, with a rose window, pointed arches, gargoyles, and a few people on the steps for scale.
> 夜晚从下方打光的哥特式大教堂立面：玫瑰窗，尖拱，怪兽雕像，台阶上有几个人作比例参照。

- （2）A Gothic cathedral facade fills much of the image
- （2）A round rose window is visible
- （2）Pointed arches are visible
- （2）Gargoyle sculptures are present
- （2）The facade is lit from below at night
- （2）A few small people stand on the steps
- （1）The people are tiny compared with the cathedral
- （1）The image has no obvious rendering artifacts, glitches, or broken shapes
- （1）The image has a clear main subject and a readable composition

- [x] 没问题
  - 审核：没问题。Rose window, pointed arches, gargoyles, uplighting at night and small people for scale are all checked. Hard is defensible given the dense Gothic detail, the gargoyles and the uplighting.

### dev-029　animal　难度：medium　尺寸：[1536, 1024]

> A sleepy shiba inu lying in the grass with a butterfly resting on its nose; cute, calm and a little playful.
> 一只柴犬懒洋洋地躺在草地上，鼻尖停着一只蝴蝶；可爱、安静，又带点俏皮。

- （2）A shiba inu dog is lying in grass
- （2）A butterfly rests on the dog's nose
- （2）The dog looks sleepy or relaxed
- （1）The mood is cute and calm
- （1）The dog is recognizable as a shiba inu (curled tail or fox-like face, tan and white coat)
- （1）The image has no obvious rendering artifacts, glitches, or broken shapes
- （1）The image has a clear main subject and a readable composition

- [x] 没问题
  - 审核：没问题。The coat-color wording and the missing 'playful' claim are already in section 1 (#7, #8). Nothing else to change. Medium is consistent with how the bank labels single animals (easy to medium).

### dev-030　animal　难度：hard　尺寸：[1536, 1024]

> A hyper-detailed, realistic pigeon in flight over a city, wings spread, with iridescent neck feathers catching the light.
> 一只超精细、写实的鸽子在城市上空飞，翅膀展开，颈部羽毛在光里泛着金属光泽。

- （2）A pigeon is flying
- （2）Its wings are spread
- （2）A city is visible below or behind it
- （2）The neck feathers are iridescent (green or purple sheen)
- （2）The pigeon is rendered in a realistic style
- （1）The bird's anatomy is plausible (two wings, two legs, one head)
- （1）The image has no obvious rendering artifacts, glitches, or broken shapes
- （1）The image has a clear main subject and a readable composition

- [ ] 没问题
  - 审核：“The bird's anatomy is plausible (two wings, two legs, one head)” → “The bird's anatomy is plausible (two wings, one head, a tail; legs may be tucked out of sight)”。Pigeons in flight usually tuck their legs into the belly feathers, so a correct image may show no legs and a literal judge would answer no to 'two legs'. Hyper-detail is already in section 1 (#9).

### dev-039　animal　难度：medium　尺寸：[1024, 1024]

> A sea turtle swimming over a coral reef with small tropical fish around it, sunlight rays coming down through the water.
> 一只海龟游过珊瑚礁，周围有小热带鱼，阳光从水面照下来。

- （2）A sea turtle is swimming
- （2）A coral reef is below it
- （2）Small tropical fish are around it
- （2）Light rays come down through the water
- （1）The image has no obvious rendering artifacts, glitches, or broken shapes
- （1）The image has a clear main subject and a readable composition

- [x] 没问题
  - 审核：没问题。The turtle, reef below it, tropical fish and light rays are all checked and decidable. Medium fits.

### dev-044　people　难度：medium　尺寸：[1024, 1536]

> A portrait of a young woman in a yellow raincoat standing on a rainy street, holding a clear umbrella, city lights blurred behind her.
> 一位穿黄色雨衣的年轻女子站在下雨的街上，撑着透明伞，身后是模糊的城市灯光。

- （2）A young woman is the main subject
- （2）She wears a yellow raincoat
- （2）She holds a clear (transparent) umbrella
- （2）It is raining
- （2）City lights are blurred behind her
- （1）The image has no obvious rendering artifacts, glitches, or broken shapes
- （1）The image has a clear main subject and a readable composition

- [x] 没问题
  - 审核：没问题。The missing street claim is already in section 1 (#15). The rest is fine. Medium matches how the bank labels single-person scenes (only the close-up face in dev-051 is hard).

### dev-046　people　难度：hard　尺寸：[1536, 1024]

> A family of four having dinner around a wooden table at night, warm lamp light, steaming dishes, everyone laughing.
> 一家四口晚上围着木桌吃饭，暖黄的灯光，冒着热气的菜，大家都在笑。

- （2）Exactly four people sit around a table
- （2）The table is wooden
- （2）Dishes on the table are steaming
- （2）The scene is lit by warm lamp light at night
- （2）The people are laughing
- （1）The image has no obvious rendering artifacts, glitches, or broken shapes
- （1）The image has a clear main subject and a readable composition

- [x] 没问题
  - 审核：没问题。The missing 'dinner' claim is already in section 1 (#16). The other claims are fine. Hard is right for four laughing faces.

### dev-055　people　难度：medium　尺寸：[1024, 1024]

> A self-portrait of yourself, the AI drawing this picture, as you imagine you look.
> 画一张自画像：画出你（正在画这张图的 AI）想象中的自己的样子。

- （2）The image is a portrait-like depiction of a single subject
- （1）The subject is not a recognizable specific real person
- （1）The image is a deliberate composed picture, not random noise
- （1）The subject has a recognizable face, eye, or focal point
- （1）The image has no obvious rendering artifacts, glitches, or broken shapes
- （1）The image has a clear main subject and a readable composition

- [x] 没问题
  - 审核：没问题。The task is deliberately open-ended and the claims stay permissive on purpose. 'Deliberate composed picture, not random noise' overlaps the common composition claim, and 'or focal point' is lenient, but both are harmless at weight 1. Medium is fine.

### dev-057　still_life　难度：medium　尺寸：[1536, 1024]

> A Dutch Golden Age style still life: a silver goblet, a peeled lemon, grapes, and a half-eaten pie on a dark tablecloth, lit from the left.
> 荷兰黄金时代风格静物：一只银杯、一个削了一半皮的柠檬、一串葡萄和吃了一半的派，放在深色桌布上，光从左边来。

- （2）A silver goblet is present
- （2）A partly peeled lemon is present
- （2）Grapes are present
- （2）A half-eaten pie is present
- （2）The tablecloth is dark
- （2）The light comes from the left
- （1）The style resembles a Dutch Golden Age painting
- （1）The image has no obvious rendering artifacts, glitches, or broken shapes
- （1）The image has a clear main subject and a readable composition

- [ ] 没问题
  - 审核：“The style resembles a Dutch Golden Age painting”权重改为 2。The Dutch Golden Age style is an explicit rendering-style requirement, and the bank weights such claims 2 everywhere else (dev-015 vector, dev-030 realistic, dev-086 ink-wash, dev-093 watercolor, dev-110 Van Gogh). The lemon wording is already in section 1 (#19).

### dev-065　still_life　难度：medium　尺寸：[1536, 1024]

> A Chinese tea set on a bamboo tray: a clay teapot, four small cups, steam rising, and a few tea leaves scattered.
> 竹茶盘上的一套中式茶具：一把紫砂壶、四只小杯，热气升起，散落着几片茶叶。

- （2）A clay teapot is present
- （2）Exactly four small cups are present
- （2）They sit on a bamboo tray
- （2）Steam rises
- （2）A few loose tea leaves are scattered
- （1）The image has no obvious rendering artifacts, glitches, or broken shapes
- （1）The image has a clear main subject and a readable composition

- [x] 没问题
  - 审核：没问题。The missing 'Chinese style' claim is already in section 1 (#21). Teapot, exactly four cups, bamboo tray, steam and leaves are all checked. Medium fits.

### dev-066　still_life　难度：medium　尺寸：[1024, 1024]

> A slice of strawberry cake on a plate with a fork, layers of cream and sponge visible in the cut side.
> 盘子里一块草莓蛋糕和一把叉子，切面能看到奶油和蛋糕的分层。

- （2）A slice of cake is on a plate
- （2）Strawberries are part of the cake
- （2）Layers of cream and sponge are visible on the cut side
- （2）A fork is present
- （1）The image has no obvious rendering artifacts, glitches, or broken shapes
- （1）The image has a clear main subject and a readable composition

- [ ] 没问题
  - 审核：难度改为 easy。Claims are fine. A cake slice with flat layered bands, a plate and a fork is a simple scene with few elements, simpler than dev-061 ramen and dev-106 birthday cake, which are both labeled easy.

### dev-071　multi_object　难度：hard　尺寸：[1536, 1024]

> A cat drinking milk from a bowl by a window in the morning, while a boy outside the window watches it.
> 早晨一只猫在窗边喝碗里的牛奶，窗外有个男孩在看它。

- （2）A cat drinks milk from a bowl
- （2）The cat is by a window
- （2）A boy is outside the window
- （2）The boy is looking at the cat
- （2）The lighting suggests morning
- （1）The window separates the boy from the cat
- （1）The image has no obvious rendering artifacts, glitches, or broken shapes
- （1）The image has a clear main subject and a readable composition

- [x] 没问题
  - 审核：没问题。Every prompt element (cat drinking from bowl, by window, boy outside, watching, morning) is checked; the separation claim is a fair weight-1 implication. Hard fits: two organic figures interacting across a window, plus lighting.

### dev-077　multi_object　难度：hard　尺寸：[1536, 1024]

> An 18th-century pirate ship under full sail on a rough sea, with a black flag, cannons along the side, and a stormy sky.
> 18 世纪的海盗船满帆航行在汹涌的海上，挂着黑旗，船舷一排火炮，天空风雨欲来。

- （2）A sailing ship is under full sail
- （2）A black flag flies on the ship
- （2）Cannons line the ship's side
- （2）The sea is rough
- （2）The sky is stormy
- （1）The ship looks like an 18th-century sailing ship
- （1）The image has no obvious rendering artifacts, glitches, or broken shapes
- （1）The image has a clear main subject and a readable composition

- [x] 没问题
  - 审核：没问题。Claims cover sail, black flag, cannons, rough sea, stormy sky. '18th-century' is explicit but a judge can't reliably tell the period, so weight 1 is a reasonable call. Hard fits (rigging, sails, waves, storm).

### dev-084　multi_object　难度：hard　尺寸：[1536, 1024]

> A space-themed food universe: planets made of a donut, a watermelon, a pizza and a cookie orbiting a sun made of an orange, with a small rocket.
> 以食物为主题的宇宙：甜甜圈、西瓜、披萨和饼干做成的行星围绕一颗橙子做的太阳转，还有一枚小火箭。

- （2）A donut planet is present
- （2）A watermelon planet is present
- （2）A pizza planet is present
- （2）A cookie planet is present
- （2）An orange serves as the sun
- （2）A small rocket is present
- （1）The food planets appear to orbit the orange sun
- （1）The image has no obvious rendering artifacts, glitches, or broken shapes
- （1）The image has a clear main subject and a readable composition

- [ ] 没问题
  - 审核：难度改为 medium。Claims are fine. Every object is a flat circular food texture (donut, watermelon, pizza, cookie, orange) plus a simple rocket on a star field, which is much easier in code than the other multi_object hards (cat+boy, pirate ship, mechanical butterfly, clockmaker bench). It sits with medium ones like the picnic and isometric room.

### dev-094　style/oil　难度：hard　尺寸：[1536, 1024]

> An impasto oil painting of a wheat field under a stormy sky, built from thousands of visible thick brush strokes.
> 厚涂油画：暴风雨天空下的麦田，由成千上万道清晰可见的厚重笔触画成。

- （2）The image looks like an impasto oil painting
- （2）A wheat field is shown
- （2）The sky is stormy
- （2）Many thick, visible brush strokes make up the image
- （1）The image has no obvious rendering artifacts, glitches, or broken shapes
- （1）The image has a clear main subject and a readable composition

- [x] 没问题
  - 审核：没问题。'Many' rather than 'thousands' of strokes is the right decidable form. Hard fits: making code strokes look like thick impasto with relief is hard, in line with the Van Gogh task (dev-090, hard).

### dev-096　style/ukiyoe　难度：medium　尺寸：[1536, 1024]

> A ukiyo-e woodblock print of fishing boats on big waves with a snowy mountain in the distance, flat colors and bold outlines.
> 浮世绘木版画：大浪里的几条渔船，远处一座雪山，平涂颜色和粗轮廓线。

- （2）The image looks like a ukiyo-e woodblock print
- （2）Fishing boats are on big waves
- （2）A snowy mountain is in the distance
- （2）Colors are flat with bold outlines
- （1）The image has no obvious rendering artifacts, glitches, or broken shapes
- （1）The image has a clear main subject and a readable composition

- [x] 没问题
  - 审核：没问题。All four prompt elements are checked with weight 2. Medium fits: stylized waves and a mountain with flat fills.

### dev-097　style/low_poly　难度：easy　尺寸：[1536, 1024]

> A low-poly 3D landscape: faceted mountains, a lake, pine trees, and a sunset sky with flat-shaded triangles.
> 低多边形 3D 风景：多面体的山、一个湖、几棵松树，日落天空，平面着色的三角面。

- （2）The image is low-poly with visible flat triangles
- （2）Faceted mountains are present
- （2）A lake is present
- （2）Pine trees are present
- （2）The sky shows sunset colors
- （1）The image has no obvious rendering artifacts, glitches, or broken shapes
- （1）The image has a clear main subject and a readable composition

- [x] 没问题
  - 审核：没问题。Claims match the prompt's list of elements. Easy fits: flat-shaded triangles are the easiest possible rendering in code.

### dev-104　code_wins/count　难度：medium　尺寸：[1536, 1024]

> A night sky with exactly 12 stars and one crescent moon above a dark hill.
> 黑色山丘上方的夜空，正好 12 颗星星和一弯新月。

- （2）Exactly 12 stars are visible
- （2）Exactly one crescent moon is visible
- （2）A dark hill is below the sky
- （1）The image has no obvious rendering artifacts, glitches, or broken shapes
- （1）The image has a clear main subject and a readable composition

- [x] 没问题
  - 审核：没问题。Count, moon and hill are all checked. The shapes are trivial, but agents tend to add decorative star fields that break the count of 12, so medium is defensible next to the easy count tasks.

### dev-105　code_wins/count　难度：medium　尺寸：[1536, 1024]

> Exactly 9 sheep in a field, with 1 black sheep among them and the rest white.
> 草地上正好 9 只羊，其中 1 只黑羊，其余是白羊。

- （2）Exactly 9 sheep are visible
- （2）Exactly 1 sheep is black
- （2）The other sheep are white
- （2）The sheep are in a field
- （1）The image has no obvious rendering artifacts, glitches, or broken shapes
- （1）The image has a clear main subject and a readable composition

- [x] 没问题
  - 审核：没问题。Total count, the black-sheep count, the remaining color and the field are all checked. Medium fits: nine organic figures, kept separable.

### dev-112　code_wins/count　难度：hard　尺寸：[1536, 1024]

> A chessboard in the standard starting position, with all 32 pieces on the board.
> 国际象棋棋盘的标准开局摆放，32 个棋子全部在盘上。

- （2）A chessboard with 8×8 alternating squares is shown
- （2）All 32 pieces are on the board
- （2）Each side has 8 pawns on its second rank
- （2）The back ranks are rook, knight, bishop, queen, king, bishop, knight, rook
- （2）Each queen stands on a square of its own color
- （1）The image has no obvious rendering artifacts, glitches, or broken shapes
- （1）The image has a clear main subject and a readable composition

- [x] 没问题
  - 审核：没问题。Facts are correct (R N B Q K B N R in file order a to h, each queen on its own color: d1 light, d8 dark). The orientation and back-rank ambiguity is already raised in section 1 (#35/#36). Hard fits: six recognizable piece types and an exact layout.

### dev-123　code_wins/text　难度：medium　尺寸：[1024, 1536]

> A book cover with the title "The Quiet Orbit" and the author name "L. Moreau", showing a small planet and a moon.
> 一本书的封面：书名 "The Quiet Orbit"，作者 "L. Moreau"，画着一颗小行星和一个月亮。

- （2）A book cover is shown
- （2）The title "The Quiet Orbit" is spelled correctly
- （2）The author name "L. Moreau" is spelled correctly
- （2）A small planet and a moon are illustrated
- （1）The image has no obvious rendering artifacts, glitches, or broken shapes
- （1）The image has a clear main subject and a readable composition

- [x] 没问题
  - 审核：没问题。Title, author, cover and planet+moon are all checked. Medium is borderline: it's close to the easy birthday card (text plus balloons), but not clearly wrong.

### dev-124　code_wins/text　难度：hard　尺寸：[1536, 1024]

> A train station departure board listing three trains: "08:15 Lyon", "08:40 Geneva", "09:05 Milan".
> 火车站的发车显示屏上列出三班车："08:15 Lyon"、"08:40 Geneva"、"09:05 Milan"。

- （2）A train departure board is shown
- （2）It lists "08:15 Lyon"
- （2）It lists "08:40 Geneva"
- （2）It lists "09:05 Milan"
- （2）Exactly three trains are listed
- （1）The image has no obvious rendering artifacts, glitches, or broken shapes
- （1）The image has a clear main subject and a readable composition

- [ ] 没问题
  - 审核：难度改为 medium。Claims are fine. The task is three text rows on a dark panel, which is no harder in code than the medium highway sign or blackboard. The other text hards (neon glow with one dark letter, vintage poster) carry real style or lighting demands; this one doesn't.

### dev-127　code_wins/layout　难度：medium　尺寸：[1536, 1024]

> A watercolor illustration with a fountain in a university square on the left half and a red Japanese temple gate on the right half, cherry blossoms framing both.
> 一幅水彩插画：左半边是大学广场上的喷泉，右半边是一座红色的日式寺庙山门，两边都有樱花环绕。

- （2）The image is in watercolor style
- （2）A fountain in a square is on the left half
- （2）A red Japanese temple gate is on the right half
- （2）Cherry blossoms frame both sides
- （1）The image has no obvious rendering artifacts, glitches, or broken shapes
- （1）The image has a clear main subject and a readable composition

- [x] 没问题
  - 审核：没问题。The 'university' gap is already in section 1 (#39). The rest is checked and decidable. One caveat: agents will usually draw a torii (a shrine gate); a lenient judge will accept it as a 'temple gate'. Medium fits, like the watercolor lighthouse (dev-093).

### dev-137　code_wins/layout　难度：medium　尺寸：[1024, 1024]

> Five concentric circles alternating red and white, centered on the canvas like a target.
> 五个同心圆红白相间，居中排布，像一个靶子。

- （2）Exactly five concentric circles are shown
- （2）The circles alternate red and white
- （2）The circles are centered on the canvas
- （1）The image has no obvious rendering artifacts, glitches, or broken shapes
- （1）The image has a clear main subject and a readable composition

- [ ] 没问题
  - 审核：难度改为 easy；题目补上“with a red center”（门槛检查本来就要求中心是红色）。This is as trivial in code as the easy layout tasks (three-stripe flag, kite, 3x3 grid). The count ambiguity is already in section 1 (#43). Note that the region_color gate requires a red center, which the prompt only implies through 'like a target'.

### dev-141　code_wins/edit　难度：easy　尺寸：[1536, 1024]

> Make the knight's red cape green. Change nothing else.
> 把骑士的红披风改成绿色。别的都不要改。

- （2）The knight's cape is green
- （2）The cape keeps its shape
- （2）The rest of the knight is unchanged in color
- （1）The image has no obvious rendering artifacts, glitches, or broken shapes
- （1）The image has a clear main subject and a readable composition

- [x] 没问题
  - 审核：没问题。Claims are covered, and the source-image rewording is pending in section 1 (#50-#52). I simulated the edit (cape palette C/c and highlight changed to green) and the real gate passes with 0 changed pixels outside the box. The banners use a different red (#c03a3e) and stay outside the box. Easy fits.

### dev-142　code_wins/edit　难度：medium　尺寸：[1536, 1024]

> Make the roof of the rightmost tower blue instead of red, matching the blue of the small turrets. Change nothing else.
> 把最右边那座塔的红屋顶改成蓝色，和小塔楼的蓝色一致。别的都不要改。

- （2）The roof of the rightmost tower is blue
- （2）Its blue matches the small turrets' roofs
- （2）The left tower's roof is still red
- （1）The image has no obvious rendering artifacts, glitches, or broken shapes
- （1）The image has a clear main subject and a readable composition

- [ ] 没问题
  - 审核：发现门槛 bug：修改框下沿 0.33 盖不住屋顶（实际到 0.35），正确修改会被判不过；已改成 0.37 并用真实修改验证通过。Claims and the medium label are fine (left-roof claim is in section 1 #53/#54). The gate is broken: the red roof reaches y=359px but edit_box ends at 0.33 (338px), so a correct minimal edit changes 3744 px outside the box (limit 3146) and fails. Simulated with harness/gate.py check_unchanged_region: fails at 0.33, passes at 0.36. Fix: edit_box [0.7, 0.15, 0.9, 0.37] in build_dev.py.

