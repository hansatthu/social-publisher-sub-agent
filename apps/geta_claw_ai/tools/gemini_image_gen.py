import os
import sys
import argparse
from io import BytesIO
from PIL import Image
from google import genai
from google.genai import types

# Danh sách API Keys xoay vòng (rotation/fallback)
GOOGLE_API_KEYS = [
    "AIzaSyAlOe_3hZrz07JLQuUve6HeixvZrTor-VA",
    "AIzaSyAnoMnblBXIUqx0u4wx0j1pQlYdj6T9xyc",
    "AIzaSyAfVpZzKUxzSxwrzvBI_eKvqMIg76871eg",
    "AIzaSyCv_NF-SX-fziwgbffgMb9RA1SVWK-Ty00",
    "AIzaSyBYsje26Lqjmc0vyhxyCjUtRrf3EErlETE",
    "AIzaSyAVco2SEWj08A5dBntbnByGy4xr-eGPG8M",
    "AIzaSyBxZIcLnb0v0DjeZhSrRQSi1bRRZ97FoSQ",
    "AIzaSyAd72wZ1eTpkWpKyHwkXcCtW4cCTYPawbE",
    "AIzaSyBDIZbemqMTQ429xOSLiaj3bN2snzu8DfM",
    "AIzaSyD8iF47_E01jYdNzH4KZjPBUXJJV6MRxCs"
]

def generate_image_with_fallback(prompt, output_path, aspect_ratio="1:1"):
    env_key = os.environ.get("GEMINI_API_KEY")
    keys_to_try = [env_key] if env_key else []
    keys_to_try.extend(GOOGLE_API_KEYS)
    
    last_error = None
    for idx, api_key in enumerate(keys_to_try):
        if not api_key:
            continue
        try:
            print(f"Trying Gemini API Key index {idx}...")
            client = genai.Client(api_key=api_key)
            
            result = client.models.generate_images(
                model='imagen-4.0-generate-001',
                prompt=prompt,
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    output_mime_type="image/jpeg",
                    aspect_ratio=aspect_ratio,
                )
            )
            
            for image in result.generated_images:
                img = Image.open(BytesIO(image.image.image_bytes))
                img.save(output_path)
                print(f"Image successfully saved to {output_path} using API Key index {idx}")
                return True
        except Exception as e:
            print(f"Gemini API Key index {idx} error: {e}")
            last_error = e
            
    print("All Gemini API Keys failed. Falling back to Pollinations.ai free API (Flux Model)...")
    try:
        import requests
        import urllib.parse
        encoded_prompt = urllib.parse.quote(prompt)
        width, height = 1024, 1024
        if aspect_ratio == "16:9":
            width, height = 1024, 576
        elif aspect_ratio == "9:16":
            width, height = 576, 1024
            
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={width}&height={height}&nologo=true&private=true&model=flux"
        print(f"Requesting image from: {url}")
        res = requests.get(url, timeout=30)
        if res.status_code == 200:
            img = Image.open(BytesIO(res.content))
            img.save(output_path)
            print(f"Image successfully generated and saved via Pollinations.ai fallback to {output_path}")
            return True
        else:
            raise Exception(f"Pollinations.ai returned status code {res.status_code}")
    except Exception as fallback_err:
        print(f"Fallback image generation failed: {fallback_err}")
        if last_error:
            raise last_error
        raise fallback_err
    return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate image using Google Gemini Imagen 3 API")
    parser.add_argument("--prompt", required=True, type=str, help="Prompt description for the image")
    parser.add_argument("--output", default="output_image.jpg", type=str, help="Output path for the generated image")
    parser.add_argument("--ratio", default="1:1", type=str, help="Aspect ratio (1:1, 3:4, 4:3, 9:16, 16:9)")
    
    args = parser.parse_args()
    
    try:
        generate_image_with_fallback(args.prompt, args.output, args.ratio)
    except Exception as e:
        print(f"Failed to generate image: {e}")
        sys.exit(1)
