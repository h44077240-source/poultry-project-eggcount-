import os
from gradio_client import Client, handle_file

def process_video_with_gpu(video_path):
    space_id = os.environ.get("HF_SPACE_ID", "")
    hf_token = os.environ.get("HF_TOKEN", None)
    
    if not space_id:
        raise ValueError("HF_SPACE_ID environment variable is not set. Please configure HF_SPACE_ID.")

    # If token is empty string, treat as None for public spaces
    token_val = hf_token if hf_token and hf_token.strip() else None

    client = Client(
        space_id,
        token=token_val
    )
    result = client.predict(
        handle_file(video_path),
        api_name="/predict"
    )
    return result

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        test_video = sys.argv[1]
        print(f"Processing video with GPU: {test_video}")
        res = process_video_with_gpu(test_video)
        print("Result:", res)
    else:
        print("huggingface_gpu.py ready. Usage: process_video_with_gpu('path/to/video.mp4')")
