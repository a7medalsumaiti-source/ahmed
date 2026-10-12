# Alfaytri — "Warm Air" Summer AC Promo (30 s, 9:16)

| Path | Purpose |
|---|---|
| **[exports/alfaytri_ac_promo_30s.mp4](exports/alfaytri_ac_promo_30s.mp4)** | **Finished 30 s video**: flat-illustrated 2D animation of the storyboard, with brand captions, end card, music and SFX (no voice-over) |
| [video/build_video.py](video/build_video.py) | Re-renders the finished video (`python3 video/build_video.py`, about 2 min, needs Pillow, numpy and ffmpeg) |
| [video/build_photoreal.py](video/build_photoreal.py) | Photorealistic version: generates each storyboard shot with Google Vertex AI (Veo), then assembles it with the same captions, end card and audio. Needs `GOOGLE_CLOUD_PROJECT` and a valid credential (see the file header) |
| [STORYBOARD.md](STORYBOARD.md) | Continuity bible, shot-by-shot storyboard, timed VO, sound design, AI video-generation prompts, finishing checklist |
| [exports/end_card.mp4](exports/end_card.mp4) · [end_card.png](exports/end_card.png) | Finished 3 s animated brand card (Scene 5) |
| [exports/overlays/](exports/overlays/) | Transparent 1080×1920 caption overlays, in brand style |
| [exports/alfaytri_ac_promo_animatic.mp4](exports/alfaytri_ac_promo_animatic.mp4) | 30 s branded timing animatic (footage shown as placeholders) |
| [voiceover_en.srt](voiceover_en.srt) · [onscreen_text.srt](onscreen_text.srt) | Timed VO captions and headline timings |
| [brand/](brand/) | Style sheet, logos (colour and white, transparent PNG) and the Changa font |
| [animatic/build_branded.py](animatic/build_branded.py) | Re-renders everything in `exports/` (`python3 animatic/build_branded.py`, needs Pillow and ffmpeg) |

Brand: orange `#F7901E`, dark grey `#414042`, Changa typeface (from the AlFaytri style sheet).
Still to supply: the real phone/WhatsApp number (currently `[Phone / WhatsApp]`).
