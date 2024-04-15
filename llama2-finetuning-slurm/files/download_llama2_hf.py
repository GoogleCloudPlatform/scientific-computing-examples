# Copyright 2024 Google LLC

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#      http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from huggingface_hub import snapshot_download
model_id="meta-llama/Llama-2-7b-hf"
snapshot_download(repo_id=model_id, local_dir="./llama2-7b", 
                  local_dir_use_symlinks=False, revision="main", 
                  ignore_patterns=["*.safetensors", "model.safetensors.index.json"])
