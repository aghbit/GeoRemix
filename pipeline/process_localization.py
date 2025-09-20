import os
from urllib.error import HTTPError
import uuid
from dotenv import load_dotenv
from api_helpers import wait_until_queue_empty, queue_prompt, load_prompt, load_prompt_text
from helpers import clear_outputs_dir, find_line_with_max_avg, copy_images_with_pattern

load_dotenv()

DEFAULT_OUTPUTS_PATH = os.getenv("DEFAULT_OUTPUTS_PATH", "")
DEFAULT_FIND_MAX_FILE = os.getenv("DEFAULT_FIND_MAX_FILE", "")
DEFAULT_COPY_DEST = os.getenv("DEFAULT_COPY_DEST", "")

server_address = os.getenv("SERVER_ADDRESS", "127.0.0.1:8188")
client_id = str(uuid.uuid4())
workflow_file = os.getenv("WORKFLOW_FILE", "pipeline_api.json")
pictures_directory = os.getenv("PICTURES_DIRECTORY", "pictures/paris/before")
prompts_directory = "prompts"


cfgs = [6.9, 7.5, 8.0]
denoises = [0.7, 0.8, 0.9]
seeds = [691033582574281, 42]



def process_images(workflow_path, pictures_dir, location_prompt):
    prompts = load_prompt_text(location_prompt)
    prompt_data = load_prompt(workflow_path)
    prompt_data["48"]["inputs"]["directory"] = pictures_dir
    prompt_data["48"]["inputs"]["image_load_cap"] = len(os.listdir(pictures_dir))
    prompt_data["5"]["inputs"]["batch_size"] = len(os.listdir(pictures_dir))
    prompt_data["38"]["inputs"]["limit"] = len(os.listdir(pictures_dir))
    prompt_data["2"]["inputs"]["text"] = prompts["positive_prompt"]
    prompt_data["3"]["inputs"]["text"] = prompts["negative_prompt"]
    prompt_data["40"]["inputs"]["text"] = prompts["verification_prompt"]

    i = 0

    for cfg in cfgs:
        for denoise in denoises:
            for seed in seeds:
                prompt_data["4"]["inputs"]["cfg"] = cfg
                prompt_data["4"]["inputs"]["denoise"] = denoise
                prompt_data["4"]["inputs"]["seed"] = seed
                prompt_data["7"]["inputs"]["filename_prefix"] = f"{i}batch"

                i += 1

                queue_prompt(prompt_data, server_address, client_id)
                
def localization_workflow(workflow_path, pictures_dir, prompts_text_dir):
    for filename in os.listdir(prompts_text_dir):
        clear_outputs_dir(DEFAULT_OUTPUTS_PATH)

        if not filename.lower().endswith(".json"):
            continue
        full_path = os.path.join(prompts_text_dir, filename)
        try:
            process_images(workflow_path, pictures_dir, full_path)
        except Exception as e:
            print(f"Error processing {full_path}: {e}")
            continue

        # wait until the server's prompt queue is empty before continuing
        wait_until_queue_empty(server_address)

        line_number, score = find_line_with_max_avg(DEFAULT_FIND_MAX_FILE)
        print(f"Best line in {DEFAULT_FIND_MAX_FILE}: {line_number} with average score {score}")
        
        base_name = os.path.splitext(filename)[0]
        new_dest = os.path.join(DEFAULT_COPY_DEST, base_name)
        os.makedirs(new_dest, exist_ok=True)
        copy_pattern = f"{line_number}batch"
        copy_images_with_pattern(DEFAULT_OUTPUTS_PATH, new_dest, copy_pattern)


if __name__ == "__main__":
    localization_workflow(workflow_file, pictures_directory, prompts_directory)
