import os
from vieneu import Vieneu
import time

# Khởi tạo Engine ở cấp module (Singleton) để tiết kiệm thời gian load mô hình
# Sử dụng CPU/ONNX mặc định (rất nhanh)
print("[*] Loading VieNeu-TTS Engine (ONNX CPU)...")
tts_engine = Vieneu()

def generate_tts(text: str, output_path: str = "temp_tts.wav", voice_name: str = "Phạm Tuyên") -> str:
    """Sử dụng VieNeu-TTS để tạo file âm thanh từ văn bản.
    Mặc định sử dụng giọng 'Phạm Tuyên'. 
    Trả về đường dẫn tuyệt đối tới file wav.
    """
    print(f"[*] TTS Generating for text ({len(text)} chars)...")
    start_time = time.time()
    
    # Sinh âm thanh
    audio_data = tts_engine.infer(text, voice=voice_name)
    
    # Đảm bảo đường dẫn tuyệt đối
    abs_path = os.path.abspath(output_path)
    
    # Lưu file
    tts_engine.save(audio_data, abs_path)
    elapsed = time.time() - start_time
    print(f"[*] TTS Generated in {elapsed:.2f}s. Saved to {abs_path}")
    
    return abs_path

if __name__ == "__main__":
    # Test script
    test_text = "Chào mừng các bạn đến với công cụ tự động tạo video bằng trí tuệ nhân tạo."
    generate_tts(test_text, "test_audio.wav")
