"""Build an illustrated, narrated walkthrough from the app's actual screenshots."""
from pathlib import Path
import json
import math
import subprocess
import wave

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).resolve().parent
W, H = 1920, 1080
PINE = '#153b30'
GREEN = '#254f40'
LIME = '#d5e6a6'
CREAM = '#f4f6f0'
MUTED = '#637268'
FONT = 'C:/Windows/Fonts/segoeui.ttf'
BOLD = 'C:/Windows/Fonts/segoeuib.ttf'


def font(size, bold=False):
    return ImageFont.truetype(BOLD if bold else FONT, size)


def lines(draw, text, face, max_width):
    result, current = [], ''
    for word in text.split():
        candidate = (current + ' ' + word).strip()
        if current and draw.textlength(candidate, font=face) > max_width:
            result.append(current)
            current = word
        else:
            current = candidate
    if current:
        result.append(current)
    return result


def paragraph(draw, text, position, face, width, fill, line_height):
    x, y = position
    for line in lines(draw, text, face, width):
        draw.text((x, y), line, font=face, fill=fill)
        y += line_height
    return y


def rounded_image(canvas, path, box, radius=16):
    x, y, w, h = map(round, box)
    picture = Image.open(path).convert('RGB').resize((w, h), Image.Resampling.LANCZOS)
    mask = Image.new('L', (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w-1, h-1), radius=radius, fill=255)
    canvas.paste(picture, (x, y), mask)


def shadow(canvas, box, radius=28):
    layer = Image.new('RGBA', canvas.size)
    x, y, w, h = box
    ImageDraw.Draw(layer).rounded_rectangle((x, y+12, x+w, y+h+12), radius=radius, fill=(16, 49, 34, 35))
    canvas.alpha_composite(layer.filter(ImageFilter.GaussianBlur(20)))


def phone(canvas, path, x, y=166, height=744, label=''):
    picture = Image.open(path)
    width = round(picture.width / picture.height * height)
    shadow(canvas, (x-12, y-12, width+24, height+24))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((x-12, y-12, x+width+12, y+height+12), radius=30, fill=PINE)
    rounded_image(canvas, path, (x, y, width, height), 21)
    draw = ImageDraw.Draw(canvas)
    if label:
        tw = draw.textlength(label, font=font(19))
        draw.text((x+(width-tw)/2, y+height+23), label, font=font(19), fill=MUTED)
    return width


def desktop(canvas, path, x=646, y=214, width=1210):
    picture = Image.open(path)
    height = round(picture.height / picture.width * width)
    shadow(canvas, (x-2, y-42, width+4, height+44), radius=18)
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((x-2, y-42, x+width+2, y+height+2), radius=18, fill='#e3e9dd')
    for i, color in enumerate(['#7e9a82', '#b4c59b', '#ced9bc']):
        draw.ellipse((x+18+i*22, y-26, x+29+i*22, y-15), fill=color)
    draw.text((x+102, y-31), 'Courtside / Overview', fill=MUTED, font=font(17))
    rounded_image(canvas, path, (x, y, width, height), 4)


def frame(scene, caption, sentence_index, sentence_count, elapsed, total):
    canvas = Image.new('RGBA', (W, H), CREAM)
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, W, 101), fill=PINE)
    draw.ellipse((65, 25, 109, 69), outline=LIME, width=3)
    draw.arc((54, 20, 91, 74), -65, 65, fill=LIME, width=3)
    draw.arc((83, 20, 120, 74), 115, 245, fill=LIME, width=3)
    draw.text((126, 19), 'courtside.', font=font(38, True), fill='#f0f5df')
    draw.text((1368, 30), 'INTERFACE WALKTHROUGH', font=font(21, True), fill='#cbd9c1')
    for i in range(7):
        x = 64 + i * 257
        draw.rounded_rectangle((x, 115, x+238, 121), radius=3, fill=LIME if i < int(scene['id']) else '#dce4d5')
    draw.text((64, 172), scene['id'] + ' / ' + scene['label'], font=font(19, True), fill=GREEN)
    title_bottom = paragraph(draw, scene['title'], (64, 213), font(51, True), 520, PINE, 62)
    bullet_y = max(407, title_bottom + 48)
    active = min(2, int(sentence_index / max(1, sentence_count) * 3))
    for i, bullet in enumerate(scene['bullets']):
        draw.ellipse((65, bullet_y+11, 88, bullet_y+34), fill=GREEN if i == active else '#d9e4d1')
        if i == active:
            draw.ellipse((72, bullet_y+18, 81, bullet_y+27), fill=LIME)
        bottom = paragraph(draw, bullet, (106, bullet_y), font(28), 458, GREEN if i == active else MUTED, 39)
        bullet_y = bottom + 32
    draw.text((65, 841), 'ACTUAL APP SCREENS', font=font(16, True), fill=GREEN)
    draw.text((65, 869), 'Sample sessions · illustrative measurements', font=font(18), fill=MUTED)
    draw.line((602, 166, 602, 914), fill='#dce4d7', width=2)

    images = [ROOT/'screens'/name for name in scene['images']]
    layout = scene['layout']
    if layout == 'intro':
        desktop(canvas, images[0], 655, 264, 1110)
        phone(canvas, images[1], 1528, 166, 736, 'PHONE VIEW')
    elif layout == 'desktop':
        desktop(canvas, images[0])
    elif layout == 'phone':
        phone(canvas, images[0], 922, 166, 744, 'SESSION LIBRARY / LIST VIEW')
        d = ImageDraw.Draw(canvas)
        d.rounded_rectangle((1334, 310, 1826, 680), radius=22, fill='#e5ecd9')
        d.text((1370, 345), 'What changed', font=font(29, True), fill=PINE)
        for j, label in enumerate(['A readable workspace row', 'Larger touch targets', 'Status under each title']):
            d.text((1370, 412+j*78), '0'+str(j+1), font=font(22, True), fill=GREEN)
            paragraph(d, label, (1426, 408+j*78), font(24), 353, GREEN, 32)
    elif layout == 'phones':
        labels = {'04':['CAMERA PREVIEW', 'PERMISSION & START'], '05':['CHOOSE A SHOT', 'CLIP & MEASUREMENTS'], '06':['READABLE CHART LABELS', 'UPLOAD DIALOG']}
        phone(canvas, images[0], 802, 166, 744, labels[scene['id']][0])
        phone(canvas, images[1], 1330, 166, 744, labels[scene['id']][1])
    else:
        phone(canvas, images[0], 666, 166, 744, 'PORTRAIT NAVIGATION')
        landscape = Image.open(images[1])
        lw = 753
        lh = round(landscape.height/landscape.width*lw)
        shadow(canvas, (1074, 226, lw+20, lh+20))
        d = ImageDraw.Draw(canvas)
        d.rounded_rectangle((1074, 226, 1094+lw, 246+lh), radius=25, fill=PINE)
        rounded_image(canvas, images[1], (1084, 236, lw, lh), 18)
        d.text((1185, 268+lh), 'SHORT LANDSCAPE NAVIGATION', font=font(18), fill=MUTED)
        d.rounded_rectangle((1084, 690, 1837, 882), radius=20, fill=PINE)
        d.text((1121, 720), '26 frontend tests passed', font=font(34, True), fill=LIME)
        d.text((1121, 778), 'Production build passed', font=font(27), fill='#eef4e7')
        d.text((1121, 828), 'Phone, tablet and landscape layouts checked', font=font(20), fill='#c5d4bc')

    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 956, W, H), fill=PINE)
    caption_lines = lines(draw, caption, font(31), 1700)
    caption_y = 972 if len(caption_lines) > 1 else 990
    for line in caption_lines:
        tw = draw.textlength(line, font=font(31))
        draw.text(((W-tw)/2, caption_y), line, font=font(31), fill='#f2f6eb')
        caption_y += 43
    draw.rectangle((0, 1073, round(W * min(1, elapsed/total)), 1079), fill=LIME)
    return canvas.convert('RGB')


def srt_time(seconds):
    milliseconds = round(seconds * 1000)
    h, milliseconds = divmod(milliseconds, 3600000)
    m, milliseconds = divmod(milliseconds, 60000)
    s, milliseconds = divmod(milliseconds, 1000)
    return f'{h:02}:{m:02}:{s:02},{milliseconds:03}'


def main():
    scenes = json.loads((ROOT/'scenes.json').read_text(encoding='utf-8'))
    segments = json.loads((ROOT/'segments.json').read_text(encoding='utf-8-sig'))
    (ROOT/'frames').mkdir(exist_ok=True)
    timeline, chunks, cursor, reference = [], [], 0.0, None
    for index, segment in enumerate(segments):
        with wave.open(str(ROOT/'audio'/segment['file']), 'rb') as source:
            params = source.getparams()
            if reference is None:
                reference = params
            assert (params.nchannels, params.sampwidth, params.framerate) == (reference.nchannels, reference.sampwidth, reference.framerate)
            pcm = source.readframes(source.getnframes())
            duration = source.getnframes()/source.getframerate()
        if index == 0:
            prefix = b'\0' * int(.3*reference.framerate)*reference.nchannels*reference.sampwidth
            chunks.append(prefix)
            cursor += .3
        segment['start'] = cursor
        segment['duration'] = duration
        segment['end'] = cursor + duration
        chunks.append(pcm)
        cursor += duration
        last_in_scene = index == len(segments)-1 or segments[index+1]['scene'] != segment['scene']
        pause = .7 if last_in_scene else .06
        silence = b'\0' * round(pause*reference.framerate)*reference.nchannels*reference.sampwidth
        chunks.append(silence)
        segment['frame_duration'] = duration + pause + (.3 if index == 0 else 0)
        cursor += pause
        timeline.append(segment)
    with wave.open(str(ROOT/'narration.wav'), 'wb') as output:
        output.setparams(reference)
        output.writeframes(b''.join(chunks))
    level = np.frombuffer(b''.join(chunks), dtype='<i2').astype(float)
    print(f'Narration {cursor:.1f}s; peak {np.abs(level).max():.0f}; RMS {np.sqrt(np.mean(level**2)):.0f}', flush=True)
    assert np.sqrt(np.mean(level**2)) > 100, 'Narration must contain audible speech.'

    concat, subtitles, chapters = [], [], [';FFMETADATA1', 'title=Courtside interface and mobile walkthrough', 'comment=Actual app screenshots with illustrative sample sessions; narrated and captioned walkthrough.']
    for scene in scenes:
        pieces = [piece for piece in timeline if piece['scene'] == scene['id']]
        chapters += ['[CHAPTER]', 'TIMEBASE=1/1000', f'START={round(pieces[0]["start"]*1000)}', f'END={round((pieces[-1]["end"]+.7)*1000)}', 'title='+scene['title']]
        for sentence_index, piece in enumerate(pieces):
            image_path = ROOT/'frames'/f'{scene["id"]}-{sentence_index:02}.png'
            image = frame(scene, piece['text'], sentence_index, len(pieces), piece['start'], cursor)
            image.save(image_path, optimize=True)
            concat += ["file '"+image_path.as_posix()+"'", f'duration {piece["frame_duration"]:.6f}']
            subtitles += [str(len(subtitles)//4+1), srt_time(piece['start'])+' --> '+srt_time(piece['end']), piece['text'], '']
        print('Rendered chapter '+scene['id'], flush=True)
    concat += ["file '"+image_path.as_posix()+"'"]
    (ROOT/'video.ffconcat').write_text('\n'.join(concat)+'\n', encoding='utf-8')
    (ROOT/'captions.srt').write_text('\n'.join(subtitles), encoding='utf-8')
    (ROOT/'chapters.ffmeta').write_text('\n'.join(chapters)+'\n', encoding='utf-8')
    (ROOT/'timeline.json').write_text(json.dumps(timeline, indent=2), encoding='utf-8')
    (ROOT/'transcript.txt').write_text('\n\n'.join(scene['title']+'\n'+scene['text'] for scene in scenes), encoding='utf-8')
    first = frame(scenes[0], timeline[0]['text'], 0, 3, 0, cursor)
    first.save(ROOT/'poster.jpg', quality=94)

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    command = [ffmpeg, '-y', '-hide_banner', '-loglevel', 'warning', '-f', 'concat', '-safe', '0', '-i', str(ROOT/'video.ffconcat'), '-i', str(ROOT/'narration.wav'), '-i', str(ROOT/'chapters.ffmeta'), '-map', '0:v:0', '-map', '1:a:0', '-map_metadata', '2', '-vf', 'fps=24', '-c:v', 'libx264', '-preset', 'fast', '-crf', '19', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-ar', '48000', '-b:a', '128k', '-movflags', '+faststart', '-shortest', str(ROOT/'courtside-walkthrough.mp4')]
    subprocess.run(command, check=True)
    print('Saved '+str(ROOT/'courtside-walkthrough.mp4'), flush=True)


if __name__ == '__main__':
    main()
