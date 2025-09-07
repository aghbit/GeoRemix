# ensure the comfyUI server is running before executing this script
import os
from urllib.error import HTTPError
import requests
import websocket
import uuid
import json
import urllib.request
import urllib.parse

server_address = "127.0.0.1:8188"
client_id = str(uuid.uuid4())

def queue_prompt(prompt):
    p = {"prompt": prompt, "client_id": client_id}
    data = json.dumps(p).encode('utf-8')
    req = urllib.request.Request(
        f"http://{server_address}/prompt",
        data=data,
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        print(f"[HTTP {e.code}] {e.reason}\n{body}")
        raise

def get_image(filename, subfolder, folder_type):
    data = {"filename": filename, "subfolder": subfolder, "type": folder_type}
    url_values = urllib.parse.urlencode(data)
    with urllib.request.urlopen("http://{}/view?{}".format(server_address, url_values)) as response:
        return response.read()

def get_history(prompt_id):
    with urllib.request.urlopen("http://{}/history/{}".format(server_address, prompt_id)) as response:
        return json.loads(response.read())

def get_images(ws, prompt):
    prompt_id = queue_prompt(prompt)['prompt_id']
    output_images = {}
    current_node = ""
    while True:
        out = ws.recv()
        if isinstance(out, str):
            message = json.loads(out)
            if message['type'] == 'executing':
                data = message['data']
                if data['prompt_id'] == prompt_id:
                    if data['node'] is None:
                        break
                    else:
                        current_node = data['node']
        else:
            if current_node == 'save_image_websocket_node':
                images_output = output_images.get(current_node, [])
                images_output.append(out[8:])
                output_images[current_node] = images_output

    return output_images


def load_prompt(prompt_path):
    if not os.path.exists(f"workflows/{prompt_path}"):
        raise FileNotFoundError(f"Prompt file not found: workflows/{prompt_path}")
    with open(f"workflows/{prompt_path}", 'r') as f:
        prompt_text = f.read()
    
    return json.loads(prompt_text)


def save_processed_images(ws, workflow_path, img_paths, subfolder="before"):
    prompt = load_prompt(f"{workflow_path}")

    for filename in img_paths:
        img_path = f"{subfolder}/{filename}"
        prompt["11"]["inputs"]["image"] = img_path # 11 is the node ID for the input image node
    
        images = get_images(ws, prompt)
        for node_id in images:
            for image_data in images[node_id]:
                output_dir = f"pictures/after/{workflow_path.split('-')[0]}/{filename}"
                os.makedirs(output_dir, exist_ok=True)
                with open(f"{output_dir}/{filename}", 'wb') as img_file:
                    img_file.write(image_data)
                print(f"[OK] Saved: {output_dir}/{filename}")

def exists_on_server(server, filename, subfolder="before", folder_type="input"):
    qs = urllib.parse.urlencode({"filename": filename, "subfolder": subfolder, "type": folder_type})
    try:
        with urllib.request.urlopen(f"http://{server}/view?{qs}") as resp:
            return resp.status == 200
    except Exception:
        return False
    
def upload_to_comfy(server_address, filename, subfolder="before"):
    files = {"image": (filename, open(f"pictures/before/{filename}", "rb"))}
    data = {"subfolder": subfolder}
    r = requests.post(f"http://{server_address}/upload/image", files=files, data=data)
    r.raise_for_status()
    info = r.json()
    rel = f"{info.get('subfolder','')}/{info['name']}".strip("/")
    return rel

if __name__ == "__main__":
    for img in os.listdir("pictures/before"):
        if not exists_on_server(server_address, img, folder_type="input"):
            upload_to_comfy(server_address, img, subfolder="before")
    

    ws = websocket.WebSocket()
    ws.connect("ws://{}/ws?clientId={}".format(server_address, client_id))
    save_processed_images(ws, "cyberpunk-v2.json", os.listdir("pictures/before"))
    ws.close() 

    print("Done processing all images.")
