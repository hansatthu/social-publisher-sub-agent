import unittest
from unittest.mock import patch, MagicMock
import os
import sys
from unittest.mock import patch, MagicMock

# --- MOCK DEPENDENCIES BEFORE IMPORT ---
sys.modules['langchain_openai'] = MagicMock()
sys.modules['vieneu'] = MagicMock()
sys.modules['moviepy.editor'] = MagicMock()
sys.modules['moviepy.video.fx.all'] = MagicMock()

# Ensure backend is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from video_engine.content_writer import generate_tiktok_script
from video_engine.tts_engine import generate_tts
from video_engine.video_editor import get_broll_files
from video_engine.assembler import generate_faceless_tiktok

class TestVideoEngine(unittest.TestCase):

    @patch('video_engine.content_writer.ChatOpenAI')
    @patch('os.getenv')
    def test_generate_tiktok_script(self, mock_getenv, mock_chat_openai):
        # Mock environment variables
        def getenv_side_effect(key, default=None):
            if key == "DEEPSEEK_API_KEY":
                return "fake-key"
            return default
        mock_getenv.side_effect = getenv_side_effect
        
        # Mock LLM response
        mock_llm_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Day la kich ban test."
        mock_llm_instance.invoke.return_value = mock_response
        mock_chat_openai.return_value = mock_llm_instance

        script = generate_tiktok_script("Test topic", 15)
        self.assertEqual(script, "Day la kich ban test.")
        mock_llm_instance.invoke.assert_called_once()

    @patch('video_engine.tts_engine.tts_engine')
    def test_generate_tts(self, mock_tts_engine):
        mock_tts_engine.infer.return_value = b"fake audio data"
        output_path = generate_tts("Test", "test_output.wav")
        mock_tts_engine.infer.assert_called_with("Test", voice="Phạm Tuyên")
        mock_tts_engine.save.assert_called_with(b"fake audio data", os.path.abspath("test_output.wav"))
        self.assertEqual(output_path, os.path.abspath("test_output.wav"))

    def test_get_broll_files_empty(self):
        # Kiểm tra thư mục không tồn tại hoặc rỗng
        files = get_broll_files("thumuc_khong_ton_tai_123")
        self.assertEqual(files, [])

    @patch('video_engine.assembler.generate_tiktok_script')
    @patch('video_engine.assembler.generate_tts')
    @patch('video_engine.assembler.create_tiktok_video')
    @patch('os.listdir')
    def test_generate_faceless_tiktok(self, mock_listdir, mock_create_video, mock_generate_tts, mock_generate_script):
        # Giả lập thư mục tồn tại và có file
        mock_listdir.return_value = ["video1.mp4"]
        
        mock_generate_script.return_value = "Test script"
        mock_generate_tts.return_value = "test.wav"
        mock_create_video.return_value = "test.mp4"

        # Tạm thời tạo thư mục test để os.makedirs hoạt động bình thường
        output_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../outputs/tiktok_videos'))
        os.makedirs(output_dir, exist_ok=True)
        raw_videos_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../raw_videos'))
        os.makedirs(raw_videos_dir, exist_ok=True)
        
        output = generate_faceless_tiktok("Test topic", 15)
        
        self.assertTrue(output.endswith(".mp4"))
        mock_generate_script.assert_called_once_with("Test topic", 15)
        mock_generate_tts.assert_called_once()
        mock_create_video.assert_called_once()

if __name__ == '__main__':
    unittest.main()
