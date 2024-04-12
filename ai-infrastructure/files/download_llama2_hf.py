from huggingface_hub import snapshot_download
model_id="meta-llama/Llama-2-7b-hf"
snapshot_download(repo_id=model_id, local_dir="./llama2-7b", 
                  local_dir_use_symlinks=False, revision="main", 
                  ignore_patterns=["*.safetensors", "model.safetensors.index.json"])
