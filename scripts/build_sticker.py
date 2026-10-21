#!/usr/bin/env python3
"""Assemble 16 approved transparent frames; do not generate or repair artwork."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def require(condition, message):
    if not condition:
        raise ValueError(message)


def rgba(path):
    image = Image.open(path)
    require('A' in image.getbands() or 'transparency' in image.info,
            f'{path}: no transparency channel; remove background before assembling')
    image = image.convert('RGBA')
    require(image.getchannel('A').getextrema()[0] < 128,
            f'{path}: fully opaque background; not a transparent source')
    return image


def assemble(config_path, prepare_only=False):
    config_path = Path(config_path).resolve()
    cfg = json.loads(config_path.read_text(encoding='utf-8'))
    def resolve(value):
        p = Path(value).expanduser()
        return p if p.is_absolute() else config_path.parent / p

    output = resolve(cfg['output'])
    preflight = output.with_name(output.name + '-preflight')
    if not prepare_only:
        require(cfg.get('preflight_approved') is True,
                'Run --prepare-only, visually review the preflight PNGs, then set preflight_approved=true')
    require(not output.exists() or (output.is_dir() and not any(output.iterdir())),
            f'Output must be a new or empty directory: {output}')
    size = int(cfg.get('size', 400))
    duration = int(cfg.get('duration_ms', 100))
    require(160 <= size <= 1600, 'size must be 160–1600 pixels')
    require(duration >= 20 and duration % 10 == 0,
            'duration_ms must be >=20 and a multiple of 10')
    require(bool(cfg.get('sheet')) != bool(cfg.get('frames')),
            'Specify either sheet or frames, not both')
    if cfg.get('frames'):
        require(len(cfg['frames']) == 16, 'Exactly 16 input frames required')
        tiles = [rgba(resolve(p)) for p in cfg['frames']]
    else:
        sheet = rgba(resolve(cfg['sheet']))
        rects = cfg.get('rects')
        if rects is None:
            rects = [(round(c*sheet.width/4), round(r*sheet.height/4),
                      round((c+1)*sheet.width/4), round((r+1)*sheet.height/4))
                     for r in range(4) for c in range(4)]
        require(len(rects) == 16, 'Exactly 16 crop rectangles required')
        tiles = []
        for rect in rects:
            require(len(rect) == 4 and all(isinstance(v, int) for v in rect),
                    'rects must contain integer pixel bounds')
            l, t, r, b = rect
            require(0 <= l < r <= sheet.width and 0 <= t < b <= sheet.height,
                    f'Invalid rectangle: {rect}')
            tiles.append(sheet.crop(rect))

    caption_top = round(size * .87)
    caption_layer = Image.new('RGBA', (size, size))
    font_path = None
    actual_font_size = None
    stroke_width = None
    if cfg.get('caption_layer'):
        caption_layer = rgba(resolve(cfg['caption_layer']))
        require(caption_layer.size == (size, size), 'caption_layer size must equal output size')
        require(caption_layer.crop((0, 0, size, caption_top)).getbbox() is None,
                'caption_layer must stay inside the bottom caption region')
    else:
        caption = cfg.get('caption', '')
        require(caption and '\n' not in caption, 'Provide a nonempty one-line caption')
        if cfg.get('font'):
            font_path = resolve(cfg['font'])
        else:
            candidates = [Path('/System/Library/Fonts/STHeiti Medium.ttc'),
                          Path('/System/Library/Fonts/Hiragino Sans GB.ttc'),
                          Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')]
            font_path = next((p for p in candidates if p.exists()), None)
        require(font_path is not None and font_path.is_file(),
                'Provide a font file supporting the caption; no silent font substitution')
        actual_font_size = int(cfg.get('font_size', round(34*size/400)))
        stroke_width = float(cfg.get('caption_stroke_width', size/400))
        require(0 <= stroke_width <= 4*size/400,
                'caption_stroke_width must be between 0 and 4px per 400px canvas')
        # Render the fixed text once at 4x; the same-color stroke thickens glyphs
        # without changing the font file or introducing a background-colored fringe.
        text_scale = 4
        high_res = Image.new('RGBA', (size*text_scale, size*text_scale))
        draw = ImageDraw.Draw(high_res)
        stroke = round(stroke_width*text_scale)
        while actual_font_size >= 8:
            font = ImageFont.truetype(str(font_path), actual_font_size*text_scale)
            box = tuple(v/text_scale for v in draw.textbbox(
                (0, 0), caption, font=font, stroke_width=stroke))
            if box[2]-box[0] <= size*.915 and box[3]-box[1] <= size*.1:
                break
            actual_font_size -= 1
        require(actual_font_size >= 8, 'Caption too long; shorten it or increase size')
        x = (size-(box[2]-box[0]))/2-box[0]
        y = size*.9+(size*.085-(box[3]-box[1]))/2-box[1]
        color = cfg.get('caption_color', '#354C28')
        draw.text((round(x*text_scale), round(y*text_scale)), caption, font=font,
                  fill=color, stroke_width=stroke, stroke_fill=color)
        caption_layer = high_res.resize((size, size), Image.Resampling.LANCZOS)
        require(caption_layer.crop((0, 0, size, caption_top)).getbbox() is None,
                'Caption exceeds its reserved region; shorten it or reduce font/stroke size')

    offsets = cfg.get('offsets', [[0, 0] for _ in range(16)])
    require(len(offsets) == 16 and all(len(v) == 2 for v in offsets),
            'offsets requires 16 pairs')
    scale = min(size*.86/max(t.width for t in tiles), size*.86/max(t.height for t in tiles))
    frames = []
    for n, tile in enumerate(tiles):
        tile = tile.resize((max(1, round(tile.width*scale)), max(1, round(tile.height*scale))),
                           Image.Resampling.LANCZOS)
        x = round((size-tile.width)/2+offsets[n][0])
        y = round((size*.86-tile.height)/2+offsets[n][1])
        box = tile.getchannel('A').point(lambda a: 255 if a >= 128 else 0).getbbox()
        require(box is not None, f'Frame {n+1} is empty')
        require(0 <= x+box[0] and x+box[2] <= size and 0 <= y+box[1]
                and y+box[3] <= caption_top, f'Frame {n+1} clips or overlaps caption')
        frame = Image.new('RGBA', (size, size))
        frame.alpha_composite(tile, (x, y))
        frame.alpha_composite(caption_layer)
        frames.append(frame)

    atlas = Image.new('RGBA', (4*size, 4*size))
    for n, frame in enumerate(frames):
        atlas.alpha_composite(frame, ((n%4)*size, (n//4)*size))
    # Approval is manual; the digest only ensures the encoded pixels match the
    # static review, never that the artwork or edges passed visual inspection.
    digest = hashlib.sha256(atlas.tobytes() + str(duration).encode()).hexdigest()
    if prepare_only:
        require(not preflight.exists() or not any(preflight.iterdir()),
                f'Preflight directory must be new or empty: {preflight}; use a new output version')
        preflight.mkdir(parents=True, exist_ok=True)
        atlas.save(preflight/'sprite-4x4.png')
        caption_layer.save(preflight/'caption-fixed.png')
        (preflight/'frames').mkdir()
        for n, frame in enumerate(frames):
            frame.save(preflight/'frames'/f'{n+1:02}.png')
        binary = atlas.copy()
        binary.putalpha(atlas.getchannel('A').point(lambda a: 255 if a >= 128 else 0))
        for name, color in [('light', '#ECEEED'), ('dark', '#252A33')]:
            for prefix, source in [('preview', atlas), ('gif-alpha', binary)]:
                bg = Image.new('RGBA', atlas.size, color)
                bg.alpha_composite(source)
                bg.convert('RGB').save(preflight/f'{prefix}-{name}.png')
        review = dict(pixel_digest=digest, approval_required=True,
                      font=str(font_path) if font_path else 'caption_layer',
                      actual_font_size=actual_font_size, caption_stroke_width=stroke_width,
                      visual_review='Pending human/agent visual inspection; no GIF encoded')
        (preflight/'review.json').write_text(json.dumps(review, ensure_ascii=False, indent=2))
        print(f'Static preflight saved: {preflight}; inspect PNGs before approving GIF encoding')
        return review
    require((preflight/'review.json').is_file(), 'Missing preflight; run --prepare-only first')
    review = json.loads((preflight/'review.json').read_text())
    require(review.get('pixel_digest') == digest,
            'Artwork, caption, layout or timing changed since preflight; prepare and review a new output version')
    # Select colors from opaque pixels, not RGB data hidden under transparent pixels.
    raw = np.asarray(atlas)
    visible = raw[:, :, :3][raw[:, :, 3] >= 128]
    samples = visible[::max(1, len(visible)//250000)]
    palette_image = Image.fromarray(samples.reshape(-1, 1, 3)).quantize(
        colors=255, method=Image.Quantize.MEDIANCUT)
    palette = (palette_image.getpalette()+[0]*768)[:768]
    palette[765:768] = palette[762:765]
    palette_image.putpalette(palette)
    indexed = []
    for frame in frames:
        q = frame.convert('RGB').quantize(palette=palette_image, dither=Image.Dither.NONE)
        data = np.array(q)
        data[data == 255] = 254  # 255 is reserved exclusively for transparency.
        data[np.asarray(frame.getchannel('A')) < 128] = 255
        q = Image.fromarray(data)
        q.putpalette(palette)
        q.info['transparency'] = 255
        indexed.append(q)

    output.mkdir(parents=True, exist_ok=True)
    gif = output/'sticker.gif'
    indexed[0].save(gif, save_all=True, append_images=indexed[1:], duration=duration,
                    loop=0, disposal=2, transparency=255, background=255, optimize=False)
    decoded = Image.open(gif)
    require(decoded.n_frames == 16,
            f'Encoder retained {decoded.n_frames}/16 frames; inspect duplicated poses')
    require(decoded.info.get('loop') == 0, 'Loop metadata missing')
    text_hashes, frame_hashes, appearances = [], [], []
    previews = {'light': [], 'dark': []}
    for n in range(16):
        decoded.seek(n)
        require(decoded.info.get('duration') == duration, f'Frame {n+1}: timing mismatch')
        frame = decoded.convert('RGBA')
        alpha = np.asarray(frame.getchannel('A'))
        require(alpha.min() == 0 and alpha.max() == 255, f'Frame {n+1}: invalid transparency')
        require(np.array_equal(alpha == 0, np.asarray(frames[n].getchannel('A')) < 128),
                f'Frame {n+1}: disposal/alpha mismatch')
        text_hashes.append(hashlib.sha256(frame.crop((0, caption_top, size, size)).tobytes()).hexdigest())
        frame_hashes.append(hashlib.sha256(frame.tobytes()).hexdigest())
        for name, color in [('light', '#ECEEED'), ('dark', '#252A33')]:
            bg = Image.new('RGBA', frame.size, color)
            bg.alpha_composite(frame)
            previews[name].append(bg.convert('RGB'))
        appearances.append(np.asarray(previews['light'][-1], dtype=np.float32))
    require(len(set(text_hashes)) == 1, 'Caption pixels vary across frames')
    diffs = [round(float(np.abs(appearances[(n+1)%16]-appearances[n]).mean()), 3)
             for n in range(16)]
    median = float(np.median(diffs))
    warnings = []
    if diffs[-1] > max(1.8*median, 2):
        warnings.append('Loop seam difference is elevated; inspect 16 -> 1 visually')
    if len(set(frame_hashes)) < 16:
        warnings.append('Some decoded poses repeat; check holds and motion progression')
    report = dict(frames=16, unique_frames=len(set(frame_hashes)), size=[size, size],
                  duration_ms=duration, loop_duration_ms=16*duration, transparent=True,
                  caption_fixed=True, font=str(font_path) if font_path else 'caption_layer',
                  actual_font_size=actual_font_size, adjacent_pixel_differences=diffs,
                  caption_stroke_width=stroke_width, preflight_approved=True,
                  preflight_pixel_digest=digest,
                  warnings=warnings, visual_review='Required; encoding checks do not prove smooth motion')
    atlas.save(output/'sprite-4x4.png')
    caption_layer.save(output/'caption-fixed.png')
    (output/'frames').mkdir(exist_ok=True)
    for n, frame in enumerate(frames):
        frame.save(output/'frames'/f'{n+1:02}.png')
    for name, preview in previews.items():
        p = preview[0].quantize(colors=255)
        qs = [f.quantize(palette=p, dither=Image.Dither.NONE) for f in preview]
        qs[0].save(output/f'preview-{name}.gif', save_all=True, append_images=qs[1:],
                   duration=duration, loop=0, disposal=2)
    (output/'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    (output/'preview.html').write_text('''<!doctype html><meta charset="utf-8">
<title>透明表情包预览</title><style>body{font-family:system-ui;background:#999}
section{display:inline-block;margin:12px;padding:20px;border-radius:16px}
img{width:400px;max-width:80vw}section:first-child{background:#eceeed}section:last-child{background:#252a33}</style>
<section><img src="sticker.gif" alt="浅色背景"></section><section><img src="sticker.gif" alt="深色背景"></section>''', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config', type=Path)
    parser.add_argument('--prepare-only', action='store_true',
                        help='Save static PNG review sheets and frames without encoding GIF')
    args = parser.parse_args()
    try:
        assemble(args.config, prepare_only=args.prepare_only)
    except (ValueError, OSError, KeyError) as error:
        parser.exit(1, f'Error: {error}\n')
