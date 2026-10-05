import requests
import os

# The directories to scrape
directories = [
    {"owner": "GoogleCloudPlatform", "repo": "cluster-toolkit", "path": "examples"},
    {"owner": "GoogleCloudPlatform", "repo": "cluster-toolkit", "path": "community/examples"},
    {"owner": "GoogleCloudPlatform", "repo": "scientific-computing-examples", "path": "cluster-toolkit-examples"}
]

output_dir = "agent_skill_yamls"

def download_yaml_files(owner, repo, path):
    """Recursively fetch YAML files and save them individually."""
    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    response = requests.get(api_url)
    
    if response.status_code != 200:
        print(f"Error fetching {api_url}: {response.status_code}")
        return

    items = response.json()
    
    for item in items:
        if item['type'] == 'file' and (item['name'].endswith('.yaml') or item['name'].endswith('.yml')):
            print(f"Fetching: {item['path']}")
            raw_response = requests.get(item['download_url'])
            if raw_response.status_code == 200:
                # Construct local file path using the repo name and the file's path
                local_path = os.path.join(output_dir, repo, item['path'])
                
                # Create directories if they don't exist
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                
                # Write the content to the individual file
                with open(local_path, 'w') as f:
                    f.write(f"# Source: https://github.com/{owner}/{repo}/blob/main/{item['path']}\n")
                    f.write(raw_response.text)
        elif item['type'] == 'dir':
            # Recursively search subdirectories
            download_yaml_files(owner, repo, item['path'])

def main():
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    for directory in directories:
        print(f"Scanning {directory['repo']}/{directory['path']}...")
        download_yaml_files(directory['owner'], directory['repo'], directory['path'])
        
    print(f"\nDone! All files have been downloaded to the '{output_dir}' directory.")
    print(f"To download them all easily, run this command next: zip -r {output_dir}.zip {output_dir}")

if __name__ == "__main__":
    main()

