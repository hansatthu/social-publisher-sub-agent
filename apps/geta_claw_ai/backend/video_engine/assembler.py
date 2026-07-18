import os
import time
from .content_writer import generate_tiktok_script
from .tts_engine import generate_tts
from .video_editor import create_tiktok_video

def generate_faceless_tiktok(topic: str, duration_seconds: int = 30, source_folder: str = "") -> str:
    """
    Tạo Video TikTok hoàn chỉnh.
    - Bước 1: Sinh kịch bản
    - Bước 2: Sinh Audio (TTS)
    - Bước 3: Dựng Video
    Trả về đường dẫn tới file MP4.
    """
    start_time = time.time()
    
    # Đảm bảo các thư mục output tồn tại
    output_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../outputs/tiktok_videos'))
    os.makedirs(output_dir, exist_ok=True)
    
    if source_folder:
        raw_videos_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../content/b_rolls', source_folder))
    else:
        raw_videos_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../raw_videos'))
        
    if not os.path.exists(raw_videos_dir) or not os.listdir(raw_videos_dir):
        # Fallback to default if custom folder doesn't exist or is empty
        fallback_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../raw_videos'))
        if not os.path.exists(fallback_dir) or not os.listdir(fallback_dir):
            raise ValueError(f"Chưa có video B-roll nào trong thư mục {raw_videos_dir}. Hãy copy vài video vào đó trước.")
        raw_videos_dir = fallback_dir
    
    # Tên file
    timestamp = int(time.time())
    audio_output = os.path.join(output_dir, f"audio_{timestamp}.wav")
    video_output = os.path.join(output_dir, f"video_{timestamp}.mp4")
    
    # Bước 1
    print("\n--- BƯỚC 1: SINH KỊCH BẢN ---")
    script = generate_tiktok_script(topic, duration_seconds)
    
    # Bước 2
    print("\n--- BƯỚC 2: SINH AUDIO TTS ---")
    generate_tts(script, audio_output)
    
    # Bước 3
    print("\n--- BƯỚC 3: DỰNG VIDEO ---")
    create_tiktok_video(audio_output, raw_videos_dir, video_output)
    
    elapsed = time.time() - start_time
    print(f"\n✅ Hoàn thành trong {elapsed:.2f}s. Video đã được lưu tại: {video_output}")
    
    return video_output

if __name__ == "__main__":
    # Script test
    try:
        from dotenv import load_dotenv
        load_dotenv("../../.env")
        result = generate_faceless_tiktok("Review bình giữ nhiệt vỏ tre khắc tên", 15)
        print("Test OK:", result)
    except Exception as e:
        print("Lỗi:", e)
