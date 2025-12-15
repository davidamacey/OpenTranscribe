# Universal Media URL Test Videos

This document contains publicly accessible video URLs for testing the Universal Media URL feature in OpenTranscribe. All videos are short (under 5 minutes) and publicly accessible without login.

**Last Updated:** December 2025

---

## Platform Authentication Summary

| Platform | Auth Required | Reliability | Notes |
|----------|--------------|-------------|-------|
| YouTube | No (mostly) | **Excellent** | Best supported platform. Most videos are publicly accessible. |
| Dailymotion | No (mostly) | **Good** | Reliable alternative to YouTube for public videos. |
| Twitter/X | Sometimes | **Good** | Most public tweets with video work. |
| TikTok | Sometimes | **Variable** | May have regional restrictions or require authentication. |
| Vimeo | **Yes (often)** | **Limited** | Many videos require login. Only fully public videos work. |
| Instagram | **Yes (usually)** | **Poor** | Most content requires login. Not recommended. |
| Facebook | **Yes (usually)** | **Poor** | Most videos require authentication. Not recommended. |
| Twitch | Sometimes | **Limited** | VODs may be subscriber-only. Clips generally work. |

**Recommended for Testing**: Start with **YouTube** (best support), then Dailymotion or Twitter/X.

**Important**: Authentication is not currently supported. Videos requiring login will fail.

---

## YouTube Videos

| URL | Description | Duration |
|-----|-------------|----------|
| https://www.youtube.com/watch?v=WO4tIrjBDkk | Inspirational short video | ~2-3 min |
| https://www.youtube.com/watch?v=BOksW_NabEk | Motivational short video | ~2-3 min |
| https://www.youtube.com/watch?v=qM-gZintWDc | Inspirational content | ~2-3 min |
| https://www.youtube.com/watch?v=l-gQLqv9f4o | Short inspirational video | ~2-3 min |
| https://www.youtube.com/watch?v=c0ZzN6hxdzo | Motivational content | ~2-3 min |

### YouTube Shorts (up to 3 minutes as of Oct 2024)
| URL | Description | Duration |
|-----|-------------|----------|
| https://www.youtube.com/shorts/3xReIHV13IQ | Example YouTube Short | < 3 min |

### Notes for YouTube
- YouTube URLs work in both formats: `youtube.com/watch?v=VIDEO_ID` and `youtu.be/VIDEO_ID`
- YouTube Shorts URLs can be converted: `youtube.com/shorts/VIDEO_ID` -> `youtube.com/watch?v=VIDEO_ID`
- As of October 2024, YouTube Shorts can be up to 3 minutes long

---

## Vimeo Videos

| URL | Description | Duration |
|-----|-------------|----------|
| https://vimeo.com/2336458 | Short animated film | ~2-5 min |
| https://vimeo.com/32613201 | "SPRING" - animated short | ~3-5 min |
| https://vimeo.com/17565861 | "The Tadpole" - animated short | ~3-5 min |
| https://vimeo.com/blog/post/cyclists-veljko-popovic-staff-pick-premiere/ | "Cyclists" - award-winning animation (Staff Pick Premiere page) | ~4-5 min |

### Vimeo Staff Picks (Search for these titles on vimeo.com)
- "A Crab in the Pool" by Jean-Sebastien Hamel and Alexandra Myotte
- "Return to Hairy Hill" by Daniel Gies
- "Boat People" by Thao Lam and Kjell Boersma (NFB)
- "Sierra" by Sander Joon (animated)

### Notes for Vimeo
- Vimeo URLs follow format: `vimeo.com/VIDEO_ID`
- **Authentication Issues**: Most Vimeo videos now require login to access. If you encounter "logged-in" errors, try YouTube or Dailymotion instead.
- Some videos may have regional restrictions (EU/UK limitations on some Staff Pick content)
- Private videos require password and are not supported
- **Workaround**: Search for "Vimeo Staff Picks" or "Vimeo Short Film" directly on Vimeo to find publicly accessible content

---

## TikTok Videos

| URL | Description | Duration |
|-----|-------------|----------|
| https://www.tiktok.com/@bellapoarch/video/6862153058223197445 | Bella Poarch "M to the B" - most liked TikTok | ~15 sec |
| https://www.tiktok.com/@marenmicrobe | Science educator profile (browse videos) | Various |
| https://www.tiktok.com/@rhodeslovesneuroscience | Neuroscience educator profile (browse videos) | Various |
| https://www.tiktok.com/@scientificblonde | Women's health science educator | Various |

### Educational TikTok Accounts to Find Short Videos
- @nilered - Chemistry experiments (3.7M+ followers)
- @instituteofhumananatomy - Human biology (6.5M+ followers)

### Notes for TikTok
- TikTok URLs follow format: `tiktok.com/@USERNAME/video/VIDEO_ID`
- Most TikTok videos are under 3 minutes
- **Known Issues**: TikTok downloads may fail due to:
  - Regional restrictions (geo-blocking)
  - Anti-bot measures by TikTok
  - Content requiring age verification
- **Recommendation**: If TikTok fails, use YouTube or Dailymotion instead

---

## X (Twitter) Videos

| URL | Description | Duration |
|-----|-------------|----------|
| https://x.com/Olympics/status/1873685005970669886 | Paris 2024 Olympic highlights - Jin (BTS) torch relay | ~30-60 sec |
| https://x.com/debugsenpai/status/1893560031817478531 | Viral post example | ~30 sec |

### Notes for X (Twitter)
- Twitter.com URLs automatically redirect to X.com as of May 2024
- Both formats work: `twitter.com/USER/status/ID` and `x.com/USER/status/ID`
- Video length limited to 140 seconds for free users, up to 4 hours for Premium

---

## Dailymotion Videos

| URL | Description | Duration |
|-----|-------------|----------|
| https://www.dailymotion.com/video/x9vqjvo | CH-7 stealth drone flight debut | ~1-2 min |
| https://www.dailymotion.com/video/x9vpkem | "Discovering One Of The Largest Black Holes" | ~2-3 min |
| https://www.dailymotion.com/video/x9vpwzs | DOQAUS Bluetooth Headphones Review | ~2-3 min |
| https://www.dailymotion.com/video/x2m8jpp | Dailymotion Spirit Movie (example) | ~1-2 min |
| https://www.dailymotion.com/video/x260fp0 | Example video | ~1-2 min |

### Tech Channel Browse
- https://www.dailymotion.com/us/channel/tech/1 - Tech channel with many short videos

### Notes for Dailymotion
- Dailymotion URLs follow format: `dailymotion.com/video/VIDEO_ID`
- Most videos have autogenerated transcripts available
- Supports time parameters: `?start=35` (seconds)

---

## Facebook Videos

| URL | Description | Duration |
|-----|-------------|----------|
| N/A - Facebook Watch has been discontinued | As of 2025, Facebook Watch redirects to Facebook Reels | N/A |

### Notes for Facebook
- Facebook Watch was discontinued and redirects to Facebook Reels as of 2025
- Public Facebook video URLs use format: `facebook.com/watch/?v=VIDEO_ID` or shortened `fb.watch/VIDEO_ID`
- Facebook Reels are short-form videos similar to TikTok
- Many Facebook videos require login to view

---

## Reddit Videos

| URL | Description | Duration |
|-----|-------------|----------|
| Browse: https://reddit.com/r/videos | r/videos subreddit - sort by Top for popular short videos | Various |

### Notes for Reddit
- Reddit video URLs vary in format
- Native Reddit videos: `v.redd.it/VIDEO_ID` or `reddit.com/r/SUBREDDIT/comments/POST_ID`
- Many Reddit videos are reposts from YouTube, TikTok, etc.
- Videos can be up to 15 minutes long, 1GB max file size
- Sort by "Top" -> "This Year" to find popular 2024 content

---

## Platform-Specific Considerations

### URL Format Summary
| Platform | URL Pattern | Example |
|----------|-------------|---------|
| YouTube | youtube.com/watch?v=ID | youtube.com/watch?v=WO4tIrjBDkk |
| YouTube Short | youtube.com/shorts/ID | youtube.com/shorts/3xReIHV13IQ |
| Vimeo | vimeo.com/ID | vimeo.com/2336458 |
| TikTok | tiktok.com/@USER/video/ID | tiktok.com/@bellapoarch/video/6862153058223197445 |
| X (Twitter) | x.com/USER/status/ID | x.com/Olympics/status/1873685005970669886 |
| Dailymotion | dailymotion.com/video/ID | dailymotion.com/video/x9vqjvo |
| Facebook | facebook.com/watch/?v=ID | (requires login for most content) |
| Reddit | reddit.com/r/SUB/comments/ID | (varies by post) |

### Common Issues
1. **Authentication Required**: Many platforms (Vimeo, Instagram, Facebook) require login for most videos. OpenTranscribe will display a user-friendly error message when this occurs.
2. **Private/Restricted Videos**: Some videos require login or are geo-restricted
3. **Age Verification**: Some platforms require age verification for certain content
4. **Deleted Content**: Videos may be removed over time - test URLs periodically
5. **Rate Limiting**: Platforms may rate-limit downloads/access
6. **DRM Protection**: Some platforms use DRM that prevents downloading

### Authentication Error Messages
When a video requires authentication, OpenTranscribe displays helpful messages like:
- "This Vimeo video requires a logged-in account. Most Vimeo videos require authentication. Try YouTube or Dailymotion instead."
- "This video is private or restricted. For best results, try publicly accessible videos on YouTube, Dailymotion, TikTok."
- "This video is age-restricted and requires verification."

### Recommended Test Workflow
1. Start with YouTube videos - most reliable and widely supported
2. Test Vimeo for professional/artistic content
3. Test TikTok for short-form vertical video
4. Test Dailymotion as YouTube alternative
5. Test X for social media video integration
6. Note any platform-specific failures for feature limitations

---

## Additional Resources

### Educational YouTube Channels with Short Content
- **MinutePhysics** (youtube.com/@minutephysics) - Physics explanations, 1-7 minutes
- **TED-Ed** (youtube.com/@TEDEd) - Educational animations, 3-10 minutes
- **Big Think** (youtube.com/@bigthink) - Expert interviews, 5-20 minutes
- **Kurzgesagt** (youtube.com/@kurzgesagt) - Science animations, 8-15 minutes

### Short Film Resources
- **Vimeo Staff Picks**: https://vimeo.com/watch (curated short films)
- **Short of the Week**: https://www.shortoftheweek.com/ (curated from Vimeo)

---

*Note: URLs were verified as of December 2025. Video availability may change over time. Always verify URLs are still accessible before running test suites.*
