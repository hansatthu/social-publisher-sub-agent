import os
import random
from moviepy import VideoFileClip, concatenate_videoclips, AudioFileClip

def get_broll_files(raw_videos_dir: str):
    supported_exts = [".mp4", ".mov", ".avi", ".mkv"]
    brolls = []
    if os.path.exists(raw_videos_dir):
        for f in os.listdir(raw_videos_dir):
            if any(f.lower().endswith(ext) for ext in supported_exts):
                brolls.append(os.path.join(raw_videos_dir, f))
    return brolls

def create_tiktok_video(audio_path: str, raw_videos_dir: str, output_path: str):
    """
    Tạo video TikTok 9:16 bằng cách ghép các B-roll ngẫu nhiên cho vừa khít với thời lượng Audio.
    """
    print(f"[*] Starting Video Editor. Audio: {audio_path}")
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
        
    brolls = get_broll_files(raw_videos_dir)
    if not brolls:
        raise ValueError(f"No video files found in {raw_videos_dir}")
        
    # Lấy thời lượng của Audio
    audio_clip = AudioFileClip(audio_path)
    target_duration = audio_clip.duration
    print(f"[*] Target duration (Audio length): {target_duration:.2f}s")
    
    # Random shuffle brolls
    random.shuffle(brolls)
    
    clips = []
    original_clips = []
    current_duration = 0.0
    
    # 9:16 Resolution
    target_w, target_h = 1080, 1920
    
    for broll_path in brolls:
        if current_duration >= target_duration:
            break
            
        try:
            clip = VideoFileClip(broll_path)
            
            # Nếu clip dài quá, cắt ra đoạn ngẫu nhiên khoảng 3-5s hoặc phần còn thiếu
            needed_duration = target_duration - current_duration
            clip_dur = min(clip.duration, needed_duration, random.uniform(3.0, 5.0))
            
            # Chọn start time ngẫu nhiên
            max_start = max(0, clip.duration - clip_dur)
            start_t = random.uniform(0, max_start)
            subclip = clip.subclipped(start_t, start_t + clip_dur)
            
            # Resize & Crop to 9:16 (1080x1920)
            # 1. Resize sao cho chiều cao = 1920
            resized_clip = subclip.resized(height=target_h)
            
            # 2. Crop giữa khung hình nếu chiều rộng > 1080
            w, h = resized_clip.size
            if w > target_w:
                x_center = w / 2
                cropped_clip = resized_clip.cropped(x1=x_center - target_w/2, y1=0, x2=x_center + target_w/2, y2=target_h)
            else:
                # Nếu video hẹp hơn 1080, resize the width
                resized_clip = subclip.resized(width=target_w)
                w, h = resized_clip.size
                y_center = h / 2
                cropped_clip = resized_clip.cropped(x1=0, y1=y_center - target_h/2, x2=target_w, y2=y_center + target_h/2)
            
            # Bỏ âm thanh gốc
            cropped_clip = cropped_clip.without_audio()
            
            clips.append(cropped_clip)
            original_clips.append(clip)
            current_duration += clip_dur
        except Exception as e:
            print(f"[!] Error processing {broll_path}: {e}")
            continue
            
    if not clips:
        raise RuntimeError("Failed to process any video clips.")
        
    print(f"[*] Assembling {len(clips)} clips...")
    final_video = concatenate_videoclips(clips, method="compose")
    
    # Đảm bảo video không vượt quá audio
    final_video = final_video.subclipped(0, target_duration)
    
    # Gắn audio
    final_video = final_video.with_audio(audio_clip)
    
    print(f"[*] Exporting final video to {output_path}...")
    final_video.write_videofile(
        output_path, 
        fps=30, 
        codec="libx264", 
        audio_codec="aac",
        threads=4,
        preset="ultrafast",
        logger=None # Hide progress bar in logs
    )
    
    audio_clip.close()
    final_video.close()
    for c in original_clips:
        try:
            c.close()
        except:
            pass
    
    return output_path

if __name__ == "__main__":
    pass
