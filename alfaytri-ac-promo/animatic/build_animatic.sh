#!/usr/bin/env bash
# Builds a 30 s, 1080x1920 placeholder animatic (timing reference for the editor).
# Each scene is a colour plate with the shot description and the exact on-screen text timings.
# Usage: ./build_animatic.sh   ->  alfaytri_ac_promo_animatic.mp4
set -euo pipefail
cd "$(dirname "$0")"
FONT_B=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf
FONT=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf
T=txt; mkdir -p "$T"

# Text snippets go into files so no shell or ffmpeg escaping is needed
printf 'SCENE 1 · SUMMER HEAT · 0–5s'            > $T/l1
printf 'SCENE 2 · ALFAYTRI ARRIVES · 5–10s'      > $T/l2
printf 'SCENE 3 · MAINTENANCE · 10–21s'          > $T/l3
printf 'SCENE 4 · COMFORT RESTORED · 21–26s'     > $T/l4
printf 'SCENE 5 · BRAND CARD · 26–30s'           > $T/l5
printf 'Midday sun · dusty filters\nresident checks remote'          > $T/d1
printf 'Van arrives · greeting\ninspection'                          > $T/d2
printf 'Isolate power · protect · wash filters\ncoil bag clean · drain · outdoor · test' > $T/d3
printf 'Clean AC running · subtle airflow\nresident relaxes · final check' > $T/d4
printf 'Summer heat in Qatar…\nAC not cooling?'  > $T/h1
printf 'Alfaytri is here to help.'               > $T/h2
printf 'Inspect.'                                > $T/h3a
printf 'Inspect. Clean.'                         > $T/h3b
printf 'Inspect. Clean. Service.'                > $T/h3c
printf 'Inspect. Clean. Service. Test.'          > $T/h3d
printf 'Clean AC. Cool home.\nSummer comfort.'   > $T/h4
printf 'ALFAYTRI'                                > $T/b1
printf 'Maintenance Company'                     > $T/b2
printf '“Keep your cool this summer.”'           > $T/b3
printf 'Book your AC maintenance today.'         > $T/b4
printf '[Phone / WhatsApp]'                      > $T/b5
printf '[LOGO PLACEHOLDER]'                      > $T/b6

lab() { echo "drawtext=fontfile=$FONT_B:textfile=$T/$1:fontsize=40:fontcolor=white@0.85:x=(w-tw)/2:y=300:enable='between(t,$2,$3)'"; }
desc(){ echo "drawtext=fontfile=$FONT:textfile=$T/$1:fontsize=38:line_spacing=14:fontcolor=white@0.7:x=(w-tw)/2:y=380:enable='between(t,$2,$3)'"; }
head(){ echo "drawtext=fontfile=$FONT_B:textfile=$T/$1:fontsize=${4:-70}:line_spacing=20:fontcolor=white:shadowcolor=black@0.35:shadowx=4:shadowy=4:x=(w-tw)/2:y=(h-th)/2:enable='between(t,$2,$3)'"; }
brand(){ echo "drawtext=fontfile=$5:textfile=$T/$1:fontsize=$4:fontcolor=white:x=(w-tw)/2:y=$2:enable='gte(t,$3)'"; }

F=$(IFS=,; echo "$(lab l1 0 5),$(desc d1 0 5),$(head h1 0.5 5),\
$(lab l2 5 10),$(desc d2 5 10),$(head h2 5.5 10),\
$(lab l3 10 21),$(desc d3 10 21),$(head h3a 10.5 13 64),$(head h3b 13 16 64),$(head h3c 16 19 64),$(head h3d 19 21 52),\
$(lab l4 21 26),$(desc d4 21 26),$(head h4 21.5 26),\
$(brand b6 600 26 34 $FONT),$(brand b1 760 26.2 120 $FONT_B),$(brand b2 910 26.2 50 $FONT),\
$(brand b3 1080 26.5 52 $FONT),$(brand b4 1170 26.8 52 $FONT_B),$(brand b5 1300 27.1 56 $FONT_B)")

# Colour plates follow the grade: warm -> neutral -> cool -> brand placeholder (navy)
ffmpeg -y -hide_banner -loglevel error \
  -f lavfi -i color=c=0xC8742E:s=1080x1920:d=5:r=30 \
  -f lavfi -i color=c=0xB98A4E:s=1080x1920:d=5:r=30 \
  -f lavfi -i color=c=0x6B7680:s=1080x1920:d=11:r=30 \
  -f lavfi -i color=c=0x2E8FA3:s=1080x1920:d=5:r=30 \
  -f lavfi -i color=c=0x14284B:s=1080x1920:d=4:r=30 \
  -f lavfi -i anullsrc=r=48000:cl=stereo \
  -filter_complex "[0][1][2][3][4]concat=n=5:v=1:a=0,$F,format=yuv420p[v]" \
  -map "[v]" -map 5:a -t 30 -c:v libx264 -crf 23 -preset medium -c:a aac -b:a 64k -movflags +faststart \
  alfaytri_ac_promo_animatic.mp4
rm -rf "$T"
echo "Wrote $(pwd)/alfaytri_ac_promo_animatic.mp4"
