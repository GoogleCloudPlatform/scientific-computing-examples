Request access:


https://huggingface.co/meta-llama/Llama-2-7b


Install Miniconda

```bash
mkdir -p ~/miniconda3
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O ~/miniconda3/miniconda.sh
bash ~/miniconda3/miniconda.sh -b -u -p ~/miniconda3
rm -rf ~/miniconda3/miniconda.sh
~/miniconda3/bin/conda init bash
exec bash
conda 
```


```
conda env create -n llama2 --file llama2.yml
```

Install with conda env with Sudo
```
sudo env "PATH=$PATH" conda env update -n llama2 --file llama2.yml
```

conda activate llama2

export HUGGING_FACE_HUB_TOKEN=

python download_llama2_hf.py 

python fine-tune.py