# 连帧生成规范

先读取当前环境的imagegen技能，遵循其工具调用、参考图片查看、保存与透明输出规则。每次生成后查看结果，不只信任提示词。

## 可填写的提示词

```text
Use case: stylized-concept / identity-preserve (choose to match task).
Asset: one 4×4 sprite sheet containing exactly16 consecutive frames of ONE loop.
References: image1 locks character identity; image2 (if supplied) locks product appearance.
Subject invariants: [face, proportions, colors, clothing, materials, accessories].
Action: [one clear action relevant to scene].
Frame progression: [describe 1–16 small incremental poses with eased timing and return].
Composition: equal square cells, row-major order, fixed camera, fixed character scale,
consistent body center and feet baseline. Entire subject and props fit inside each cell
with at least8% clear padding on every side. No crossing between cells.
Loop: frame16 is immediately before frame1 in the same motion cycle; avoid a sudden reset.
Product: [exact package colors, layout, visible text, orientation and hand contact].
Style: match reference, consistent lighting/materials across all frames.
Background: true alpha transparency, no floor, no cast floor shadow, no backdrop,
no baked checkerboard. Preserve opaque white parts of subject and props.
Clean silhouette and transparent margins; no white matte, fringe, stray edge pixels
or background speckles. Keep intentional translucent details intact.
Text: omit main caption entirely; it will be added from one fixed text layer later.
No grid strokes, frame labels, watermarks, extra limbs, camera motion or abrupt pose changes.
```

不要求所有表情都举杯：加油可小幅握拳抬臂，喝水/喝茶可举杯，拥抱可收臂再展开，问候可摆手，庆祝可点头或轻拍手。行动幅度应适合16帧；复杂多阶段动作应简化，或在用户指定较长时长时增加帧数。不要用整体缩放替代用户要求的四肢动作。

动作停顿可以自然存在；完全重复的帧不是自动失败，但要防止生成器重复整行，或编码器合并重复帧导致16帧合同失效。对于严格16帧要求，修复生成内容，不能向不可见角落加噪点来骗过帧数验证。

字体“相同”包括：字形、字体文件、字号、颜色、描边、排版与位置。主配文只渲染一次。用户希望沿用特殊艺术字时，需要独立透明的文字素材；不要从含人物遮挡的区域粗暴剪出一块带底的文字。

生成提示不包含主配文或要求生成器加粗字样。主体的透明底、边缘修复在PNG阶段完成；默认的适度加粗由后续固定文字层实现。合成GIF前必须先通过静态预检，详见assembly.md。
