Request access:


https://huggingface.co/meta-llama/Llama-2-7b




ghpc create ml-cluster.yaml --vars project_id=openfoam-jrt -w --vars bucket_model=llama2-jrt --vars region=us-central1 --vars zone=us-central1-c ; ghpc deploy llama2-hpc --auto-approve

gcloud compute scp *.yml *.py schemd-image-test:~




 /opt/conda/bin/conda init
 source ~/.bashrc

 conda activate llama2

 export HUGGING_FACE_HUB_TOKEN=XXXXXXXXX

  python3 /data_bucket/download_llama2_hf.py 

